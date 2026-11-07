"""情绪：半衰期、增量上限、守衡（总和恒为 100）、转移。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tide.emotion import Emotion  # noqa: E402


def fresh(**levels):
    """直接摆一个状态：默认把剩下的都放平静，保证总和 1.0。"""
    e = Emotion()
    rest = 1.0 - sum(levels.values())
    e.levels = dict(levels)
    if rest > 1e-9:
        e.levels["calm"] = rest
    return e


class TestEmotionDecay(unittest.TestCase):
    def test_half_life_angry_25min(self):
        e = fresh(angry=0.4)
        e.decay(25 * 60)
        self.assertAlmostEqual(e.levels["angry"], 0.2, places=3)

    def test_two_half_lives_quarter(self):
        e = fresh(sad=0.8)
        e.decay(2 * 240 * 60)  # sad 半衰期 4h，两个半衰期
        self.assertAlmostEqual(e.levels["sad"], 0.2, places=3)

    def test_max_delta_per_event(self):
        e = Emotion(max_delta=0.4)
        e.add("angry", 0.9)
        self.assertAlmostEqual(e.levels["angry"], 0.4, places=3)

    def test_negative_delta_cools_down(self):
        e = fresh(sad=0.5)
        e.add("sad", -0.2)  # 道歉
        self.assertAlmostEqual(e.levels["sad"], 0.3, places=3)

    def test_returns_to_calm(self):
        e = Emotion(calm_threshold=0.12)
        e.add("joyful", 0.35)
        self.assertEqual(e.label, "joyful")
        e.decay(60 * 60 * 6)  # 6 个半衰期
        self.assertEqual(e.label, "calm")
        self.assertLess(e.peak, 0.12)

    def test_pad_returns_to_baseline(self):
        e = Emotion()
        base = e.pad()
        e.add("joyful", 0.35)
        self.assertGreater(e.pad()[0], base[0])
        e.decay(60 * 60 * 24)
        self.assertAlmostEqual(e.pad()[0], base[0], places=2)


class TestConservation(unittest.TestCase):
    """情绪不会消失，只会转移：总和永远是 1.0。"""

    def test_add_takes_from_others(self):
        e = Emotion()
        e.add("angry", 0.3)
        self.assertAlmostEqual(sum(e.levels.values()), 1.0, places=6)
        self.assertAlmostEqual(e.levels["calm"], 0.7, places=6)

    def test_decay_keeps_total(self):
        e = fresh(angry=0.5)
        e.decay(3 * 60 * 60)
        self.assertAlmostEqual(sum(e.levels.values()), 1.0, places=6)

    def test_angry_turns_into_guilty(self):
        e = fresh(angry=0.6)
        e.decay(25 * 60)          # 一个半衰期，掉 0.3
        self.assertGreater(e.levels.get("guilty", 0.0), 0.05)
        self.assertGreater(e.levels.get("sad", 0.0), 0.02)
        self.assertAlmostEqual(sum(e.levels.values()), 1.0, places=6)

    def test_accounts_sum_to_100(self):
        e = Emotion()
        e.add("angry", 0.4)
        e.add("joyful", 0.2)
        acc = e.accounts()
        self.assertEqual(sum(acc.values()), 100)
        self.assertGreater(acc["anger"], 0)
        self.assertGreater(acc["joy"], 0)

    def test_add_does_not_invent_value(self):
        e = fresh(worried=0.2)
        before = sum(e.levels.values())
        e.add("sad", 0.4)
        self.assertAlmostEqual(sum(e.levels.values()), before, places=6)
        self.assertLess(e.levels["calm"], 0.8)   # 先挤平静

    def test_old_state_is_migrated(self):
        old = {"intensity": {"angry": 0.2, "sad": 0.07}}   # 旧版总和 0.27
        e = Emotion.from_dict(old)
        self.assertAlmostEqual(sum(e.levels.values()), 1.0, places=6)
        self.assertAlmostEqual(e.levels["calm"], 0.73, places=6)


if __name__ == "__main__":
    unittest.main()