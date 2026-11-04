"""渴：涨得比饿快、喝水回落、她说得出「渴了」，而且她自己会去喝。"""
import tempfile
import unittest
from pathlib import Path

from tide.core import TideCore
from tide.needs import Needs

CONFIG = Path(__file__).resolve().parent.parent / "config"
T0 = 1_800_000_000.0


class TestThirst(unittest.TestCase):
    def test_thirst_rises_faster_than_hunger(self):
        n = Needs()
        n.advance(3600, night=False)
        self.assertGreater(n.thirst, n.hunger)

    def test_drinking_lowers_thirst(self):
        n = Needs()
        n.advance(3 * 3600, night=False)
        before = n.thirst
        n.apply({"thirst": -45})
        self.assertLess(n.thirst, before)

    def test_thirst_never_negative(self):
        n = Needs()
        n.apply({"thirst": -999})
        self.assertEqual(n.thirst, 0.0)


class TestSheTakesCareOfHerself(unittest.TestCase):
    """渴了饿了，她自己会解决——不该一直挂在高位等人喂。"""

    def test_thirst_stops_climbing_and_gets_handled(self):
        n = Needs()
        n.advance(30 * 3600, night=False)
        # 一路涨到 100 是不可能的：她中途就去倒水了
        self.assertLess(n.thirst, 90)
        self.assertGreater(n.thirst, 0)

    def test_self_care_notes_are_recorded(self):
        n = Needs()
        n.advance(20 * 3600, night=False)
        self.assertTrue(any("水" in note for note in n.care_log))

    def test_never_stays_pinned_at_hundred(self):
        n = Needs()
        for _ in range(12):                      # 每两小时看一眼
            n.advance(2 * 3600, night=False)
            for key in ("thirst", "hunger", "energy", "boredom"):
                self.assertLess(getattr(n, key), 95, key)

    def test_longing_does_not_heal_itself(self):
        n = Needs()
        n.last_seen = 1000.0
        now = 1000.0 + 100 * 3600
        self.assertGreater(n.longing(now, 50), 90)   # 想你不能自己解决


class TestDrinkEvent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = TideCore.from_config(CONFIG, state_path=Path(self.tmp.name) / "state.json")
        self.core.reset()

    def tearDown(self):
        self.tmp.cleanup()

    def test_drink_event_lowers_thirst_and_records_memory(self):
        self.core.advance(hours=3)
        before = self.core.needs.thirst
        self.core.event("drink", at=self.core.now())
        self.assertLess(self.core.needs.thirst, before)
        self.assertTrue(any(it.get("text") == "喝了点水" for it in self.core.memory.items))

    def test_snapshot_exposes_thirst(self):
        snap = self.core.snapshot(at=self.core.now())
        self.assertIn("thirst", snap["needs"])

    def test_forecast_includes_thirst(self):
        from tide.forecast import forecast
        series = forecast(self.core, hours=2, step_h=1)
        self.assertIn("thirst", series[0])

    def test_self_care_shows_up_in_snapshot(self):
        self.core.advance(hours=6)
        snap = self.core.snapshot()
        self.assertTrue(snap["auto"]["note"])
        self.assertIsNotNone(snap["auto"]["ago_min"])

    def test_self_care_is_remembered(self):
        self.core.advance(hours=6)
        texts = [it.get("text") for it in self.core.memory.items]
        self.assertTrue(any("水" in (x or "") or "吃" in (x or "") for x in texts))


if __name__ == "__main__":
    unittest.main()