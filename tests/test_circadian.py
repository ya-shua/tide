"""生物钟：几点睡看累不累；睡着了也能被叫醒，而且会不高兴。"""
import time
import unittest
from pathlib import Path

from tide.circadian import Circadian, hour_of
from tide.core import TideCore
from tide.needs import Needs

CONFIG = Path(__file__).resolve().parent.parent / "config"
DAY = time.mktime(time.strptime("2026-03-01 15:00", "%Y-%m-%d %H:%M"))
NIGHT = time.mktime(time.strptime("2026-03-02 03:00", "%Y-%m-%d %H:%M"))


class TestBedtimeFollowsFatigue(unittest.TestCase):
    def test_tired_goes_to_bed_earlier(self):
        c = Circadian()
        self.assertLess(c.onset_hour(95), c.onset_hour(20))

    def test_onset_stays_in_sane_range(self):
        c = Circadian()
        self.assertGreaterEqual(c.onset_hour(100), 21.5)
        self.assertLessEqual(c.onset_hour(0), 26.0)

    def test_sleep_length_follows_fatigue(self):
        c = Circadian()
        self.assertGreater(c.plan_sleep(95), c.plan_sleep(10))
        self.assertTrue(6.0 <= c.plan_sleep(50) <= 9.0)

    def test_nap_at_noon_when_wrecked(self):
        c = Circadian()
        noon = time.mktime(time.strptime("2026-03-01 14:00", "%Y-%m-%d %H:%M"))
        self.assertTrue(c.should_fall_asleep(noon, 92))
        self.assertFalse(c.should_fall_asleep(noon, 30))


class TestSleepFixesFatigue(unittest.TestCase):
    def test_sleeping_lowers_tiredness(self):
        n = Needs()
        n.energy = 90
        before = n.energy
        n.advance(4 * 3600, night=True, asleep=True)
        self.assertLess(n.energy, before - 50)

    def test_sleeping_slows_hunger(self):
        awake, asleep = Needs(), Needs()
        awake.advance(2 * 3600, night=False)          # 两小时内还不会自己加餐
        asleep.advance(2 * 3600, night=False, asleep=True)
        self.assertLess(asleep.hunger, awake.hunger)


class TestWokenUp(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.core = TideCore.from_config(CONFIG, state_path=Path(self.tmp.name) / "state.json")
        self.core.reset()
        self.core.last_tick = DAY
        self.core.clock.asleep = True
        self.core.clock.plan_hours = 8.0      # 打算睡八小时
        self.core.clock.since = DAY - 600     # 刚睡十分钟

    def tearDown(self):
        self.tmp.cleanup()

    def test_she_wakes_up_and_answers(self):
        self.core.observe("在吗", at=DAY)
        self.assertFalse(self.core.clock.asleep)
        self.assertIsNotNone(self.core.just_woken)

    def test_short_sleep_means_bad_mood(self):
        self.core.observe("在吗", at=DAY)
        self.assertTrue(self.core.just_woken["hard"])
        self.assertGreater(self.core.emotion.levels.get("annoyed", 0), 0.2)

    def test_being_woken_is_remembered(self):
        self.core.observe("在吗", at=DAY)
        texts = [i.get("text") for i in self.core.memory.items]
        self.assertTrue(any("吵醒" in (x or "") for x in texts))

    def test_deep_sleep_is_less_angry(self):
        self.core.clock.since = NIGHT - 5 * 3600   # 睡够了五小时
        self.core.last_tick = NIGHT                # 不推进，直接在这时候被叫醒
        self.core.observe("在吗", at=NIGHT)         # 但凌晨三点
        self.assertTrue(self.core.just_woken["hard"])  # 凌晨照样有起床气

    def test_she_does_not_proactively_talk_while_asleep(self):
        self.assertTrue(self.core.is_quiet(DAY))
        self.assertIsNone(self.core.pending_message(at=DAY))


if __name__ == "__main__":
    unittest.main()