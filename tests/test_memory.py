"""记忆库：记什么、忘什么、久远的事还剩多少。

这些测试钉的是"人味"那几条约定，不是实现细节：
- 有分量的事才记，寒暄不记
- 12 小时内记得原话，之后只剩概括
- 时间永远是模糊说法，没有"49 分钟前"
- 同一件事连发不重复记
"""
import tempfile
import unittest
from pathlib import Path

from tide import memory as mem_mod
from tide.core import TideCore
from tide.memory import Memory, phrase_age, phrase_idle

CONFIG = Path(__file__).resolve().parent.parent / "config"
T0 = 1_800_000_000.0


class TestWhatSheRemembers(unittest.TestCase):
    def setUp(self):
        self.m = Memory()

    def test_only_memorable_things_are_recorded(self):
        self.assertIsNone(self.m.add(T0, "said", "嗯", tags=[]))
        self.assertIsNone(self.m.add(T0, "said", "在吗", tags=["neutral"]))
        self.assertIsNotNone(self.m.add(T0, "said", "你真笨", tags=["hostile"]))

    def test_quote_fades_after_half_a_day(self):
        self.m.add(T0, "said", "你真笨", tags=["hostile"])
        fresh = self.m.digest(T0 + 2 * 3600)[0]
        old = self.m.digest(T0 + 30 * 3600)[0]
        self.assertEqual(fresh["quote"], "你真笨")
        self.assertIsNone(old["quote"])
        self.assertEqual(old["verb"], "凶了一句")

    def test_repeating_the_same_line_does_not_pile_up(self):
        self.m.add(T0, "said", "你真笨", tags=["hostile"])
        self.m.add(T0 + 5, "said", "你真笨", tags=["hostile"])
        self.m.add(T0 + 9, "said", "你真笨", tags=["hostile"])
        self.assertEqual(len(self.m.items), 1)

    def test_heavier_memories_survive_the_cut(self):
        m = Memory(max_items=3)
        m.add(T0, "said", "你真笨", tags=["hostile"])          # w=1 最重
        for i in range(4):
            m.add(T0 + 100 + i, "said", "在吗", tags=["praise"])  # w=3
        tags = {it["tag"] for it in m.items}
        self.assertIn("hostile", tags)


class TestBlurredTime(unittest.TestCase):
    def test_age_is_never_exact(self):
        self.assertEqual(phrase_age(T0, T0 + 30), "刚刚")
        self.assertEqual(phrase_age(T0, T0 + 600), "刚才")
        self.assertEqual(phrase_age(T0, T0 + 3 * 3600), "今天早些")
        self.assertEqual(phrase_age(T0, T0 + 6 * 3600), "今天")
        self.assertEqual(phrase_age(T0, T0 + 26 * 3600), "昨天")
        self.assertEqual(phrase_age(T0, T0 + 60 * 3600), "前几天")
        self.assertEqual(phrase_age(T0, T0 + 600 * 3600), "前不久")

    def test_talk_length_is_fuzzy_not_counted(self):
        self.assertEqual(phrase_idle(None), "还没说过话")
        self.assertEqual(phrase_idle(1), "刚说完话")
        self.assertEqual(phrase_idle(10), "聊了一会儿")
        self.assertEqual(phrase_idle(120), "隔了一阵没说话")
        self.assertEqual(phrase_idle(2000), "一两天没说话了")

    def test_no_number_with_minutes_appears(self):
        for m in (1, 10, 40, 120, 400, 1000, 3000, 9000):
            self.assertNotIn("分钟", phrase_idle(m))


class TestMemoryInCore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = TideCore.from_config(CONFIG, state_path=Path(self.tmp.name) / "state.json")
        self.core.reset()

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_carries_memory_and_talk_phrase(self):
        self.core.observe("你真笨", at=T0)
        snap = self.core.snapshot(at=T0 + 60)
        self.assertEqual(snap["memory"]["last_neg"]["verb"], "凶了一句")
        self.assertIn("phrase", snap["memory"]["talk"])
        self.assertTrue(snap["memory"]["digest"])

    def test_praise_is_also_remembered_as_a_cause(self):
        self.core.observe("你今天好可爱呀", at=T0)
        snap = self.core.snapshot(at=T0 + 60)
        self.assertIsNotNone(snap["memory"]["last_pos"])
        self.assertEqual(snap["memory"]["last_pos"]["verb"], "夸了一句")

    def test_memory_survives_reload(self):
        self.core.observe("你真笨", at=T0)
        again = TideCore.from_config(CONFIG, state_path=Path(self.tmp.name) / "state.json")
        self.assertTrue(any("你真笨" == it.get("text") for it in again.memory.items))

    def test_reset_clears_memory(self):
        self.core.observe("你真笨", at=T0)
        self.core.reset()
        self.assertEqual(self.core.memory.items, [])


if __name__ == "__main__":
    unittest.main()