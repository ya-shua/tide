"""睡眠不是墙上时间：累会提前，担心/难过/生气会往后拖。"""
import sys
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tide.circadian import Circadian  # noqa: E402
from tide.core import TideCore  # noqa: E402

CFG_DIR = ROOT / "config"
T0 = time.mktime(time.strptime("2026-03-01 22:00", "%Y-%m-%d %H:%M"))


class TestOnset(unittest.TestCase):
    def setUp(self):
        self.c = Circadian()

    def test_tired_goes_to_bed_earlier(self):
        self.assertLess(self.c.onset_hour(90), self.c.onset_hour(20))

    def test_worry_delays_sleep(self):
        calm = self.c.onset_hour(50)
        worried = self.c.onset_hour(50, {"worried": 0.5})
        self.assertGreater(worried, calm + 0.5)

    def test_anger_is_worse_than_worry(self):
        self.assertGreater(self.c.onset_hour(50, {"angry": 0.5}),
                           self.c.onset_hour(50, {"worried": 0.5}))

    def test_delay_is_capped(self):
        wild = self.c.onset_hour(50, {"angry": 1.0, "worried": 1.0, "sad": 1.0})
        self.assertLessEqual(wild, self.c.cfg["latest_onset"])

    def test_calm_mood_does_not_move_it(self):
        self.assertAlmostEqual(self.c.onset_hour(50, {"calm": 1.0}),
                               self.c.onset_hour(50), places=3)

    def test_sad_sleeps_shorter_joy_sleeps_longer(self):
        self.assertLess(self.c.plan_sleep(50, {"sad": 1.0}),
                        self.c.plan_sleep(50))
        self.assertGreater(self.c.plan_sleep(50, {"joyful": 1.0}),
                           self.c.plan_sleep(50))


class TestInCore(unittest.TestCase):
    def setUp(self):
        tmp = ROOT / ".test_tmp"
        tmp.mkdir(exist_ok=True)
        self.state = tmp / ("sleep-" + uuid.uuid4().hex + ".json")
        self.core = TideCore.from_config(CFG_DIR, state_path=self.state)
        self.core.last_tick = T0

    def tearDown(self):
        self.state.unlink(missing_ok=True)

    def test_snapshot_says_when_and_why(self):
        snap = self.core.snapshot(at=T0)
        ck = snap["clock"]
        self.assertIn("onset_text", ck)
        self.assertRegex(ck["onset_text"], r"^\d\d:\d\d$")
        self.assertTrue(ck["why"])

    def test_worried_she_goes_later(self):
        base = self.core.clock.onset_hour(50)
        later = self.core.clock.onset_hour(50, {"worried": 0.6})
        self.assertGreater(later, base)

    def test_settings_move_the_window(self):
        self.core.update_settings({"sleep_normal": "22:30", "sleep_earliest": "20:00",
                                   "sleep_mood_delay": 3})
        self.assertAlmostEqual(self.core.clock.cfg["normal_onset"], 22.5, places=2)
        self.assertAlmostEqual(self.core.clock.cfg["earliest_onset"], 20.0, places=2)
        self.assertEqual(self.core.clock.cfg["mood_delay_max"], 3.0)


if __name__ == "__main__":
    unittest.main()