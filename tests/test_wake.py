"""叫醒 / 缓解期 / 余温 / 自动免打扰：都要能算，也要守衡。"""
import sys
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tide.core import TideCore  # noqa: E402

CFG_DIR = ROOT / "config"
T0 = time.mktime(time.strptime("2026-03-01 14:00", "%Y-%m-%d %H:%M"))
H = 3600.0


class WakeBase(unittest.TestCase):
    def setUp(self):
        tmp = ROOT / ".test_tmp"
        tmp.mkdir(exist_ok=True)
        self.state_path = tmp / ("state-" + uuid.uuid4().hex + ".json")
        self.core = TideCore.from_config(CFG_DIR, state_path=self.state_path)
        self.core.last_tick = T0

    def tearDown(self):
        if self.state_path.exists():
            self.state_path.unlink()

    def idle_hours(self, h: float):
        self.core.needs.last_seen = T0 - h * H
        self.core.last_tick = T0

    def longing(self, t):
        return self.core.needs.longing(t, self.core._bond(self.core.default_person).affinity)


class TestHoldPeriod(WakeBase):
    def test_she_speaks_longing_freezes(self):
        self.idle_hours(8)
        before = self.longing(T0)
        self.assertGreater(before, 55)
        self.core.observe(text="在忙吗", speaker="self", at=T0, initiated=True)
        after = self.longing(T0)
        self.assertAlmostEqual(after, before, delta=1.0)   # 不降
        self.assertAlmostEqual(self.longing(T0 + 1 * H), after, delta=1.0)  # 冻结
        self.assertGreater(self.longing(T0 + 3 * H), after)                 # 过了缓解期再涨

    def test_reply_leaves_residual(self):
        self.idle_hours(8)
        self.core.observe(text="在忙吗", speaker="self", at=T0, initiated=True)
        self.core.observe(text="刚在忙", speaker="other", at=T0 + 60)
        self.assertAlmostEqual(self.longing(T0 + 120), 12, delta=2.0)
        # 余温窗口过了，从 12 接着往上爬
        self.assertGreater(self.longing(T0 + 3 * H), 12)

    def test_hold_is_configurable(self):
        self.core.needs.hold_min = 10
        self.idle_hours(8)
        self.core.observe(text="在吗", speaker="self", at=T0, initiated=True)
        self.assertGreater(self.longing(T0 + 30 * 60), 40)


class TestLateReplyGrievance(WakeBase):
    def test_long_wait_raises_grievance_on_reply(self):
        self.idle_hours(8)
        self.core.observe(text="在忙吗", speaker="self", at=T0, initiated=True)
        g0 = self.core._bond(self.core.default_person).grievance
        self.core.observe(text="来了", speaker="other", at=T0 + 3 * H)
        g1 = self.core._bond(self.core.default_person).grievance
        self.assertGreater(g1, g0 + 10)     # 委屈在回复那一刻才涨

    def test_no_spike_without_waiting(self):
        self.idle_hours(8)
        g0 = self.core._bond(self.core.default_person).grievance
        self.core.observe(text="随便聊聊", speaker="other", at=T0)
        g1 = self.core._bond(self.core.default_person).grievance
        self.assertAlmostEqual(g1, g0, delta=1.0)


class TestWakeDecision(WakeBase):
    def test_threshold_not_reached(self):
        self.idle_hours(0.5)
        res = self.core.should_wake(T0)
        self.assertFalse(res["wake"])

    def test_longing_wakes(self):
        self.idle_hours(12)
        self.core.last_wake_at = 0
        self.core.wake_marks = []
        res = self.core.should_wake(T0)
        self.assertTrue(res["wake"], res)
        self.assertIn("想", res["why"])

    def test_quiet_hours_hold_back(self):
        self.idle_hours(12)
        night = time.mktime(time.strptime("2026-03-02 03:00", "%Y-%m-%d %H:%M"))
        self.core.last_tick = night - 60
        self.assertFalse(self.core.should_wake(night)["wake"])

    def test_cooldown_modes(self):
        self.idle_hours(12)
        for mode, expect in (("dec", 70), ("fixed", 90), ("inc", 110)):
            self.core.wake_cfg["cooldown_mode"] = mode
            self.core.wake_marks = [T0 - 2 * H, T0 - H]   # 今天已经叫醒 2 次
            self.core.last_wake_at = T0 - 10
            res = self.core.should_wake(T0)
            self.assertFalse(res["wake"])
            self.assertAlmostEqual(res["cooldown_min"], expect, delta=0.1)

    def test_max_wakes_caps(self):
        self.idle_hours(12)
        self.core.wake_cfg["max_wakes"] = 2
        self.core.wake_marks = [T0 - 2 * H, T0 - H]
        res = self.core.should_wake(T0)
        self.assertFalse(res["wake"])
        self.assertIn("忍", res["why"])

    def test_zero_means_unlimited(self):
        self.idle_hours(30)
        self.core.wake_cfg["max_wakes"] = 0
        self.core.wake_marks = [T0 - 2 * H] * 6
        self.core.last_wake_at = 0
        self.assertTrue(self.core.should_wake(T0)["wake"])

    def test_manual_dnd_blocks_wake(self):
        self.idle_hours(12)
        self.core.set_dnd(True)
        res = self.core.should_wake(T0)
        self.assertFalse(res["wake"])
        self.assertEqual(res["dnd"], "manual")

    def test_auto_dnd_after_three_silences(self):
        self.core.observe(text="在吗", speaker="self", at=T0, initiated=True)
        self.core.observe(text="在吗？", speaker="self", at=T0 + 60, initiated=True)
        self.assertEqual(self.core.dnd, "off")
        self.core.observe(text="你忙吧", speaker="self", at=T0 + 120, initiated=True)
        self.assertEqual(self.core.dnd, "auto")


class TestConservationUnderEvents(WakeBase):
    def test_total_stays_100(self):
        self.idle_hours(8)
        self.core.observe(text="你真笨", speaker="other", at=T0)
        self.core.tick(T0 + 3 * H)
        self.core.observe(text="在忙吗", speaker="self", at=T0 + 3 * H, initiated=True)
        self.assertAlmostEqual(sum(self.core.emotion.levels.values()), 1.0, places=6)
        self.assertEqual(sum(self.core.emotion.accounts().values()), 100)

    def test_feelings_read_like_a_person(self):
        self.idle_hours(8)
        self.core.observe(text="你真笨", speaker="other", at=T0)
        text = self.core._feelings(T0, self.core.default_person)
        self.assertTrue(text.startswith("心里"))
        self.assertNotIn("强度", text)


if __name__ == "__main__":
    unittest.main()