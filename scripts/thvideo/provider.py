"""RunningHub transport and the inherited Drama3 / MiniMax H3 node contracts."""
import json
import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .config import UserError, api_key, workflow_id


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = json.loads((ROOT / "references/workflow-contracts.json").read_text(encoding="utf-8"))
BASE_URL = "https://www.runninghub.cn"
AUDIO_SUFFIXES = {".flac", ".wav", ".mp3", ".m4a", ".ogg"}


class RunningHubError(UserError):
    def __init__(self, code):
        # Never echo arbitrary response fields, including a malformed code value.
        self.code = code if type(code) is int else None
        label = self.code if self.code is not None else "unknown"
        super().__init__(f"RunningHub 返回错误码 {label}；请在平台核查。")


def find_graph(value):
    if isinstance(value, str):
        try:
            return find_graph(json.loads(value))
        except ValueError:
            return None
    if isinstance(value, dict):
        if any(str(k).isdigit() and isinstance(v, dict) and "inputs" in v for k, v in value.items()):
            return value
        return next((graph for child in value.values() if (graph := find_graph(child))), None)
    if isinstance(value, list):
        return next((graph for child in value if (graph := find_graph(child))), None)
    return None


def validate_graph(response, mode):
    graph = find_graph(response)
    if not graph:
        raise UserError("接口未返回可核验的 API 工作流图。")
    contract = CONTRACTS[mode]
    for node_id, rule in contract["nodes"].items():
        node = graph.get(node_id, {})
        if node.get("class_type") != rule["class_type"]:
            raise UserError(f"工作流节点 {node_id} 类型不符合登记契约：{rule['class_type']}。")
        missing = set(rule["fields"]) - set(node.get("inputs", {}))
        if missing:
            raise UserError(f"工作流节点 {node_id} 缺少字段：{', '.join(sorted(missing))}。")
    for edge in contract["links"]:
        actual = graph[edge["target"]]["inputs"].get(edge["field"])
        if actual != [edge["source"], edge["slot"]]:
            raise UserError(f"工作流连线不匹配：{edge['target']}.{edge['field']}。")
    if mode != "tts":
        inputs = graph["76"]["inputs"]
        kind = str(inputs.get("task_type", "")).lower()
        if ("ref2va" if mode == "fl-base" else "i2va") not in kind:
            raise UserError("H3 工作流类型不符合基础流 / 续接流登记。")
        allowed_media = {"drive_audio"} | ({f"ref_images.ref_image_{i}" for i in range(3)} if mode == "fl-base" else {"first_frame"})
        for field, value in inputs.items():
            if (field.startswith(("ref_images.", "ref_videos.", "ref_video_audios.", "ref_audios."))
                    or field in ("first_frame", "last_frame", "final_audio", "drive_audio")):
                if field not in allowed_media and value not in (None, ""):
                    raise UserError(f"工作流连接了契约外媒体输入：76.{field}。")
        if inputs.get("audio_mode") != "remix_source" or inputs.get("audio_denoise_strength") != 0:
            raise UserError("工作流必须使用 remix_source 且 audio_denoise_strength=0，以保留驱动语音。")
    return graph


def validate_prompt(prompt, text, mode):
    sections = ["subject_definitions:", "summary:", "retention_analysis:",
                "detailed_description:", "overall_soundscape:", "non_diegetic_music:"]
    positions = [prompt.find(section) for section in sections]
    if min(positions) < 0 or positions != sorted(positions):
        raise UserError("H3 提示词须包含顺序正确的六段式结构。")
    if not text or prompt.count(text) != 1 or f"<d>[Chinese]{text}</d>" not in prompt:
        raise UserError("提示词必须逐字、仅一次包含 <d>[Chinese]批准口播</d>。")
    tags = set(re.findall(r"<(Picture|Audio)\s+(\d+)>", prompt, re.I))
    allowed = {("Picture", "1"), ("Picture", "2"), ("Picture", "3")} if mode == "fl-base" else set()
    if not tags <= allowed:
        raise UserError("提示词引用了未连接的媒体标签；续接流仅使用 first_frame，驱动音频没有编号标签。")
    if "[Shot 1]" not in prompt or re.search(r"\[Shot\s+(?:[2-9]|\d{2,})\]", prompt):
        raise UserError("每段数字人口播使用一个连续 [Shot 1]。")
    if "drive_audio" not in prompt or "(S1)" not in prompt:
        raise UserError("请在提示词中明确把唯一 drive_audio 绑定到说话人 (S1)。")


