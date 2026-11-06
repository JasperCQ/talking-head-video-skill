import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import UserError


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def fingerprint(path):
    path = Path(path)
    if not path.is_file():
        raise UserError(f"素材文件不存在：{path}")
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return {"path": str(path.resolve()), "sha256": checksum.hexdigest(), "bytes": path.stat().st_size}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
        tmp = Path(out.name)
        json.dump(data, out, ensure_ascii=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    def directory(self, task_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", task_id):
            raise UserError("任务编号只能包含字母、数字、短横线和下划线。")
        return self.root / "tasks" / task_id

    def load(self, task_id):
        path = self.directory(task_id) / "task.json"
        if not path.is_file():
            raise UserError(f"未找到任务 {task_id}。")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, task):
        task["updated_at"] = now()
        write_json(self.directory(task["id"]) / "task.json", task)

    def create(self, title, plan, assets):
        task = {"schema_version": 1, "id": "TH-" + uuid.uuid4().hex[:12], "title": title,
                "created_at": now(), "plan": plan, "assets": assets, "reviews": {},
                "operations": {}, "audio": None, "segments": [], "final": None}
        self.save(task)
        return task

    def list(self):
        return sorted((json.loads(p.read_text(encoding="utf-8"))
                       for p in (self.root / "tasks").glob("*/task.json")),
                      key=lambda t: t["updated_at"], reverse=True)

    @contextmanager
    def lock(self, task_id):
        directory = self.directory(task_id)
        directory.mkdir(parents=True, exist_ok=True)
        lock = directory / ".lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise UserError("此任务正在被另一个操作使用；若进程已退出，请先核查平台任务，再清除此任务的 .lock 文件。") from exc
        try:
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            yield
        finally:
            lock.unlink(missing_ok=True)
