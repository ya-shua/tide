"""宿主桥：通知一次、等回执、成功才记账、失败不记账。

这一套的要点是「不是轮询」：跨过门槛只通知一次，回执回来才闭麦；
报成功但其实没发出去，她会以为你在冷落她 —— 所以失败必须如实上报。
"""
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tide.core import TideCore  # noqa: E402

CFG_DIR = ROOT / "config"
T0 = time.mktime(time.strptime("2026-03-01 14:00", "%Y-%m-%d %H:%M"))
H = 3600.0


class BridgeBase(unittest.TestCase):
    def setUp(self):
        tmp = ROOT / ".test_tmp"
        tmp.mkdir(exist_ok=True)
        self.state_path = tmp / ("state-" + uuid.uuid4().hex + ".json")
        self.core = TideCore.from_config(CFG_DIR, state_path=self.state_path)
        # 测试里不真的打网络：把宿主当成「一直通」
        self.core.bridge.url = "http://127.0.0.1:9"
        self.core.bridge.token = "t"
        self.core.bridge.enabled = True
        self.core.pending_proactive = None
        self.core.notify_fail_at = 0.0
        self.core.last_tick = T0

    def tearDown(self):
        if self.state_path.exists():
            self.state_path.unlink()

    def idle_hours(self, h: float):
        self.core.needs.last_seen = T0 - h * H
        self.core.needs.longing_at = T0 - h * H
        self.core.needs.longing_value = 0.0
        self.core.needs.hold_until = 0.0
        self.core.last_tick = T0

    def patch_notify(self, ok=True, error=""):
        return mock.patch.object(
            self.core.bridge, "notify",
            return_value={"ok": ok, "accepted": True} if ok else {"ok": False, "error": error},
        )


class TestNotify(BridgeBase):
    def test_crossing_notifies_host_once(self):
        self.idle_hours(10)
        with self.patch_notify() as notify:
            self.core._maybe_notify_host(T0)
            self.assertEqual(notify.call_count, 1)
            self.assertIsNotNone(self.core.pending_proactive)
            # 还在等回执：再 tick 也不能再通知
            self.core._maybe_notify_host(T0 + 60)
            self.assertEqual(notify.call_count, 1)

    def test_notifies_nothing_when_not_crossed(self):
        self.core.last_tick = T0
        with self.patch_notify() as notify:
            self.core._maybe_notify_host(T0)
            notify.assert_not_called()

    def test_quiet_hours_block(self):
        self.idle_hours(10)
        t = time.mktime(time.strptime("2026-03-02 03:00", "%Y-%m-%d %H:%M"))
        self.core.last_tick = t
        with self.patch_notify() as notify:
            self.core._maybe_notify_host(t)
            notify.assert_not_called()

    def test_host_down_backs_off(self):
        self.idle_hours(10)
        with self.patch_notify(ok=False, error="连不上") as notify:
            self.core._maybe_notify_host(T0)
            self.assertIsNone(self.core.pending_proactive)
            self.assertGreater(self.core.notify_fail_at, 0)
            # 退避窗口内不再敲
            self.core._maybe_notify_host(T0 + 60)
            self.assertEqual(notify.call_count, 1)


class TestReport(BridgeBase):
    def test_sent_true_counts_and_closes(self):
        self.idle_hours(10)
        with self.patch_notify():
            self.core._maybe_notify_host(T0)
        ev = self.core.pending_proactive["event_id"]
        out = self.core.report_proactive(ev, True, text="在吗", at=T0 + 5)
        self.assertTrue(out["sent"])
        self.assertEqual(self.core.pending_proactive, None)
        self.assertAlmostEqual(self.core.last_proactive_at, T0 + 5, delta=0.1)
        self.assertEqual(self.core._wakes_today(T0 + 5), 1)

    def test_sent_false_does_not_count(self):
        self.idle_hours(10)
        with self.patch_notify():
            self.core._maybe_notify_host(T0)
        ev = self.core.pending_proactive["event_id"]
        before = self.core.last_proactive_at
        out = self.core.report_proactive(ev, False, error="QQ 断线", at=T0 + 5)
        self.assertFalse(out["sent"])
        self.assertEqual(self.core.last_proactive_at, before)
        self.assertEqual(self.core._wakes_today(T0 + 5), 0)
        self.assertGreater(self.core.notify_fail_at, 0)

    def test_wrong_event_ignored(self):
        self.idle_hours(10)
        with self.patch_notify():
            self.core._maybe_notify_host(T0)
        out = self.core.report_proactive("别的号", True, text="x", at=T0 + 5)
        self.assertFalse(out["ok"])

    def test_cooldown_after_sent(self):
        self.idle_hours(10)
        with self.patch_notify() as notify:
            self.core._maybe_notify_host(T0)
            ev = self.core.pending_proactive["event_id"]
            self.core.report_proactive(ev, True, text="在吗", at=T0 + 5)
            # 刚说完：冷却里，不该再敲
            self.core._maybe_notify_host(T0 + 6 * 60)
            self.assertEqual(notify.call_count, 1)


if __name__ == "__main__":
    unittest.main()