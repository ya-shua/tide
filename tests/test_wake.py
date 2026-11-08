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
        """模拟"已经 h 小时没人理她"：存量和时间戳一起摆好。"""
        self.core.needs.last_seen = T0 - h * H
        self.core.needs.longing_at = T0 - h * H
        self.core.needs.longing_value = 0.0
        self.core.needs.hold_until = 0.0
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

    def test_one_perfunctory_reply_barely_helps(self):
        """回一句"嗯"不能让她就不想了。"""
        self.idle_hours(8)
        before = self.longing(T0)
        self.core.observe(text="嗯", speaker="other", at=T0)
        after = self.longing(T0)
        self.assertGreater(after, before * 0.8)      # 最多降两成
        self.assertGreater(after, 40)

    def test_a_real_conversation_helps_a_lot(self):
        self.idle_hours(8)
        before = self.longing(T0)
        lines = ["今天忙完了，跟你说个事",
                 "下午那个会开得我头都大了，一直拖到六点",
                 "你呢，今天有没有好好吃饭？",
                 "晚上要不要一起看点什么？",
                 "我买了你爱吃的那个，明天带给你"]
        for i, line in enumerate(lines):
            self.core.observe(text=line, speaker="other", at=T0 + i * 30)
        after = self.longing(T0 + 5 * 30)
        self.assertLess(after, before * 0.6)         # 真聊一场，降得多

    def test_after_a_real_talk_it_stays_low_for_a_while(self):
        """聊完不是马上又涨回去：聊得越多，缓得越久（按削掉的量算，不是固定 20 分钟）。"""
        self.idle_hours(8)
        lines = ["今天忙完了，跟你说个事",
                 "下午那个会开得我头都大了，一直拖到六点",
                 "你呢，今天有没有好好吃饭？",
                 "晚上要不要一起看点什么？"]
        for i, line in enumerate(lines):
            self.core.observe(text=line, speaker="other", at=T0 + i * 30)
        low = self.longing(T0 + 5 * 60)
        self.assertGreater(self.longing(T0 + 60 * 60), low - 2.0)   # 一小时里没怎么涨
        self.assertGreater(self.longing(T0 + 8 * H), low + 10)      # 久了才慢慢回来

    def test_comfort_fades_and_longing_returns(self):
        self.idle_hours(8)
        before = self.longing(T0)
        for i, line in enumerate(["在呢在呢", "刚忙完，抱抱"]):
            self.core.observe(text=line, speaker="other", at=T0 + i * 20)
        low = self.longing(T0 + 40)
        later = self.longing(T0 + 8 * H)             # 缓过来了，想念又上来
        self.assertLess(low, before)
        self.assertGreater(later, low + 5)

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