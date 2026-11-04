"""设置：写进去要能生效、不合法要挡住、越界要夹住。"""
import tempfile
import unittest
from pathlib import Path

from tide.core import TideCore
from tide.settings import DEFAULTS, Settings

CONFIG = Path(__file__).resolve().parent.parent / "config"
T0 = 1_800_000_000.0


class TestSettingsValidation(unittest.TestCase):
    def setUp(self):
        self.st = Settings()

    def test_clamps_out_of_range(self):
        self.st.update({"tier_big": 999})
        self.assertEqual(self.st.data["tier_big"], 100)

    def test_rejects_bad_time(self):
        with self.assertRaises(ValueError):
            self.st.update({"quiet_start": "25:99"})

    def test_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            self.st.update({"name": "   "})

    def test_thresholds_must_increase(self):
        with self.assertRaises(ValueError):
            self.st.update({"tier_mild": 50, "tier_mid": 40})
        self.assertEqual(self.st.data["tier_mid"], DEFAULTS["tier_mid"])

    def test_bad_batch_changes_nothing(self):
        before = dict(self.st.data)
        with self.assertRaises(ValueError):
            self.st.update({"calm_hours": 8, "quiet_end": "nope"})
        self.assertEqual(self.st.data, before)

    def test_survives_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.json"
            a = Settings(path); a.update({"tier_big": 70})
            b = Settings(path); b.load()
            self.assertEqual(b.data["tier_big"], 70)


class TestSettingsTakeEffect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.core = TideCore.from_config(CONFIG, state_path=Path(self.tmp.name) / "state.json")
        self.core.reset()

    def tearDown(self):
        self.tmp.cleanup()

    def test_calm_hours_changes_cooldown(self):
        self.core.update_settings({"calm_hours": 2})
        self.core.observe("你真笨", at=T0)
        self.core.observe("你真笨", at=T0 + 10)
        self.core.observe("你真笨", at=T0 + 20)
        self.core.event("apologize", at=T0 + 30)
        bond = self.core._bond("主人")
        self.assertLessEqual(bond.cool_left_h(T0 + 31), 2.0)

    def test_quiet_hours_changes_quiet_flag(self):
        self.core.update_settings({"quiet_start": "00:00", "quiet_end": "23:59"})
        self.assertTrue(self.core.snapshot(at=T0)["quiet"])

    def test_name_and_person_apply(self):
        self.core.update_settings({"name": "小Tide", "person": "阿蓝"})
        snap = self.core.snapshot(at=T0)
        self.assertEqual(snap["name"], "小Tide")
        self.assertEqual(snap["person"], "阿蓝")

    def test_memory_quote_ttl_applies(self):
        self.core.update_settings({"memory_quote_hours": 0})
        self.core.observe("你真笨", at=T0)
        snap = self.core.snapshot(at=T0 + 3600)
        self.assertIsNone(snap["memory"]["last_neg"]["quote"])

    def test_settings_show_up_in_snapshot(self):
        snap = self.core.snapshot(at=T0)
        self.assertIn("refresh_ms", snap["settings"])


if __name__ == "__main__":
    unittest.main()