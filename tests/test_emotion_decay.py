"""情绪半衰期、增量上限、向基线回归。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tide.emotion import Emotion  # noqa: E402


class TestEmotionDecay(unittest.TestCase):
    def test_half_life_angry_25min(self):
        e = Emotion()
        e.levels["angry"] = 0.4
        e.decay(25 * 60)
        self.assertAlmostEqual(e.levels["angry"], 0.2, places=3)

    def test_two_half_lives_quarter(self):
        e = Emotion()
        e.levels["sad"] = 0.8
        e.decay(2 * 240 * 60)  # sad 半衰期 4h，两个半衰期
        self.assertAlmostEqual(e.levels["sad"], 0.2, places=3)

    def test_max_delta_per_event(self):
        e = Emotion(max_delta=0.4)
        e.add("angry", 0.9)
        self.assertAlmostEqual(e.levels["angry"], 0.4, places=3)

    def test_negative_delta_cools_down(self):
        e = Emotion()
        e.levels["sad"] = 0.5
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
        self.assertAlmostEqual(e.pad()[0], base[0], places=3)


if __name__ == "__main__":
    unittest.main()