"""Shared application service for the Skill CLI and the local workbench."""
import copy
import json
import shutil
from pathlib import Path

from . import media
from .config import MODES, UserError, workflow_id
from .provider import RunningHub, RunningHubError, node_info, validate_prompt
from .store import digest, fingerprint, now


class Service:
    def __init__(self, store, config, provider=None):
        self.store, self.config = store, config
        self.provider = provider or RunningHub(config)

    def create(self, plan, base_dir):
        plan = copy.deepcopy(plan)
        if not isinstance(plan.get("script"), str) or not plan["script"].strip():
            raise UserError("任务需要完整 script 口播文本。")
        if not isinstance(plan.get("assets"), dict):
            raise UserError("请提供 assets 中的 presenter、scene、product，以及 voice 或 audio。")
        assets = {}
        for key in ("presenter", "scene", "product", "voice", "audio"):
            value = plan["assets"].get(key)
            if value:
                path = Path(value).expanduser()
                if not path.is_absolute():
                    path = Path(base_dir) / path
                assets[key] = fingerprint(path)
        if not {"presenter", "scene", "product"} <= assets.keys() or not ({"audio", "voice"} & assets.keys()):
            raise UserError("基础流需要人物图、场景图、产品图，并提供参考音色 voice 或已录好的 audio。")
        for key in ("presenter", "scene", "product"):
            if Path(assets[key]["path"]).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise UserError(f"{key} 需要 PNG、JPEG 或 WebP 图片。")
        plan.pop("assets")
        task = self.store.create(str(plan.get("title") or "数字人口播"), plan, assets)
        # Copy inputs to the task, so moving the original folder doesn't break resumption.
        directory = self.store.directory(task["id"]) / "inputs"
        directory.mkdir()
        for key, asset in assets.items():
            target = directory / (key + Path(asset["path"]).suffix.lower())
            shutil.copyfile(asset["path"], target)
            task["assets"][key] = fingerprint(target)
        self.store.save(task)
        return self.view(task)

    def _asset(self, task, key):
        current = fingerprint(task["assets"][key]["path"])
        if current != task["assets"][key]:
            raise UserError(f"已绑定的 {key} 素材发生变化；请新建修订任务重新审核。")
        return current

    def _review_object(self, task, stage):
        if stage == "content":
            return {"plan": task["plan"], "assets": {key: self._asset(task, key) for key in task["assets"]}}
        self._require(task, "content")
        if stage == "audio":
            if not task["audio"]:
                raise UserError("尚无可试听的主音频。")
            return {"script": task["plan"]["script"], "audio": fingerprint(task["audio"]["path"])}
        self._require(task, "audio")
        if stage == "segments":
            if not task["segments"]:
                raise UserError("尚未分段。")
            return [{key: segment[key] for key in ("index", "text", "start_seconds", "duration_seconds")}
                    | {"audio": fingerprint(segment["audio"])} for segment in task["segments"]]
        self._require(task, "segments")
        if stage.startswith("prompt:"):
            index = self._index(task, stage.split(":")[1])
            return self._video_operation(task, index)
        if stage.startswith("clip:"):
            index = self._index(task, stage.split(":")[1])
            segment = task["segments"][index]
            if not segment.get("clip"):
                raise UserError("此片段尚未完成。")
            operation_digest = digest(self._video_operation(task, index))
            record = task["operations"].get(self._operation_key(task, index), {})
            if record.get("status") != "succeeded" or record.get("digest") != operation_digest:
                raise UserError("视频产物与当前生产对象不匹配；请恢复原配置或创建修订任务。")
            return {"clip": fingerprint(segment["clip"]), "text": segment["text"],
                    "prompt_digest": operation_digest}
        if stage == "final":
            for index in range(len(task["segments"])):
                self._require(task, f"clip:{index}")
            if not task["final"]:
                raise UserError("尚无最终成片。")
            return {"final": fingerprint(task["final"]["path"]), "script": task["plan"]["script"]}
        raise UserError("未知审核阶段。")

    def _accepted(self, task, stage):
        record = task["reviews"].get(stage)
        return bool(record and record["digest"] == digest(self._review_object(task, stage)))

    def _require(self, task, stage):
        if not self._accepted(task, stage):
            raise UserError(f"请先展示并批准 {stage} 的当前审核对象。")

    def review(self, task_id, stage):
        task = self.store.load(task_id)
        value = self._review_object(task, stage)
        return {"task_id": task_id, "stage": stage, "digest": digest(value), "object": value}

    def approve(self, task_id, stage, expected_digest, by="user"):
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            value = self._review_object(task, stage)
            if digest(value) != expected_digest:
                raise UserError("审核对象已变更；请重新展示当前版本。")
            if stage.startswith("clip:"):
                index = self._index(task, stage.split(":")[1])
                segment = task["segments"][index]
                info = media.video_info(segment["clip"])
                if info["height"] <= info["width"]:
                    raise UserError("此片段不是竖屏，不能作为竖屏片段通过。")
                if abs(info["duration_seconds"] - segment["duration_seconds"]) > 0.75:
                    raise UserError("片段与驱动音频时长差超过 0.75 秒，请先核查截断、重复或静默。")
                segment["tail_frame"] = media.tail_frame(segment["clip"], self.store.directory(task_id) / f"tail-{index}.png")
            task["reviews"][stage] = {"digest": expected_digest, "by": by, "at": now()}
            self.store.save(task)
            return self.view(task)

    def use_input_audio(self, task_id):
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            self._require(task, "content")
            if task["audio"] or task["operations"]:
                raise UserError("已有音频或生产记录；不会覆盖。")
            if "audio" not in task["assets"]:
                raise UserError("本任务没有绑定已录好的 audio。")
            audio = self._asset(task, "audio")
            task["audio"] = {"path": audio["path"], "duration_seconds": media.duration(audio["path"]), "source": "user"}
            self.store.save(task)
            return self.view(task)

    def segment(self, task_id, texts=None, boundaries=None):
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            self._require(task, "audio")
            if any(op["mode"] != "tts" for op in task["operations"].values()):
                raise UserError("视频已提交，不能改变其分段；请新建修订任务。")
            texts = texts or task["plan"].get("segments") or [task["plan"]["script"]]
            if not isinstance(texts, list) or "".join(texts) != task["plan"]["script"]:
                raise UserError("分段文本拼接必须逐字等于已批准的完整口播，包括空格和换行。")
            task["segments"] = media.split_audio(task["audio"]["path"], texts,
                                                  self.store.directory(task_id) / "audio-segments", boundaries)
            self.store.save(task)
            return self.review(task_id, "segments")

    def _index(self, task, value):
        try:
            index = int(value)
        except (ValueError, TypeError) as exc:
            raise UserError("片段序号需要整数（从 0 开始）。") from exc
        if not 0 <= index < len(task["segments"]):
            raise UserError("片段序号超出范围。")
        return index

    def set_prompt(self, task_id, index, prompt, mode=None):
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            self._require(task, "segments")
            index = self._index(task, index)
            key = self._operation_key(task, index)
            if key in task["operations"]:
                raise UserError("此版本已有提交记录；修改前请显式创建新的尝试。")
            segment = task["segments"][index]
            chosen = mode or segment["mode"]
            if chosen not in ("fl-base", "fl-i2v") or (index == 0 and chosen != "fl-base"):
                raise UserError("首段必须使用 fl-base；后续同一连续人物块可使用 fl-i2v。")
            validate_prompt(prompt, segment["text"], chosen)
            segment.update(prompt=prompt, mode=chosen)
            self.store.save(task)
            return self.review(task_id, f"prompt:{index}")

    def _operation_key(self, task, index=None):
        base = "tts" if index is None else f"video-{index}"
        attempt = task.get("attempts", {}).get(base, 1)
        return f"{base}-attempt-{attempt}"

    def _video_operation(self, task, index):
        segment = task["segments"][index]
        self._require(task, "segments")
        if index:
            self._require(task, f"clip:{index - 1}")
        validate_prompt(segment["prompt"], segment["text"], segment["mode"])
        files = {"audio": fingerprint(segment["audio"])}
        if segment["mode"] == "fl-base":
            files.update({key: self._asset(task, key) for key in ("presenter", "scene", "product")})
        else:
            files["first_frame"] = fingerprint(task["segments"][index - 1]["tail_frame"])
        # Unconfigured previews are explicit; submit separately requires a numeric ID.
        selected_id = self.config.get("workflows", {}).get(segment["mode"])
        return {"key": self._operation_key(task, index), "mode": segment["mode"],
                "workflow_id": selected_id, "index": index, "files": files,
                "text": segment["text"], "prompt": segment["prompt"],
                "duration_seconds": segment["duration_seconds"], "instance_type": "plus"}

    def preview(self, task_id, index=None):
        task = self.store.load(task_id)
        self._require(task, "content")
        if index is None:
            if task["audio"]:
                raise UserError("主音频已存在，不会另提交 TTS。")
            if "voice" not in task["assets"]:
                raise UserError("请先使用已有 audio，或为新任务提供参考音色 voice。")
            operation = {"key": self._operation_key(task), "mode": "tts", "workflow_id": self.config.get("workflows", {}).get("tts"),
                         "files": {"voice": self._asset(task, "voice")}, "text": task["plan"]["script"],
                         "style": task["plan"].get("voice_style", "自然、专业、亲切的普通话讲解，语速连贯。"), "instance_type": "plus"}
        else:
            index = self._index(task, index)
            self._require(task, f"prompt:{index}")
            operation = self._video_operation(task, index)
        return {"task_id": task_id, "digest": digest(operation), "operation": operation,
                "nodeInfoList": node_info(operation), "paid_tasks": 1,
                "fee": "未知；按 RunningHub 实际扣费。此预览不提交、不上传。",
                "configured": bool(operation["workflow_id"] and str(operation["workflow_id"]).isascii() and str(operation["workflow_id"]).isdigit())}

    def submit(self, task_id, expected_digest, index=None, approved=False, calibration=False):
        if not approved:
            raise UserError("必须在展示当前预览并取得明确付费批准后，传 --approved-paid-run。")
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            preview = self.preview(task_id, index)
            operation = preview["operation"]
            if preview["digest"] != expected_digest:
                raise UserError("付费预览已变更；请重新展示并取得本次批准。")
            workflow_id(self.config, operation["mode"])
            if operation["key"] in task["operations"]:
                raise UserError("此操作已有提交日志；请 poll 恢复查询，不会重复创建。")
            if operation["mode"] != "tts" and not self._portrait_verified(operation["mode"]):
                if not calibration:
                    raise UserError("当前工作流竖屏尚未验证；请明确批准本段为 --calibration 样片，审核实测后再登记。")
            inspection = self.provider.inspect(operation["mode"])
            uploaded = {asset["path"]: self.provider.upload(asset["path"]) for asset in operation["files"].values()}
            if any(fingerprint(asset["path"]) != asset for asset in operation["files"].values()):
                raise UserError("素材在上传期间发生变化；未提交付费任务，请重新审核。")
            record = {"mode": operation["mode"], "index": index, "digest": expected_digest,
                      "status": "attempting", "paid_approval_at": now(), "calibration": calibration,
                      "inspection": inspection, "workflow_id": operation["workflow_id"]}
            task["operations"][operation["key"]] = record
            self.store.save(task)  # Durable intent BEFORE create; an ambiguous create must never be repeated.
            try:
                platform_id = self.provider.submit(operation, node_info(operation, uploaded))
            except RunningHubError as exc:
                record.update(error_code=exc.code, submission_outcome="unknown")
                # Official 416 explicitly means task creation failed for insufficient funds.
                # Unknown codes (including 605) may not safely be treated as a rejection.
                if exc.code == 416:
                    record.update(status="failed", submission_outcome="rejected", finished_at=now())
                self.store.save(task)
                raise
            record.update(status="submitted", platform_task_id=platform_id, submitted_at=now())
            self.store.save(task)  # Preserve platform ID before polling or downloading anything.
            return {"task_id": task_id, "operation_key": operation["key"], **record}

    def poll(self, task_id, key):
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            record = task["operations"].get(key)
            if not record:
                raise UserError("未找到该操作。")
            if record["status"] in ("succeeded", "failed"):
                return self.view(task)
            if not record.get("platform_task_id"):
                raise UserError("提交结果未知。请在平台核对后用 recover 绑定已有任务 ID；不会自动重提。")
            result = self.provider.poll(record["platform_task_id"])
            if result["status"] == "failed":
                record.update(status="failed", finished_at=now())
            elif result["status"] == "succeeded":
                paths = self.provider.download(result["urls"], self.store.directory(task_id) / "outputs" / key, record["mode"])
                path = paths[0]
                if record["mode"] == "tts":
                    task["audio"] = {"path": path, "duration_seconds": media.duration(path), "source": "drama3"}
                else:
                    media.video_info(path)
                    task["segments"][record["index"]]["clip"] = path
                record.update(status="succeeded", paths=paths, finished_at=now())
            self.store.save(task)
            return self.view(task)

    def recover(self, task_id, key, platform_id):
        if not str(platform_id).isascii() or not str(platform_id).isdigit():
            raise UserError("平台任务 ID 必须为数字。")
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            record = task["operations"].get(key)
            if not record or record["status"] != "attempting" or record.get("platform_task_id"):
                raise UserError("仅允许人工核查后，为结果未知的提交绑定任务 ID。")
            self.provider.poll(platform_id)  # Read-only check; never submits.
            record.update(platform_task_id=str(platform_id), status="submitted", recovered_at=now())
            self.store.save(task)
            return self.view(task)

    def retry(self, task_id, index, reason):
        if not reason.strip():
            raise UserError("请记录明确的重做原因；重做仍需新的付费批准。")
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            key = self._operation_key(task, index)
            record = task["operations"].get(key)
            if not record or record["status"] not in ("succeeded", "failed"):
                raise UserError("只能显式重做已完成或已失败的操作；运行中和结果未知的操作只能恢复查询。")
            if index is None:
                if any(op["mode"] != "tts" for op in task["operations"].values()):
                    raise UserError("已有视频提交，不能替换其主音频；请创建修订任务。")
                task["audio"], task["segments"] = None, []
                task["reviews"] = {k: v for k, v in task["reviews"].items() if k == "content"}
                base = "tts"
            else:
                index = self._index(task, index)
                if any(op.get("index") is not None and op["index"] > index for op in task["operations"].values()):
                    raise UserError("后续视频已依赖此片段，不能单独替换；请新建修订任务。")
                segment = task["segments"][index]
                segment.update(clip=None, prompt="")
                segment.pop("tail_frame", None)
                task["final"] = None
                for stage in (f"prompt:{index}", f"clip:{index}", "final"):
                    task["reviews"].pop(stage, None)
                base = f"video-{index}"
            task.setdefault("attempts", {})[base] = task.get("attempts", {}).get(base, 1) + 1
            record["retry_reason"] = reason
            self.store.save(task)
            return self.view(task)

    def assemble(self, task_id):
        with self.store.lock(task_id):
            task = self.store.load(task_id)
            for index in range(len(task["segments"])):
                self._require(task, f"clip:{index}")
            if not task["segments"]:
                raise UserError("尚无可合并的片段。")
            task["reviews"].pop("final", None)
            task["final"] = media.assemble(task["segments"], task["audio"]["path"],
                                            self.store.directory(task_id) / "final.mp4")
            self.store.save(task)
            return self.review(task_id, "final")

    def _portrait_verified(self, mode):
        evidence = self.config.get("portrait_evidence", {}).get(mode, {})
        return bool(evidence and evidence.get("workflow_id") == self.config.get("workflows", {}).get(mode))

    def verify_portrait(self, task_id, config_path, index=0):
        task = self.store.load(task_id)
        index = self._index(task, index)
        self._require(task, f"clip:{index}")
        op = task["operations"].get(self._operation_key(task, index), {})
        mode = task["segments"][index]["mode"]
        if not op.get("calibration") or op.get("workflow_id") != workflow_id(self.config, mode):
            raise UserError("需要当前工作流生成并审核通过的 calibration 样片。")
        from .store import write_json
        self.config.setdefault("portrait_evidence", {})[mode] = {"task_id": task_id, "workflow_id": op["workflow_id"],
                                            "clip": fingerprint(task["segments"][index]["clip"]), "at": now()}
        write_json(config_path, self.config)
        return {"portrait_verified": True, "mode": mode, "evidence": self.config["portrait_evidence"][mode]}

    def view(self, task):
        result = copy.deepcopy(task)
        def status():
            if not self._accepted(task, "content"):
                return "content_review"
            if not task["audio"]:
                op = task["operations"].get(self._operation_key(task))
                return self._op_status(op) if op else ("ready_import_audio" if "audio" in task["assets"] else "paid_tts_review")
            if not self._accepted(task, "audio"):
                return "audio_review"
            if not task["segments"]:
                return "segmentation_needed"
            if not self._accepted(task, "segments"):
                return "segmentation_review"
            for index, segment in enumerate(task["segments"]):
                if not segment["prompt"]:
                    return "prompt_needed"
                if not self._accepted(task, f"prompt:{index}"):
                    return "prompt_review"
                if not segment["clip"]:
                    op = task["operations"].get(self._operation_key(task, index))
                    return self._op_status(op) if op else "paid_video_review"
                if not self._accepted(task, f"clip:{index}"):
                    return "clip_review"
            if not task["final"]:
                return "ready_assembly"
            return "completed" if self._accepted(task, "final") else "final_review"
        try:
            result["status"] = status()
        except UserError as exc:
            result.update(status="blocked", blocker=str(exc))
        return result

    @staticmethod
    def _op_status(record):
        return {"attempting": "needs_reconciliation", "submitted": "running", "failed": "execution_failed",
                "succeeded": "output_review"}.get(record["status"], "blocked")

    def doctor(self):
        workflows = {}
        for mode in MODES:
            try:
                workflows[mode] = {"configured": True, "workflow_id": workflow_id(self.config, mode)}
            except UserError:
                workflows[mode] = {"configured": False}
        try:
            binary = media.ffmpeg()
        except UserError:
            binary = None
        from .config import api_key
        try:
            api_key()
            key_present = True
        except UserError:
            key_present = False
        return {"ffmpeg": binary, "api_key_present": key_present, "workflows": workflows,
                "portrait_verified": {mode: self._portrait_verified(mode) for mode in ("fl-base", "fl-i2v")},
                "note": "本检查离线运行；配置存在不代表接口或生成质量已验证。"}

    def setup(self, with_tts=False):
        checks = self.doctor()
        result = {"checks": checks, "inspections": {}}
        if not checks["ffmpeg"]:
            return {**result, "status": "needs_runtime",
                    "message": "进入首次配置：请由 Agent 准备 FFmpeg，再继续连接 RunningHub。"}
        if not checks["api_key_present"]:
            return {**result, "status": "needs_authorization",
                    "message": "进入首次配置：请在本机安全授权自己的 RunningHub API Key，并确保账号有可用额度。"
                               "视频生成配置已内置，授权后由 Agent 检查服务。请不要把 Key 发到聊天。"}
        modes = ("fl-base", "fl-i2v", "tts") if with_tts else ("fl-base", "fl-i2v")
        for mode in modes:
            try:
                result["inspections"][mode] = {"ok": True, **self.provider.inspect(mode)}
            except UserError as exc:
                result["inspections"][mode] = {"ok": False, "error": str(exc)}
        if not all(item["ok"] for item in result["inspections"].values()):
            return {**result, "status": "needs_service_attention",
                    "message": "内置生成服务检查未通过。请由 Agent 排查授权、平台权限或服务配置；"
                               "不要要求用户自行寻找或设计 H3 工作流，也不能报告已接通。"}
        return {**result, "status": "connected",
                "message": "本次所需生成服务已通过只读结构检查，可以继续整理素材和文案。"
                           "未上传素材或提交生成；额度、云端模型和实际生成效果仍需按本次方案确认。"}