def node_info(operation, uploaded=None):
    uploaded = uploaded or {}
    def file(key):
        path = operation["files"][key]["path"]
        return uploaded.get(path, f"<upload:{Path(path).name}>")
    def item(node, field, value):
        return {"nodeId": str(node), "fieldName": field, "fieldValue": value}
    if operation["mode"] == "tts":
        return [item(2, "audio", file("voice")), item(12, "prompt", operation["text"]),
                item(13, "prompt", operation["style"])]
    result = [item(73, "value", operation["duration_seconds"]), item(74, "audio", file("audio")),
              item(78, "aspect_ratio", "9:16 (Portrait Widescreen)"),
              item(78, "megapixels", 1), item(78, "multiple", 32), item(79, "prompt", operation["prompt"])]
    if operation["mode"] == "fl-base":
        result.extend(item(node, "image", file(key)) for node, key in [(72, "presenter"), (84, "scene"), (85, "product")])
    else:
        result.append(item(86, "image", file("first_frame")))
    return result


class RunningHub:
    def __init__(self, config):
        self.config = config

    def _json(self, path, payload, include_key=True):
        key = api_key()
        body = {"apiKey": key, **payload} if include_key else payload
        request = urllib.request.Request(BASE_URL + path, data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise UserError(f"RunningHub HTTP {exc.code}；请核查账号权限或平台状态。") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise UserError("RunningHub 请求中断；提交结果可能未知，请按本地日志核查，勿重复创建任务。") from exc

    def _success(self, data):
        if data.get("code") != 0:
            raise RunningHubError(data.get("code"))
        return data

    def inspect(self, mode):
        response = self._success(self._json("/api/openapi/getJsonApiFormat", {"workflowId": workflow_id(self.config, mode)}))
        graph = validate_graph(response, mode)
        return {"mode": mode, "workflow_id": workflow_id(self.config, mode), "nodes": len(graph)}

    def upload(self, path):
        key = api_key()
        path = Path(path)
        boundary = "----talking-head-" + uuid.uuid4().hex
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        # A neutral filename avoids exposing local names and is safe in MIME headers.
        name = "asset" + path.suffix.lower()
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                f'Content-Type: {mime}\r\n\r\n').encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(BASE_URL + "/openapi/v2/media/upload/binary", data=body,
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = self._success(json.load(response))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise UserError("素材上传失败；尚未创建付费任务。") from exc
        value = (data.get("data") or {}).get("fileName")
        if not value:
            raise UserError("素材上传响应缺少 data.fileName。")
        return value

    def submit(self, operation, nodes):
        data = self._success(self._json("/task/openapi/create", {"workflowId": operation["workflow_id"],
                              "nodeInfoList": nodes, "instanceType": operation["instance_type"]}))
        value = (data.get("data") or {}).get("taskId")
        if not value:
            raise UserError("提交响应缺少 taskId。请核查平台，不会自动重提。")
        return str(value)

    def poll(self, task_id):
        data = self._json("/openapi/v2/query", {"taskId": task_id}, include_key=False)
        if str(data.get("taskId")) != str(task_id):
            raise UserError("查询响应未匹配本次任务 ID；请核查平台。")
        status = data.get("status")
        if status in ("QUEUED", "RUNNING"):
            return {"status": "running"}
        if status == "FAILED":
            return {"status": "failed", "code": data.get("errorCode")}
        if status != "SUCCESS":
            raise UserError("平台返回未知任务状态；已保留任务 ID，请稍后查询或核查平台。")
        urls = [item["url"] for item in (data.get("results") or []) if item.get("url")]
        if not urls:
            raise UserError("平台报告完成但未返回可下载文件；任务 ID 已保存，可稍后再查询。")
        return {"status": "succeeded", "urls": list(dict.fromkeys(urls))}

    def download(self, urls, directory, mode):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for index, url in enumerate(urls):
            parsed = urllib.parse.urlparse(url)
            suffix = Path(parsed.path).suffix.lower()
            allowed = AUDIO_SUFFIXES if mode == "tts" else {".mp4", ".mov", ".webm"}
            if suffix not in allowed:
                continue
            if parsed.scheme != "https":
                raise UserError("拒绝下载非 HTTPS 产物。")
            target = directory / f"output-{index + 1:02d}{suffix}"
            partial = target.with_suffix(target.suffix + ".part")
            # Signed CDN requests intentionally carry no API credential.
            try:
                with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as response, partial.open("wb") as out:
                    import shutil
                    shutil.copyfileobj(response, out)
                partial.replace(target)
            except (urllib.error.URLError, TimeoutError) as exc:
                raise UserError("产物下载中断；可再次查询同一任务 ID，不会重新提交。") from exc
            paths.append(str(target.resolve()))
        if not paths:
            raise UserError("平台未产出本次所需的音频 / 视频文件。")
        return paths
