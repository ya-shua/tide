"""更新：版本比较、Release 检查、落地批处理的写法。不联网。"""
import pathlib
import shutil
import tempfile
import unittest

from tide import version as ver
from tide.updater import Updater


class VersionTest(unittest.TestCase):
    def test_compare(self):
        self.assertLess(ver.as_tuple("v0.1.0"), ver.as_tuple("0.1.1"))
        self.assertLess(ver.as_tuple("0.9.9"), ver.as_tuple("1.0.0"))
        self.assertEqual(ver.as_tuple("v1.2"), (1, 2, 0))
        self.assertEqual(ver.as_tuple("1.2.3-beta"), (1, 2, 3))
        self.assertEqual(ver.as_tuple(""), (0, 0, 0))

    def test_same_version_is_not_update(self):
        self.assertFalse(ver.as_tuple("0.1.0") > ver.as_tuple("v0.1.0"))


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.u = Updater({"repo": "someone/tide"}, self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake(self, tag):
        self.u._get_json = lambda url, timeout=15.0: {
            "tag_name": tag, "body": "说明", "zipball_url": "http://x/y.zip",
            "html_url": "http://x", "published_at": "2026-01-01",
        }

    def test_newer_release_shows_update(self):
        self._fake("v9.9.9")
        st = self.u.check(force=True)
        self.assertTrue(st["has_update"])
        self.assertEqual(st["latest"], "v9.9.9")
        self.assertEqual(st["notes"], "说明")
        self.assertEqual(st["error"], "")

    def test_same_release_is_quiet(self):
        self._fake("v" + ver.__version__)
        st = self.u.check(force=True)
        self.assertFalse(st["has_update"])

    def test_no_repo_means_no_check(self):
        u = Updater({"repo": ""}, self.tmp)
        u._get_json = lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该联网"))
        st = u.check(force=True)
        self.assertFalse(st["has_update"])
        self.assertEqual(st["error"], "")

    def test_network_failure_is_not_fatal(self):
        def boom(*a, **k):
            raise OSError("断网")
        self.u._get_json = boom
        st = self.u.check(force=True)
        self.assertFalse(st["has_update"])
        self.assertIn("检查更新失败", st["error"])

    def test_apply_without_update_refuses(self):
        self.u.state["has_update"] = False
        st = self.u.apply()
        self.assertIn("更新失败", st["error"])


class BatTest(unittest.TestCase):
    def test_bat_keeps_private_files(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            u = Updater({"repo": "someone/tide"}, tmp)
            bat = u._write_bat(tmp / "new")
            text = bat.read_text(encoding="utf-8")
            self.assertIn("robocopy", text)
            self.assertIn("data", text)
            self.assertIn("local.yaml", text)
            self.assertIn(".git", text)
            self.assertIn("-m tide.panel", text)
            self.assertIn("timeout /t 2", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()