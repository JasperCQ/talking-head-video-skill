#!/usr/bin/env python3
"""Command-line entry point. Run with --help for supported operations."""
import argparse
import json
import os
import sys
from pathlib import Path

from thvideo.config import CONFIG_PATH, DATA_PATH, UserError, load_config
from thvideo.service import Service
from thvideo.store import Store


def parser():
    p = argparse.ArgumentParser(description="数字人口播 Skill / 工作台共用生产入口")
    p.add_argument("--config", type=Path, default=Path(os.environ.get("TALKING_HEAD_CONFIG", CONFIG_PATH)).expanduser())
    p.add_argument("--data-dir", type=Path, default=DATA_PATH)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="离线检查配置与媒体工具，不输出密钥")
    setup = sub.add_parser("setup", help="首次接入：检查环境和授权，只读核验内置服务，不上传或生成")
    setup.add_argument("--with-tts", action="store_true", help="还需内置参考音色配音时检查 TTS 服务")
    sub.add_parser("list", help="列出本地任务")
    serve = sub.add_parser("serve", help="启动本机只读审片工作台，不会提交生成或修改审核")
    serve.add_argument("--port", type=int, default=0, help="监听端口；默认由系统分配")
    create = sub.add_parser("create", help="从本地 JSON 任务草稿创建任务")
    create.add_argument("--plan", required=True, type=Path)
    for name in ("show", "use-audio", "assemble", "verify-portrait"):
        command = sub.add_parser(name)
        command.add_argument("task_id")
        if name == "verify-portrait":
            command.add_argument("--index", type=int, default=0)
    review = sub.add_parser("review", help="显示当前审核对象与版本摘要")
    review.add_argument("task_id")
    review.add_argument("stage", help="content / audio / segments / prompt:0 / clip:0 / final")
    approve = sub.add_parser("approve", help="仅在用户审阅并明确批准后记录批准")
    approve.add_argument("task_id")
    approve.add_argument("stage")
    approve.add_argument("--digest", required=True)
    approve.add_argument("--by", default="user")
    segment = sub.add_parser("segment", help="按实测音频与自然停顿拆分，随后必须试听审核")
    segment.add_argument("task_id")
    segment.add_argument("--cuts", type=Path, help='JSON: {"texts": [...], "boundaries_seconds": [...]}；切点可省略')
    prompt = sub.add_parser("set-prompt", help="保存 Agent 根据实际图片编写的 H3 提示词")
    prompt.add_argument("task_id")
    prompt.add_argument("--index", required=True, type=int)
    prompt.add_argument("--file", required=True, type=Path)
    prompt.add_argument("--mode", choices=("fl-base", "fl-i2v"))
    for name in ("preview", "submit", "retry"):
        command = sub.add_parser(name)
        command.add_argument("task_id")
        command.add_argument("--index", type=int, help="视频片段序号，从 0 开始；不填表示 TTS")
        if name == "submit":
            command.add_argument("--digest", required=True)
            command.add_argument("--approved-paid-run", action="store_true")
            command.add_argument("--calibration", action="store_true", help="首次基础流竖屏校准样片")
        if name == "retry":
            command.add_argument("--reason", required=True)
    for name in ("poll", "recover"):
        command = sub.add_parser(name)
        command.add_argument("task_id")
        command.add_argument("--operation", required=True)
        if name == "recover":
            command.add_argument("--platform-task-id", required=True)
    inspect = sub.add_parser("inspect", help="只读检查线上工作流；不会生成媒体")
    inspect.add_argument("--mode", choices=("tts", "fl-base", "fl-i2v"), required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    service = Service(Store(args.data_dir), load_config(args.config))
    name = args.command
    if name == "doctor":
        return service.doctor()
    if name == "setup":
        return service.setup(args.with_tts)
    if name == "serve":
        from thvideo.workbench import serve
        return serve(service, args.port)
    if name == "list":
        return [{"id": t["id"], "title": t["title"], "status": service.view(t)["status"]} for t in service.store.list()]
    if name == "create":
        return service.create(json.loads(args.plan.read_text(encoding="utf-8-sig")), args.plan.resolve().parent)
    if name == "show":
        return service.view(service.store.load(args.task_id))
    if name == "review":
        return service.review(args.task_id, args.stage)
    if name == "approve":
        return service.approve(args.task_id, args.stage, args.digest, args.by)
    if name == "use-audio":
        return service.use_input_audio(args.task_id)
    if name == "segment":
        cuts = json.loads(args.cuts.read_text(encoding="utf-8-sig")) if args.cuts else {}
        return service.segment(args.task_id, cuts.get("texts"), cuts.get("boundaries_seconds"))
    if name == "set-prompt":
        return service.set_prompt(args.task_id, args.index, args.file.read_text(encoding="utf-8-sig"), args.mode)
    if name == "preview":
        return service.preview(args.task_id, args.index)
    if name == "submit":
        return service.submit(args.task_id, args.digest, args.index, args.approved_paid_run, args.calibration)
    if name == "retry":
        return service.retry(args.task_id, args.index, args.reason)
    if name == "poll":
        return service.poll(args.task_id, args.operation)
    if name == "recover":
        return service.recover(args.task_id, args.operation, args.platform_task_id)
    if name == "assemble":
        return service.assemble(args.task_id)
    if name == "verify-portrait":
        return service.verify_portrait(args.task_id, args.config, args.index)
    if name == "inspect":
        return service.provider.inspect(args.mode)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        result = main()
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (UserError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
