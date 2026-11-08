"""Loopback-only, read-only viewer for the same tasks used by the Skill CLI."""
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from .config import UserError


WEB = Path(__file__).parent / "web"
MEDIA_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".wav", ".flac", ".mp3",
               ".m4a", ".ogg", ".mp4", ".mov", ".webm"}


def media_files(store, task):
    """Only explicitly registered media inside this task may be served."""
    paths = [asset["path"] for asset in task["assets"].values()]
    for item in (task.get("audio"), task.get("final")):
        if item:
            paths.append(item["path"])
    for segment in task["segments"]:
        paths.extend(segment.get(key) for key in ("audio", "clip", "tail_frame"))
    root = store.directory(task["id"]).resolve()
    result = {}
    for value in filter(None, paths):
        path = Path(value).resolve()
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if path.is_file() and path.suffix.lower() in MEDIA_TYPES:
            result[str(path)] = "/media/" + quote(task["id"]) + "/" + quote(relative.as_posix())
    return result


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, service, port=0):
        self.service = service
        super().__init__(("127.0.0.1", port), Handler)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Do not put private task names or media paths in access logs.

    def headers_for(self, status, content_type, length, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.headers_for(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def file(self, path, ranges=False):
        total = path.stat().st_size
        start, end, status = 0, total - 1, 200
        extra = {"Accept-Ranges": "bytes"} if ranges else {}
        requested = self.headers.get("Range") if ranges else None
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            if not match or not any(match.groups()):
                self.headers_for(416, "text/plain", 0, {"Content-Range": f"bytes */{total}"})
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), end) if last else end
            else:
                start = max(0, total - int(last))
            if start > end or start >= total:
                self.headers_for(416, "text/plain", 0, {"Content-Range": f"bytes */{total}"})
                return
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{total}"
        length = max(0, end - start + 1)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.headers_for(status, mime, length, extra)
        with path.open("rb") as source:
            source.seek(start)
            while length:
                chunk = source.read(min(length, 65536))
                if not chunk:
                    break
                self.wfile.write(chunk)
                length -= len(chunk)

    def do_GET(self):
        allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        if self.headers.get("Host") not in allowed_hosts:
            self.json({"error": "仅允许本机地址访问。"}, 403)
            return
        service = self.server.service
        route = unquote(urlsplit(self.path).path)
        try:
            if route in ("/", "/app.js", "/style.css"):
                self.file(WEB / ({"/": "index.html"}.get(route, route[1:])))
            elif route == "/api/tasks":
                tasks = [service.view(task) for task in service.store.list()]
                self.json([{key: task[key] for key in ("id", "title", "status", "updated_at")} for task in tasks])
            elif route == "/api/doctor":
                self.json(service.doctor())
            elif route.startswith("/api/tasks/"):
                task = service.store.load(route[len("/api/tasks/"):])
                current = {}
                for stage, record in task["reviews"].items():
                    try:
                        current[stage] = service.review(task["id"], stage)["digest"] == record["digest"]
                    except UserError:
                        current[stage] = False
                self.json({"task": service.view(task), "media": media_files(service.store, task), "reviews_current": current})
            elif route.startswith("/media/"):
                task_id, relative = route[len("/media/"):].split("/", 1)
                task = service.store.load(task_id)
                path = (service.store.directory(task_id) / relative).resolve()
                if str(path) not in media_files(service.store, task):
                    raise UserError("未找到已登记的任务媒体。")
                self.file(path, ranges=True)
            else:
                self.json({"error": "页面不存在。"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Browser may cancel a media range request during seeking.
        except (UserError, OSError, ValueError, KeyError, TypeError):
            self.json({"error": "无法读取该任务或媒体，请返回任务列表后刷新。"}, 404)

    def do_POST(self):
        self.json({"error": "工作台只读；请通过 Skill 审核和提交。"}, 405)


def serve(service, port):
    with WorkbenchServer(service, port) as server:
        print(json.dumps({"url": server.url, "mode": "read-only", "stop": "Ctrl+C"}, ensure_ascii=False), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
