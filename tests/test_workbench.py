"""Real HTTP reads against isolated task data; no provider or paid operations."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from thvideo.service import Service
from thvideo.store import Store, fingerprint
from thvideo.workbench import WorkbenchServer


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Store(self.root)
        self.service = Service(self.store, {})
        self.task = self.store.create("<script>私人任务</script>", {"script": "这是审核文案。"}, {})
        inputs = self.store.directory(self.task["id"]) / "inputs"
        inputs.mkdir()
        audio = inputs / "配音 space.wav"
        audio.write_bytes(b"RIFF" + bytes(range(256)))
        self.task["assets"]["audio"] = fingerprint(audio)
        self.store.save(self.task)
        self.server = WorkbenchServer(self.service)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.stop_server, thread)

    def stop_server(self, thread):
        self.server.shutdown()
        self.server.server_close()
        thread.join(timeout=3)

    def get(self, path, **headers):
        request = urllib.request.Request(self.server.url + path, headers=headers)
        return urllib.request.urlopen(request, timeout=5)

    def detail(self):
        with self.get("/api/tasks/" + self.task["id"]) as response:
            return json.load(response)

    def test_reads_do_not_submit_mutate_or_disclose_key(self):
        task_file = self.store.directory(self.task["id"]) / "task.json"
        before = task_file.read_bytes()
        with patch.dict("os.environ", {"RUNNINGHUB_API_KEY": "do-not-disclose-key"}), \
                patch.object(self.service.provider, "submit", side_effect=AssertionError("No submit")), \
                patch.object(self.service.provider, "inspect", side_effect=AssertionError("No cloud read")):
            for path in ("/", "/app.js", "/style.css", "/api/tasks", "/api/doctor", "/api/tasks/" + self.task["id"]):
                with self.get(path) as response:
                    body = response.read()
                    self.assertNotIn(b"do-not-disclose-key", body)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(before, task_file.read_bytes())
        request = urllib.request.Request(self.server.url + "/api/tasks", data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 405)
        self.assertEqual(before, task_file.read_bytes())

    def test_media_is_registered_only_and_supports_seeking(self):
        detail = self.detail()
        audio = self.task["assets"]["audio"]["path"]
        url = detail["media"][audio]
        with self.get(url, Range="bytes=4-13") as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), bytes(range(10)))
            self.assertEqual(response.headers["Content-Range"], "bytes 4-13/260")
        with self.get(url, Range="bytes=-3") as response:
            self.assertEqual(response.read(), bytes([253, 254, 255]))
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get(url, Range="bytes=999-")
        self.assertEqual(error.exception.code, 416)
        hidden = self.store.directory(self.task["id"]) / "private.wav"
        hidden.write_bytes(b"not-registered")
        outside = self.root / "outside-task.wav"
        outside.write_bytes(b"outside-task-directory")
        task = self.store.load(self.task["id"])
        task["assets"]["voice"] = fingerprint(outside)
        self.store.save(task)
        self.assertNotIn(str(outside), self.detail()["media"])
        for relative in ("task.json", "private.wav", "inputs/../../../../etc/passwd"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.get("/media/" + self.task["id"] + "/" + relative)
            self.assertEqual(error.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.get("/api/tasks", Host="untrusted.example")
        self.assertEqual(error.exception.code, 403)

    def test_current_review_is_revalidated_when_content_changes(self):
        # Complete the required asset names without needing generation or FFmpeg.
        audio = self.task["assets"]["audio"]
        self.task["assets"].update({key: audio.copy() for key in ("presenter", "scene", "product")})
        self.store.save(self.task)
        review = self.service.review(self.task["id"], "content")
        self.service.approve(self.task["id"], "content", review["digest"], "test")
        self.assertTrue(self.detail()["reviews_current"]["content"])
        task = self.store.load(self.task["id"])
        task["plan"]["script"] = "已经修改的文案。"
        self.store.save(task)
        detail = self.detail()
        self.assertFalse(detail["reviews_current"]["content"])
        self.assertEqual(detail["task"]["status"], "content_review")


if __name__ == "__main__":
    unittest.main()
