"""发到 QQ：不发错人、不悄悄失败、排练和真发分开。"""
import tempfile
import unittest
from pathlib import Path

from tide.qq import QQ


class TestQQ(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / "outbox.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_disabled_never_sends(self):
        q = QQ({"enabled": False, "target": 123})
        self.assertFalse(q.available())
        self.assertFalse(q.send("你好")["ok"])

    def test_no_target_fails_loudly(self):
        q = QQ({"enabled": True, "target": 0}, outbox=self.outbox)
        res = q.send("你好")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "no target")

    def test_dry_run_only_writes_outbox(self):
        q = QQ({"enabled": True, "target": 123, "dry_run": True}, outbox=self.outbox)
        res = q.send("排练")
        self.assertTrue(res["ok"] and res["dry"])
        self.assertIn("排练", self.outbox.read_text(encoding="utf-8"))

    def test_empty_text_is_refused(self):
        q = QQ({"enabled": True, "target": 123})
        self.assertFalse(q.send("   ")["ok"])

    def test_success_comes_from_onebot_reply(self):
        q = QQ({"enabled": True, "target": 123}, outbox=self.outbox)
        q._call = lambda action, params=None, timeout=None: {
            "status": "ok", "retcode": 0, "data": {"message_id": 99}}
        res = q.send("在吗")
        self.assertTrue(res["ok"])
        self.assertEqual(res["message_id"], 99)

    def test_failure_is_reported_not_swallowed(self):
        q = QQ({"enabled": True, "target": 123}, outbox=self.outbox)
        q._call = lambda action, params=None, timeout=None: {
            "status": "failed", "retcode": 100, "message": "好友不存在"}
        res = q.send("在吗")
        self.assertFalse(res["ok"])
        self.assertEqual(res["retcode"], 100)


if __name__ == "__main__":
    unittest.main()