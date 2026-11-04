"""无聊的解法不止一种：刷视频、听歌、出去走走、翻聊天记录、找人聊两句。"""
import tempfile
import unittest
from pathlib import Path

from tide import inner_voice
from tide.core import TideCore
from tide.needs import Needs

CONFIG = Path(__file__).resolve().parent.parent / "config"


class TestBoredomOutlets(unittest.TestCase):
    def test_outlets_rotate(self):
        n = Needs()
        notes = []
        for _ in range(5):
            n.boredom = 79.0          # 每次推到阈值，看她换了什么法子
            notes.extend(n._self_care())
        self.assertEqual(len(set(notes)), len(notes))  # 五个出口，五次不重样
        self.assertIn("刷了会儿视频", notes)
        self.assertIn("找人随便聊了两句", notes)

    def test_all_outlets_actually_lower_boredom(self):
        for _ in range(6):
            n = Needs()
            n.boredom = 79.0
            n._self_care()
            self.assertLess(n.boredom, 40)


class TestBoredomIsSecondary(unittest.TestCase):
    """无聊只是次要推手：真正让人主动的是想念（见 test_longing）。"""

    def test_boredom_raises_urgency_a_bit(self):
        needs = {"longing": 0, "boredom": 90, "energy": 20}
        bond = {"grievance": 0, "tone": "neutral"}
        self.assertAlmostEqual(inner_voice.urgency(needs, bond), 32.6, places=1)

    def test_bored_alone_does_not_open_her_mouth(self):
        needs = {"longing": 0, "boredom": 90, "energy": 20}
        bond = {"grievance": 0, "tone": "neutral"}
        res = inner_voice.decide(needs, bond, {"urgency_threshold": 60},
                                 quiet=False, unanswered=0,
                                 last_proactive_at=0, now=10000)
        self.assertFalse(res["should_send"])


class TestTalkingCuresBoredom(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = TideCore.from_config(CONFIG, state_path=Path(self.tmp.name) / "state.json")
        self.core.reset()

    def tearDown(self):
        self.tmp.cleanup()

    def test_chatting_lowers_boredom_more_than_one_video(self):
        self.core.advance(hours=2)
        before = self.core.needs.boredom
        self.core.observe("陪你说会儿话")
        self.assertLess(self.core.needs.boredom, before - 10)


if __name__ == "__main__":
    unittest.main()