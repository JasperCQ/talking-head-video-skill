"""Exercise a copied Skill through the CLI, without credentials or network access."""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class InstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="talking-head-install-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "独立安装 验证"
        self.skill = self.root / "技能目录" / "talking-head-video"
        self.skill.mkdir(parents=True)
        for name in ("scripts", "references", "agents"):
            shutil.copytree(ROOT / name, self.skill / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name in ("SKILL.md", "README.md", "config.example.json"):
            shutil.copyfile(ROOT / name, self.skill / name)
        self.cwd = self.root / "任务素材 space"
        self.cwd.mkdir()
        image = self.cwd / "参考图.png"
        image.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII="))
        with wave.open(str(self.cwd / "测试音频.wav"), "wb") as audio:
            audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\x00\x00" * (8000 * 6))
        self.config = self.root / "用户配置" / "config.json"
        self.data = self.root / "用户数据"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.upper().startswith(("RUNNINGHUB_", "TALKING_HEAD_", "PYTHONPATH"))}
        # Any accidental network request in a child process fails locally.
        guard = self.root / "network-guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(
            "import socket\n"
            "def deny(*args, **kwargs):\n"
            "    raise RuntimeError('Network is forbidden in installation tests')\n"
            "socket.socket.connect = deny\n"
            "socket.socket.connect_ex = deny\n", encoding="utf-8")
        self.env["PYTHONPATH"] = str(guard)

    def cli(self, *args):
        result = subprocess.run(
            [sys.executable, str(self.skill / "scripts/talking_head.py"),
             "--config", str(self.config), "--data-dir", str(self.data), *args],
            cwd=self.cwd, env=self.env, capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def create(self, audio_key):
        script = "这是安装验证。接下来检查分段。"
        plan = {"title": "隔离安装测试", "script": script,
                "segments": ["这是安装验证。", "接下来检查分段。"],
                "assets": {key: "参考图.png" for key in ("presenter", "scene", "product")}}
        plan["assets"][audio_key] = "测试音频.wav"
        (self.cwd / "任务.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return self.cli("create", "--plan", str(self.cwd / "任务.json"))["id"]

    def approve(self, task_id, stage):
        review = self.cli("review", task_id, stage)
        # Synthetic fixtures only; these approvals never apply to a user's task.
        return self.cli("approve", task_id, stage, "--digest", review["digest"], "--by", "test")

    def test_recorded_audio_reaches_video_preview_from_copied_skill(self):
        doctor = self.cli("doctor")
        self.assertFalse(doctor["api_key_present"])
        self.assertTrue(all(not mode["configured"] for mode in doctor["workflows"].values()))
        self.assertIsNotNone(doctor["ffmpeg"])
        self.config.parent.mkdir()
        self.config.write_text(json.dumps({"workflows": {"fl-base": "123", "fl-i2v": "456"}}),
                               encoding="utf-8")
        task_id = self.create("audio")
        (self.cwd / "参考图.png").unlink()
        (self.cwd / "测试音频.wav").unlink()
        self.approve(task_id, "content")
        self.cli("use-audio", task_id)
        self.approve(task_id, "audio")
        cuts = self.cwd / "切点.json"
        cuts.write_text('{"boundaries_seconds": [3.0]}', encoding="utf-8")
        segments = self.cli("segment", task_id, "--cuts", str(cuts))["object"]
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(sum(s["duration_seconds"] for s in segments), 6.0, places=2)
        self.approve(task_id, "segments")
        prompt = self.cwd / "中文提示词.txt"
        prompt.write_text(
            "subject_definitions:\n(S1) 演示人物，<Picture 1> 人物，<Picture 2> 场景，<Picture 3> 产品。\n"
            "summary:\n固定中景口播。\nretention_analysis:\n保持画面稳定。\n"
            "detailed_description:\n[Shot 1] 人物自然说话。\noverall_soundscape:\n"
            "(S1) 仅按 drive_audio 说出 <d>[Chinese]这是安装验证。</d>\n"
            "non_diegetic_music:\n无音乐。", encoding="utf-8")
        self.cli("set-prompt", task_id, "--index", "0", "--file", str(prompt))
        self.approve(task_id, "prompt:0")
        preview = self.cli("preview", task_id, "--index", "0")
        self.assertTrue(preview["configured"])
        self.assertEqual(preview["operation"]["mode"], "fl-base")
        self.assertEqual(preview["operation"]["text"], "这是安装验证。")
        self.assertEqual(set(preview["operation"]["files"]), {"presenter", "scene", "product", "audio"})
        for asset in preview["operation"]["files"].values():
            self.assertTrue(Path(asset["path"]).is_file())
        task = self.cli("show", task_id)
        self.assertEqual(task["operations"], {})
        self.assertIsNone(task["final"])
        self.assertEqual(self.cli("list")[0]["id"], task_id)

    def test_reference_voice_reaches_unconfigured_tts_preview(self):
        task_id = self.create("voice")
        self.approve(task_id, "content")
        preview = self.cli("preview", task_id)
        self.assertFalse(preview["configured"])
        self.assertEqual(preview["operation"]["mode"], "tts")
        self.assertEqual(preview["operation"]["text"], "这是安装验证。接下来检查分段。")
        self.assertEqual(set(preview["operation"]["files"]), {"voice"})
        self.assertEqual(self.cli("show", task_id)["operations"], {})
