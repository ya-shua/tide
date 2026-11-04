"""话题三态：进行中 → 收尾 → 已结束，以及"她在等回答"卡住收尾。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tide.topic import Topic  # noqa: E402

CFG = {
    "quiet_factor": 0.2,
    "topic": {
        "closing_phrases": ["晚安", "先这样", "去忙了"],
        "explicit_end": ["不聊了", "睡了"],
        "question_tails": ["？", "?", "吗", "呢"],
        "idle_to_closed_min": 20,
    },
    "neglect": {
        "active_per_hour": 18,
        "winding_per_hour": 6,
        "question_multiplier": 1.8,
        "affinity_threshold": 70,
        "affinity_factor": 1.3,
        "cap": 80,
    },
}

T0 = 1_700_000_000.0


class TestTopicLifecycle(unittest.TestCase):
    def setUp(self):
        self.tp = Topic(CFG)

    def test_other_message_opens_topic(self):
        self.tp.on_other("我今天上班好累", T0)
        self.assertEqual(self.tp.state, "active")

    def test_closing_phrase_winds_down(self):
        self.tp.on_other("我去忙了，回头聊", T0)
        self.assertEqual(self.tp.state, "winding_down")

    def test_explicit_end_closes(self):
        self.tp.on_other("不聊了", T0)
        self.assertEqual(self.tp.state, "closed")

    def test_her_statement_winds_down(self):
        self.tp.on_other("今天好热", T0)
        self.tp.on_self("是呀，热死了", T0 + 10)
        self.assertEqual(self.tp.state, "winding_down")
        self.assertFalse(self.tp.her_last_asked)

    def test_her_question_keeps_topic_open(self):
        self.tp.on_other("在忙", T0)
        self.tp.on_self("你忙完啦？", T0 + 10)
        self.assertEqual(self.tp.state, "active")
        self.assertTrue(self.tp.her_last_asked)

    def test_idle_20min_closes_quiet_topic(self):
        self.tp.on_other("今天好热", T0)
        self.tp.on_self("是呀，热死了", T0 + 10)
        self.tp.maybe_close(T0 + 10 + 20 * 60)
        self.assertEqual(self.tp.state, "closed")

    def test_question_blocks_closing(self):
        """她在等回答的时候，20 分钟不算结束 —— 这正是冷落。"""
        self.tp.on_other("在忙", T0)
        self.tp.on_self("你忙完啦？", T0 + 10)
        self.tp.maybe_close(T0 + 10 + 60 * 60)
        self.assertEqual(self.tp.state, "active")
        self.assertTrue(self.tp.her_last_asked)

    def test_new_message_reopens(self):
        self.tp.on_other("不聊了", T0)
        self.tp.on_other("对了还有件事", T0 + 60)
        self.assertEqual(self.tp.state, "active")


if __name__ == "__main__":
    unittest.main()