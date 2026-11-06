"""yaml_mini 是零依赖兜底：没有 PyYAML 的机器上，规则全靠它读。

它读错一个括号，整份 rules.yaml 的列表就会变成字符串 —— 表面还能跑，
行为却全歪（冷落算错、收尾语按单个字匹配）。所以这里钉几个关键值。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tide import yaml_mini  # noqa: E402

CONFIG = ROOT / "config"


class TestRules(unittest.TestCase):
    def setUp(self):
        self.rules = yaml_mini.load_file(CONFIG / "rules.yaml")

    def test_top_level_sections_are_parsed(self):
        for key in ("needs", "topic", "neglect", "bond", "proactive", "update"):
            self.assertIsInstance(self.rules.get(key), dict, key)

    def test_multiline_flow_lists(self):
        """跨行的行内列表别被截成字符串。"""
        topic = self.rules["topic"]
        self.assertIsInstance(topic["closing_phrases"], list)
        self.assertIn("回头聊", topic["closing_phrases"])
        self.assertIn("晚点说", topic["closing_phrases"])
        self.assertEqual(topic["explicit_end"], ["不聊了", "睡了", "再见", "下了", "拜"])
        self.assertEqual(topic["idle_to_closed_min"], 20)

    def test_numbers_stay_numbers(self):
        self.assertEqual(self.rules["neglect"]["active_per_hour"], 18)
        self.assertAlmostEqual(self.rules["neglect"]["question_multiplier"], 1.8)
        self.assertEqual(self.rules["quiet_hours"], ["00:30", "07:30"])

    def test_nested_maps(self):
        tiers = self.rules["bond"]["tiers"]
        self.assertEqual(tiers["mild"], 15)
        self.assertEqual(tiers["big"], 65)

    def test_comment_is_stripped_but_quoted_hash_kept(self):
        cfg = yaml_mini.loads('a: 1   # 注释\nb: "x # y"\nc: [1, 2]  # 尾巴\n')
        self.assertEqual(cfg["a"], 1)
        self.assertEqual(cfg["b"], "x # y")
        self.assertEqual(cfg["c"], [1, 2])


if __name__ == "__main__":
    unittest.main()