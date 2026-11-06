""""吃"这件事得看是问她还是喂她：问她想吃啥不算投喂。"""
import unittest
from pathlib import Path


from tide.appraisal import Appraiser
from tide.core import _load_yaml as load_yaml

CONFIG = Path(__file__).resolve().parent.parent / "config"


class TestFoodTalk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ap = Appraiser(load_yaml(CONFIG / "stimuli.yaml"))

    def test_asking_what_she_wants_is_not_feeding(self):
        r = self.ap.evaluate("晚上想吃点什么？")
        self.assertNotIn("feeding", r.tags)
        self.assertFalse(r.needs.get("hunger", 0) < 0)

    def test_actually_feeding_her_counts(self):
        r = self.ap.evaluate("来，喂你一口")
        self.assertIn("feeding", r.tags)
        self.assertLess(r.needs["hunger"], 0)

    def test_bringing_her_a_drink_counts(self):
        r = self.ap.evaluate("给你带了杯奶茶")
        self.assertIn("feeding", r.tags)

    def test_going_out_to_eat_counts(self):
        self.assertIn("feeding", self.ap.evaluate("走，吃饭去").tags)


if __name__ == "__main__":
    unittest.main()