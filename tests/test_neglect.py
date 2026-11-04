"""冷落值：话题没收尾才算冷落；她在等回答时加倍；勿扰时段打折。

（委屈的分档地板见 test_bond_tiers.py）
"""
import sys
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tide.core import TideCore  # noqa: E402

CFG_DIR = ROOT / "config"
T_DAY = time.mktime(time.strptime("2026-03-01 14:00", "%Y-%m-%d %H:%M"))
T_NIGHT = time.mktime(time.strptime("2026-03-01 02:00", "%Y-%m-%d %H:%M"))


class TestNeglect(unittest.TestCase):
    def setUp(self):
        # 沙箱只让写工作区，状态文件放扁平目录里（子目录新建后会被 ACL 拦）
        tmp_root = ROOT / ".test_tmp"
        tmp_root.mkdir(exist_ok=True)
        self.state_path = tmp_root / ("state-" + uuid.uuid4().hex + ".json")
        self.core = TideCore.from_config(CFG_DIR, state_path=self.state_path)

    def tearDown(self):
        for p in (self.state_path, self.state_path.with_suffix(".json.tmp")):
            if p.exists():
                p.unlink()

    def test_active_topic_one_hour(self):
        self.core.observe(text="今天好热啊", at=T_DAY)
        self.core.tick(at=T_DAY + 3600)
        g = self.core.snapshot(at=T_DAY + 3600)["bond"]["grievance"]
        self.assertAlmostEqual(g, 18.0, delta=0.6)

    def test_winding_down_counts_less(self):
        self.core.observe(text="我去忙了，回头聊", at=T_DAY)  # 收尾语 → winding_down
        self.core.tick(at=T_DAY + 3600)
        g = self.core.snapshot(at=T_DAY + 3600)["bond"]["grievance"]
        self.assertAlmostEqual(g, 6.0, delta=0.6)

    def test_closed_topic_does_not_count(self):
        """话题聊完，不回很正常（R9）。"""
        self.core.observe(text="不聊了", at=T_DAY)
        self.core.tick(at=T_DAY + 3600)
        g = self.core.snapshot(at=T_DAY + 3600)["bond"]["grievance"]
        self.assertAlmostEqual(g, 0.0, delta=0.2)

    def test_waiting_for_answer_multiplies(self):
        self.core.observe(text="在忙", at=T_DAY)
        self.core.observe(text="你忙完啦？", speaker="self", at=T_DAY + 30)
        self.core.tick(at=T_DAY + 3630)
        g = self.core.snapshot(at=T_DAY + 3630)["bond"]["grievance"]
        self.assertAlmostEqual(g, 18.0 * 1.8, delta=1.0)

    def test_quiet_hours_dampen(self):
        self.core.observe(text="今天好热啊", at=T_NIGHT)
        self.core.tick(at=T_NIGHT + 3600)
        g = self.core.snapshot(at=T_NIGHT + 3600)["bond"]["grievance"]
        self.assertAlmostEqual(g, 18.0 * 0.2, delta=0.4)

    def test_affinity_amplifies(self):
        self.core.observe(text="今天好热啊", at=T_DAY)
        self.core._bond("主人").affinity = 75.0
        self.core.tick(at=T_DAY + 3600)
        g = self.core.snapshot(at=T_DAY + 3600)["bond"]["grievance"]
        self.assertAlmostEqual(g, 18.0 * 1.3, delta=0.8)

    def test_her_repeated_messages_do_not_reset_neglect(self):
        """她一直催你，冷落照涨 —— 不能因为她开口就把账清了。"""
        self.core.observe(text="在忙", at=T_DAY)
        self.core.observe(text="你忙完啦？", speaker="self", at=T_DAY + 30)
        self.core.observe(text="人呢？", speaker="self", at=T_DAY + 600)
        self.core.observe(text="算了，你是不是不想理我了？", speaker="self", at=T_DAY + 1200)
        self.core.tick(at=T_DAY + 3600)
        g = self.core.snapshot(at=T_DAY + 3600)["bond"]["grievance"]
        # 从"对方最后一条"算 1 小时：18 × 1.8 ≈ 32.4（中途有委屈衰减，留点余量）
        # 关键是：她连发三条也没把账清零（清零的话只会有 6 左右）
        self.assertGreater(g, 25)
        self.assertLess(g, 34)

    def test_grievance_reaches_sulky_not_cold_after_one_hour(self):
        self.core.observe(text="在忙", at=T_DAY)
        self.core.observe(text="你忙完啦？", speaker="self", at=T_DAY + 30)
        self.core.tick(at=T_DAY + 3630)
        snap = self.core.snapshot(at=T_DAY + 3630)
        self.assertLess(snap["bond"]["grievance"], 35)
        self.assertEqual(snap["bond"]["mood"], "slight")  # 小生气，哄一句就好


class TestSoothing(unittest.TestCase):
    """哄两句也消气，但不如正式道歉。"""

    def setUp(self):
        tmp_root = ROOT / ".test_tmp"
        tmp_root.mkdir(exist_ok=True)
        self.state_path = tmp_root / ("state-" + uuid.uuid4().hex + ".json")
        self.core = TideCore.from_config(CFG_DIR, state_path=self.state_path)

    def tearDown(self):
        for p in (self.state_path, self.state_path.with_suffix(".json.tmp")):
            if p.exists():
                p.unlink()

    def test_mild_anger_clears_with_one_comfort(self):
        """小生气：一句哄就直接清零。"""
        c = self.core
        c.observe(text="你真笨", at=T_DAY)
        self.assertEqual(c.snapshot(at=T_DAY)["bond"]["tier"], "mild")
        c.observe(text="抱抱", at=T_DAY + 60)
        self.assertEqual(c.snapshot(at=T_DAY + 60)["bond"]["grievance"], 0.0)

    def test_big_anger_numbers_do_not_move(self):
        """大生气：道歉和哄都不动数字，只缩短冷静时间。"""
        c = self.core
        c.observe(text="你真笨", at=T_DAY)              # 23
        c.observe(text="你真烦人", at=T_DAY + 40)        # 46
        c.observe(text="你真蠢", at=T_DAY + 80)          # 69 → 大生气
        snap = c.snapshot(at=T_DAY + 80)["bond"]
        self.assertEqual(snap["tier"], "big")
        self.assertAlmostEqual(snap["cool_left_h"], 6.0, delta=0.1)
        g0 = snap["grievance"]

        c.observe(text="抱抱", at=T_DAY + 120)
        snap = c.snapshot(at=T_DAY + 120)["bond"]
        self.assertAlmostEqual(snap["grievance"], g0, delta=1.0)   # 数字不动
        self.assertAlmostEqual(snap["cool_left_h"], 4.8, delta=0.1)  # 冷却 6h→4.8h

        c.observe(text="对不起，是我不好", at=T_DAY + 160)
        snap = c.snapshot(at=T_DAY + 160)["bond"]
        self.assertAlmostEqual(snap["grievance"], g0, delta=1.0)
        self.assertAlmostEqual(snap["cool_left_h"], 2.88, delta=0.1)  # →2.88h


if __name__ == "__main__":
    unittest.main()