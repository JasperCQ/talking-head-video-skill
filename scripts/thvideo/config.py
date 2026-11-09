import json
import os
from pathlib import Path


class UserError(Exception):
    """An actionable failure safe to display without a traceback."""


MODES = ("tts", "fl-base", "fl-i2v")
CONFIG_PATH = Path.home() / ".config/talking-head-video/config.json"
DATA_PATH = Path.home() / ".local/share/talking-head-video"
DEFAULT_WORKFLOWS = json.loads(
    (Path(__file__).resolve().parents[2] / "references/default-workflows.json").read_text(encoding="utf-8"))


def load_config(path=None):
    path = Path(path or os.environ.get("TALKING_HEAD_CONFIG", CONFIG_PATH)).expanduser()
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(config, dict) or not isinstance(config.get("workflows", {}), dict):
        raise UserError("配置必须为 JSON 对象，workflows 必须为对象。")
    if not isinstance(config.get("portrait_evidence", {}), dict):
        raise UserError("portrait_evidence 必须为对象。")
    workflows = config.setdefault("workflows", {})
    for mode in MODES:
        value = os.environ.get("TALKING_HEAD_WORKFLOW_" + mode.upper().replace("-", "_"))
        workflows[mode] = (str(value or "").strip()
                           or str(workflows.get(mode) or "").strip()
                           or DEFAULT_WORKFLOWS[mode])
    return config


def workflow_id(config, mode):
    value = str(config.get("workflows", {}).get(mode) or "")
    if mode not in MODES or not value.isascii() or not value.isdigit():
        raise UserError(f"内部生成配置 workflows.{mode} 无效，请由 Agent 检查配置或恢复内置默认值。")
    return value


def api_key():
    value = os.environ.get("RUNNINGHUB_API_KEY", "").strip()
    if not value:
        raise UserError("请在启动进程中设置 RUNNINGHUB_API_KEY；密钥不会写入任务或配置。")
    return value
