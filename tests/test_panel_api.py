"""面板 API：海螺靠这三个口子接 Tide，别哪天改坏了没人发现。"""
import json
import sys
import threading
import time
import unittest
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tide.core import TideCore  # noqa: E402
from tide.panel import make_handler  # noqa: E402

CFG_DIR = ROOT / "config"
T0 = time.mktime(time.strptime("2026-03-01 14:00", "%Y-%m-%d %H:%M"))


class PanelApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = ROOT / ".test_tmp"
        tmp.mkdir(exist_ok=True)
        cls.state = tmp / ("api-" + uuid.uuid4().hex + ".json")
        cls.core = TideCore.from_config(CFG_DIR, state_path=cls.state)
        cls.core.last_tick = T0
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.core))
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.state.unlink(missing_ok=True)

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, data):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_health(self):
        self.assertTrue(self.get("/api/health")["ok"])

    def test_observe_then_state(self):
        self.post("/api/observe", {"text": "在吗，今天过得怎么样", "speaker": "other"})
        st = self.get("/api/state")["snapshot"]
        self.assertIsInstance(st["feelings"], str)
        self.assertTrue(st["feelings"])
        self.assertEqual(sum(st["emotion"]["accounts"].values()), 100)

    def test_person_is_separate(self):
        self.post("/api/observe", {"text": "群里随便说一句", "person": "group:123"})
        st = self.get("/api/state?person=group:123")["snapshot"]
        self.assertEqual(st["person"], "group:123")

    def test_woke_records(self):
        self.post("/api/woke", {})
        st = self.get("/api/state")["snapshot"]
        self.assertGreaterEqual(st["wake"]["count_today"], 1)

    def test_initiated_starts_hold(self):
        now = time.time()
        self.core.needs.last_seen = now - 6 * 3600
        self.core.needs.longing_at = now - 6 * 3600
        self.core.needs.longing_value = 0.0
        self.core.needs.hold_until = 0.0
        self.post("/api/observe", {"text": "你在干嘛呀", "speaker": "self", "initiated": True})
        st = self.get("/api/state")["snapshot"]
        self.assertGreater(st["wake"]["needs"]["longing"], 20)
        self.assertGreater(self.core.needs.hold_until, now)   # 缓解期开始了


if __name__ == "__main__":
    unittest.main()