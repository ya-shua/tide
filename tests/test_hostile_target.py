"""「烦」得看是冲谁说的：冲她 → 委屈；他自己烦 → 她只会担心。"""
import unittest
from pathlib import Path

from tide.appraisal import Appraiser

CONFIG = Path(__file__).resolve().parent.parent / "config"


def load():
    import yaml
    cfg = yaml.safe_load((CONFIG / "stimuli.yaml").read_text(encoding="utf-8"))
    return Appraiser(cfg)


class TestWhoIsItAimedAt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ap = load()

    def test_aimed_at_her_counts(self):
        r = self.ap.evaluate("你怎么这么烦")
        self.assertIn("hostile", r.tags)
        self.assertGreaterEqual(r.bond.get("grievance", 0), 20)

    def test_her_own_bad_day_is_not_an_insult(self):
        r = self.ap.evaluate("今天好烦啊")
        self.assertNotIn("hostile", r.tags)
        self.assertLess(r.bond.get("grievance", 0), 10)   # 只是担心他，不是记仇

    def test_talking_about_a_thing_is_not_about_her(self):
        self.assertNotIn("hostile", self.ap.evaluate("这软件真烦").tags)

    def test_plain_insult_still_works(self):
        self.assertIn("hostile", self.ap.evaluate("你真笨").tags)


if __name__ == "__main__":
    unittest.main()