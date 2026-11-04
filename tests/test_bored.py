"""无聊：既是一个需求，也是一种情绪；以前情绪那一头永远不亮。"""
import tempfile
import unittest
from pathlib import Path

from tide.core import TideCore

CONFIG = Path(__file__).resolve().parent.parent / "config"


class TestBoredEmotion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = TideCore.from_config(CONFIG, state_path=Path(self.tmp.name) / "state.json")
        self.core.reset()

    def tearDown(self):
        self.tmp.cleanup()

    def _wake_at_afternoon(self):
        """把她的钟拨到下午三点，免得半夜跑测试时"她睡着了、无聊不涨"。"""
        import datetime as dt
        now = dt.datetime.fromtimestamp(self.core.now())
        want = now.replace(hour=15, minute=0, second=0, microsecond=0)
        if want < now:
            want += dt.timedelta(days=1)
        self.core.offset += (want - now).total_seconds()
        self.core.tick()

    def test_being_idle_makes_her_bored(self):
        self._wake_at_afternoon()
        self.core.advance(hours=3)          # 15:00 → 18:00，全程醒着
        snap = self.core.snapshot()
        self.assertFalse(snap["clock"]["asleep"], "下午三点到六点不该在睡")
        self.assertGreater(snap["emotion"]["raw"].get("bored", 0), 0.05)

    def test_talking_means_not_bored(self):
        self._wake_at_afternoon()
        self.core.advance(hours=3)
        for _ in range(4):
            self.core.observe("在干嘛呀，跟你聊会儿")
        snap = self.core.snapshot()
        self.assertLess(snap["needs"]["boredom"], 60)

    def test_saying_bored_triggers_it(self):
        before = self.core.emotion.levels.get("bored", 0.0)
        self.core.observe("好无聊啊，没事干")
        self.assertGreater(self.core.emotion.levels.get("bored", 0.0), before)

    def test_bored_is_a_known_emotion_label(self):
        from tide.emotion import PAD_ANCHOR
        self.assertIn("bored", PAD_ANCHOR)


if __name__ == "__main__":
    unittest.main()