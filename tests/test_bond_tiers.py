"""委屈分三档：小生气哄一哄就好，中生气要道歉+哄，大生气只能等。

每档有地板：时间只能把她磨到地板，再往下要靠解法。
"""
import sys
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tide.bond import Bond  # noqa: E402
from tide.core import TideCore  # noqa: E402

CFG_DIR = ROOT / "config"
T0 = time.mktime(time.strptime("2026-03-01 14:00", "%Y-%m-%d %H:%M"))


class TestTiers(unittest.TestCase):
    def test_tier_boundaries(self):
        b = Bond({})
        b.grievance = 10
        self.assertEqual(b.tier, "none")
        b.grievance = 20
        self.assertEqual(b.tier, "mild")
        b.grievance = 40
        self.assertEqual(b.tier, "mid")
        b.grievance = 70
        self.assertEqual(b.tier, "big")
        self.assertEqual(b.mood, "cold")

    def test_mild_has_no_floor(self):
        """小生气：时间能磨掉，哄一句也直接化。"""
        b = Bond({})
        b.apply({"grievance": 20}, T0)
        self.assertEqual(b.floor(T0), 0.0)
        b.decay(90 * 60, T0)          # 一个半衰期
        self.assertAlmostEqual(b.grievance, 10.0, delta=0.5)

    def test_mid_stops_at_floor_until_apology_and_comfort(self):
        """中生气：只哄不道歉，停在 36；两样都到齐才往下走。"""
        b = Bond({})
        b.apply({"grievance": 45}, T0)
        self.assertEqual(b.floor(T0), 36.0)
        for _ in range(8):            # 时间磨很久
            b.decay(3600, T0)
        self.assertAlmostEqual(b.grievance, 36.0, delta=0.5)
        self.assertEqual(b.mood, "sulky")

        b.note(["care"], T0)          # 只哄
        self.assertEqual(b.floor(T0), 36.0)
        b.note(["apology"], T0)       # 道歉到了：地板打开
        self.assertEqual(b.floor(T0), 0.0)
        b.decay(90 * 60, T0)
        self.assertLess(b.grievance, 20)

    def test_big_needs_time_not_apology(self):
        """大生气：道歉也不能立刻好，只能缩短冷静时间。"""
        b = Bond({})
        b.apply({"grievance": 80}, T0)          # 跨进大生气：冷却 6h
        self.assertAlmostEqual(b.cool_left_h(T0), 6.0, delta=0.1)
        self.assertEqual(b.floor(T0), 66.0)

        b.note(["apology"], T0)                  # 道歉：6h → 3.6h
        self.assertAlmostEqual(b.cool_left_h(T0), 3.6, delta=0.1)
        b.note(["care"], T0)                     # 哄：3.6h → 2.88h
        self.assertAlmostEqual(b.cool_left_h(T0), 2.88, delta=0.1)

        # 冷静没结束之前，时间也磨不到 66 以下
        b.decay(3600, T0 + 3600)
        self.assertAlmostEqual(b.grievance, 66.0, delta=0.5)
        self.assertEqual(b.mood, "cold")

        # 冷静结束后地板打开
        t_end = T0 + 3 * 3600
        self.assertEqual(b.floor(t_end), 0.0)
        self.assertLess(b.grievance, 66.0 + 0.01)

    def test_calm_minimum_floor(self):
        """还剩 2 小时时道歉，也只能砍到 1.5 小时（下限）。"""
        b = Bond({})
        b.apply({"grievance": 80}, T0)
        b.calm_until = T0 + 2 * 3600
        b.note(["apology"], T0)
        self.assertAlmostEqual(b.cool_left_h(T0), 1.5, delta=0.05)

    def test_comfort_cooldown(self):
        b = Bond({})
        self.assertTrue(b.comfort_ready(T0))
        b.mark_comfort(T0)
        self.assertFalse(b.comfort_ready(T0 + 60))
        self.assertTrue(b.comfort_ready(T0 + 601))


class TestTiersInCore(unittest.TestCase):
    def setUp(self):
        tmp_root = ROOT / ".test_tmp"
        tmp_root.mkdir(exist_ok=True)
        self.state_path = tmp_root / ("state-" + uuid.uuid4().hex + ".json")
        self.core = TideCore.from_config(CFG_DIR, state_path=self.state_path)

    def tearDown(self):
        for p in (self.state_path, self.state_path.with_suffix(".json.tmp")):
            if p.exists():
                p.unlink()

    def _g(self, at):
        return self.core.snapshot(at=at)["bond"]["grievance"]

    def test_comfort_cooldown(self):
        """10 分钟内连发两条哄，只算一次。"""
        c = self.core
        c.observe(text="你真笨", at=T0)
        c.observe(text="抱抱", at=T0 + 60)          # 小生气 → 清零
        self.assertEqual(self._g(T0 + 60), 0.0)
        c.observe(text="你真笨", at=T0 + 120)       # 又惹一次
        g1 = self._g(T0 + 120)
        c.observe(text="抱抱", at=T0 + 180)         # 冷却中：哄不动
        self.assertAlmostEqual(self._g(T0 + 180), g1, delta=0.5)

    def test_mid_anger_needs_both(self):
        """把她惹到中生气：只哄数字不动，道歉+哄齐了才解得开。"""
        c = self.core
        c.observe(text="你真笨", at=T0)                 # +23
        c.observe(text="你真烦人", at=T0 + 40)           # +23 → 46（中生气）
        c.observe(text="不聊了", at=T0 + 50)             # 收尾：停止冷落累积
        self.assertEqual(c.snapshot(at=T0 + 50)["bond"]["tier"], "mid")

        c.tick(at=T0 + 50 + 4 * 3600)                   # 磨 4 小时 → 停在地板
        g = self._g(T0 + 50 + 4 * 3600)
        self.assertAlmostEqual(g, 36.0, delta=1.0)
        self.assertEqual(c.snapshot(at=T0 + 50 + 4 * 3600)["bond"]["mood"], "sulky")

        c.observe(text="抱抱", at=T0 + 50 + 4 * 3600 + 60)   # 只哄：数字不动
        self.assertAlmostEqual(self._g(T0 + 50 + 4 * 3600 + 60), g, delta=0.5)

        c.observe(text="对不起，是我不好，不聊了", at=T0 + 50 + 4 * 3600 + 120)  # 补齐，并收尾
        c.tick(at=T0 + 50 + 6 * 3600)                   # 地板打开 → 化得下去
        self.assertLess(self._g(T0 + 50 + 6 * 3600), 20)


if __name__ == "__main__":
    unittest.main()