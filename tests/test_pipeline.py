"""Offline regression tests: fake network, real WAV/FFmpeg media operations."""
import base64
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from thvideo import media
from thvideo.config import UserError, load_config
from thvideo.provider import CONTRACTS, RunningHub, node_info, validate_graph, validate_prompt
from thvideo.service import Service
from thvideo.store import Store, fingerprint


TEXTS = ["今天介绍这个杯子。", "出门带上它很方便。"]


def prompt(text, mode="fl-base"):
    references = "<Picture 1> presenter; <Picture 2> scene; <Picture 3> product." if mode == "fl-base" else "Continue the first_frame."
    return (f"subject_definitions:\n(S1) Presenter. {references}\nsummary:\nStable talking head.\n"
            "retention_analysis:\nOne clear demonstration.\ndetailed_description:\n[Shot 1] Fixed camera, natural gestures.\n"
            f"overall_soundscape:\nOnly (S1) speaks from drive_audio: <d>[Chinese]{text}</d>\nnon_diegetic_music:\nNone.")


class FakeHub:
    def __init__(self, audio, clip):
        self.audio, self.clip = audio, clip
        self.created = []
        self.fail_submit = False
        self.fail_download = False
        self.status = "succeeded"

    def inspect(self, mode):
        return {"mode": mode, "workflow_id": "123", "nodes": 20}

    def upload(self, path):
        return "openapi/" + Path(path).name

    def submit(self, operation, nodes):
        self.created.append((operation, nodes))
        if self.fail_submit:
            raise UserError("模拟：平台已接收，但响应超时。")
        return str(1000 + len(self.created))

    def poll(self, task_id):
        return {"status": self.status, "urls": ["https://example.invalid/output.mp4"]}

    def download(self, urls, directory, mode):
        if self.fail_download:
            raise UserError("模拟下载中断。")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        source = self.audio if mode == "tts" else self.clip
        target = directory / ("output" + source.suffix)
        shutil.copyfile(source, target)
        return [str(target)]


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory()
        root = Path(cls.fixtures.name)
        cls.image = root / "reference.png"
        cls.image.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII="))
        cls.audio = root / "master.wav"
        rate = 8000
        with wave.open(str(cls.audio), "wb") as out:
            out.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            out.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * i / rate))
                                               if not 2.8 < i / rate < 3.2 else 0) for i in range(rate * 6)))
        cls.clip = root / "clip.mp4"
        # Slightly shorter than the driving audio to exercise frame padding at assembly.
        media.run(["-y", "-f", "lavfi", "-i", "color=c=blue:s=90x160:r=24:d=2.75", "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.clip])

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"workflows": {"tts": "123", "fl-base": "456", "fl-i2v": "789"}}
        self.hub = FakeHub(self.audio, self.clip)
        self.service = Service(Store(self.root), self.config, self.hub)

    def create(self, recorded=False):
        assets = {k: str(self.image) for k in ("presenter", "scene", "product")}
        assets["audio" if recorded else "voice"] = str(self.audio)
        task = self.service.create({"script": "".join(TEXTS), "segments": TEXTS, "assets": assets}, self.root)
        self.task_id = task["id"]
        return task

    def approve(self, stage):
        obj = self.service.review(self.task_id, stage)
        return self.service.approve(self.task_id, stage, obj["digest"])

    def submit(self, index=None, calibration=False):
        preview = self.service.preview(self.task_id, index)
        return self.service.submit(self.task_id, preview["digest"], index, approved=True, calibration=calibration)

    def ready_segments(self):
        self.create(recorded=True)
        self.approve("content")
        self.service.use_input_audio(self.task_id)
        self.approve("audio")
        self.service.segment(self.task_id, boundaries=[3])
        self.approve("segments")

    def ready_prompt(self, index=0):
        mode = "fl-base" if index == 0 else "fl-i2v"
        self.service.set_prompt(self.task_id, index, prompt(TEXTS[index], mode))
        self.approve(f"prompt:{index}")

    def finish_clip(self, index):
        self.ready_prompt(index)
        submitted = self.submit(index, calibration=True)
        self.service.poll(self.task_id, submitted["operation_key"])
        self.approve(f"clip:{index}")
        return submitted

    def test_full_tts_to_continuation_to_final_with_real_media(self):
        self.create()
        self.approve("content")
        op = self.submit()
        self.assertEqual(self.service.poll(self.task_id, op["operation_key"])["status"], "audio_review")
        self.approve("audio")
        self.service.segment(self.task_id)  # Detect the real silence at ~3 seconds.
        self.approve("segments")
        self.finish_clip(0)
        evidence = self.service.verify_portrait(self.task_id, self.root / "config.json")
        self.assertTrue(evidence["portrait_verified"])
        self.finish_clip(1)
        operation = self.hub.created[-1][0]
        self.assertEqual(operation["mode"], "fl-i2v")
        self.assertIn("first_frame", operation["files"])
        self.assertNotIn("product", operation["files"])
        self.service.verify_portrait(self.task_id, self.root / "config.json", 1)
        final = self.service.assemble(self.task_id)
        self.assertEqual(self.service.view(self.service.store.load(self.task_id))["status"], "final_review")
        self.service.approve(self.task_id, "final", final["digest"])
        done = self.service.view(self.service.store.load(self.task_id))
        self.assertEqual(done["status"], "completed")
        self.assertEqual((done["final"]["width"], done["final"]["height"]), (1080, 1920))
        self.assertAlmostEqual(done["final"]["duration_seconds"], 6, delta=0.1)
        # Decode the end of the actual exported audio: the last spoken section remains present.
        decoded = self.root / "end.wav"
        media.run(["-y", "-i", done["final"]["path"], "-ss", "5.7", "-t", "0.2", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", decoded])
        with wave.open(str(decoded), "rb") as audio:
            samples = struct.unpack("<" + "h" * audio.getnframes(), audio.readframes(audio.getnframes()))
        self.assertGreater(len(samples), 1200)
        self.assertGreater(max(map(abs, samples)), 3000)
        self.assertEqual(len(self.hub.created), 3)

    def test_ambiguous_submit_never_recreates_and_can_recover(self):
        self.create(); self.approve("content")
        self.hub.fail_submit = True
        with self.assertRaises(UserError):
            self.submit()
        task = self.service.store.load(self.task_id)
        self.assertEqual(self.service.view(task)["status"], "needs_reconciliation")
        with self.assertRaises(UserError):
            self.submit()
        with self.assertRaises(UserError):
            self.service.retry(self.task_id, None, "网络中断")
        self.assertEqual(len(self.hub.created), 1)
        resumed = Service(Store(self.root), self.config, self.hub)
        resumed.recover(self.task_id, "tts-attempt-1", "1001")
        self.assertEqual(resumed.poll(self.task_id, "tts-attempt-1")["status"], "audio_review")

    def test_download_failure_resumes_existing_id(self):
        self.create(); self.approve("content")
        op = self.submit()
        self.hub.fail_download = True
        with self.assertRaises(UserError):
            self.service.poll(self.task_id, op["operation_key"])
        self.hub.fail_download = False
        self.assertEqual(self.service.poll(self.task_id, op["operation_key"])["status"], "audio_review")
        self.assertEqual(len(self.hub.created), 1)

    def test_paid_flag_and_stale_digest_prevent_network_submission(self):
        self.create(); self.approve("content")
        preview = self.service.preview(self.task_id)
        with self.assertRaises(UserError):
            self.service.submit(self.task_id, preview["digest"])
        self.config["workflows"]["tts"] = "999"
        with self.assertRaises(UserError):
            self.service.submit(self.task_id, preview["digest"], approved=True)
        self.assertEqual(self.hub.created, [])

    def test_changed_copied_asset_invalidates_approval(self):
        self.create(); self.approve("content")
        task = self.service.store.load(self.task_id)
        Path(task["assets"]["product"]["path"]).write_bytes(b"changed")
        with self.assertRaises(UserError):
            self.submit()
        self.assertEqual(self.hub.created, [])

    def test_retry_requires_fresh_audio_review_even_if_bytes_identical(self):
        self.create(); self.approve("content")
        op = self.submit(); self.service.poll(self.task_id, op["operation_key"])
        self.approve("audio")
        self.service.retry(self.task_id, None, "语气不合适")
        op2 = self.submit()
        self.assertEqual(op2["operation_key"], "tts-attempt-2")
        self.assertEqual(self.service.poll(self.task_id, op2["operation_key"])["status"], "audio_review")
        self.assertIn("tts-attempt-1", self.service.store.load(self.task_id)["operations"])

    def test_continuation_requires_previous_review_and_prompt_binding(self):
        self.ready_segments()
        with self.assertRaises(UserError):
            self.service.set_prompt(self.task_id, 1, prompt(TEXTS[1], "fl-i2v"))
        self.assertEqual(self.hub.created, [])

    def test_calibration_is_required_and_evidence_expires_on_workflow_change(self):
        self.ready_segments(); self.ready_prompt()
        with self.assertRaises(UserError):
            self.submit(0)
        self.assertEqual(self.hub.created, [])
        submitted = self.submit(0, calibration=True)
        self.service.poll(self.task_id, submitted["operation_key"]); self.approve("clip:0")
        self.service.verify_portrait(self.task_id, self.root / "config.json")
        self.assertTrue(self.service.doctor()["portrait_verified"]["fl-base"])
        self.config["workflows"]["fl-base"] = "999"
        self.assertFalse(self.service.doctor()["portrait_verified"]["fl-base"])

    def test_segment_limits_and_text_mismatch(self):
        self.create(recorded=True); self.approve("content")
        self.service.use_input_audio(self.task_id); self.approve("audio")
        with self.assertRaises(UserError):
            self.service.segment(self.task_id, ["different"])
        with self.assertRaises(UserError):
            self.service.segment(self.task_id, boundaries=[1])
        result = self.service.segment(self.task_id, boundaries=[3])
        self.assertEqual(len(result["object"]), 2)

    def test_lock_prevents_parallel_mutation(self):
        self.create()
        with self.service.store.lock(self.task_id):
            with self.assertRaises(UserError):
                self.approve("content")


class ContractTests(unittest.TestCase):
    def test_cli_json_is_utf8_even_with_ascii_process_default(self):
        script = Path(__file__).resolve().parents[1] / "scripts/talking_head.py"
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run([sys.executable, str(script), "--config", str(Path(temp) / "config.json"), "doctor"],
                                    env={**os.environ, "PYTHONIOENCODING": "ascii"}, capture_output=True, check=True)
            output = json.loads(result.stdout.decode("utf-8"))
            self.assertIn("本检查离线运行", output["note"])

    def test_current_query_contract_states(self):
        hub = RunningHub({})
        for status, expected in [("QUEUED", "running"), ("RUNNING", "running"), ("FAILED", "failed"), ("SUCCESS", "succeeded")]:
            with self.subTest(status=status), patch.object(hub, "_json", return_value={"taskId": "123", "status": status, "results": [{"url": "https://example.invalid/video.mp4", "outputType": "mp4"}]} ) as request:
                self.assertEqual(hub.poll("123")["status"], expected)
                request.assert_called_once_with("/openapi/v2/query", {"taskId": "123"}, include_key=False)
        with patch.object(hub, "_json", return_value={"taskId": "wrong", "status": "SUCCESS"}):
            with self.assertRaises(UserError):
                hub.poll("123")

    def test_inspection_checks_real_routing_not_unconnected_optional_inputs(self):
        for mode, contract in CONTRACTS.items():
            graph = {key: {"class_type": rule["class_type"], "inputs": {field: "value" for field in rule["fields"]}} for key, rule in contract["nodes"].items()}
            for edge in contract["links"]:
                graph[edge["target"]]["inputs"][edge["field"]] = [edge["source"], edge["slot"]]
            if mode != "tts":
                graph["76"]["inputs"]["task_type"] = "Ref2VA" if mode == "fl-base" else "I2VA"
                graph["76"]["inputs"].update(audio_mode="remix_source", audio_denoise_strength=0)
                self.assertNotIn("last_frame", graph["76"]["inputs"])
            response = {"code": 0, "data": {"prompt": json.dumps(graph)}}
            self.assertEqual(validate_graph(response, mode), graph)
            if mode != "tts":
                graph["76"]["inputs"]["ref_audios.ref_audio_0"] = ["999", 0]
                with self.assertRaises(UserError):
                    validate_graph(graph, mode)
                del graph["76"]["inputs"]["ref_audios.ref_audio_0"]
            edge = contract["links"][0]
            graph[edge["target"]]["inputs"][edge["field"]] = ["999", 0]
            with self.assertRaises(UserError):
                validate_graph(graph, mode)

    def test_prompt_rejects_invented_audio_and_continuation_picture_tags(self):
        validate_prompt(prompt(TEXTS[0]), TEXTS[0], "fl-base")
        for bad, mode in [(prompt(TEXTS[0]) + " <Audio 1>", "fl-base"), (prompt(TEXTS[0]), "fl-i2v"), (prompt(TEXTS[0]).replace(TEXTS[0], "改词"), "fl-base")]:
            with self.assertRaises(UserError):
                validate_prompt(bad, TEXTS[0], mode)

    def test_all_workflow_environment_overrides_use_same_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text('{"workflows":{"tts":"1","fl-base":"2","fl-i2v":"3"}}')
            with patch.dict(os.environ, {"TALKING_HEAD_WORKFLOW_TTS": "11", "TALKING_HEAD_WORKFLOW_FL_BASE": "22", "TALKING_HEAD_WORKFLOW_FL_I2V": "33"}):
                self.assertEqual(load_config(path)["workflows"], {"tts": "11", "fl-base": "22", "fl-i2v": "33"})


if __name__ == "__main__":
    unittest.main()
