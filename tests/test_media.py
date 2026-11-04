"""真实内容源：能拿到就真的看一条，拿不到就老实退回文字。"""
import unittest

from tide import media as media_mod
from tide.media import Media


class TestMediaAvailability(unittest.TestCase):
    def test_disabled_source_is_unavailable(self):
        m = Media({"enabled": False})
        self.assertFalse(m.available())
        self.assertIsNone(m.take())

    def test_missing_python_means_unavailable(self):
        m = Media({}, py_path="C:/definitely/not/here/python.exe")
        self.assertFalse(m.available())
        self.assertIsNone(m.take())

    def test_take_pops_from_cache(self):
        m = Media({})
        m._cache = [{"bvid": "BV1", "title": "猫：你在教我做事？"}]
        first = m.take()
        self.assertEqual(first["bvid"], "BV1")
        self.assertIsNone(m.take())          # 缓存空了就没了，不会重复看同一条

    def test_describe_reads_like_a_person(self):
        text = media_mod.describe({"title": "猫妈：我好像还没教你这个吧"})
        self.assertEqual(text, "看了《猫妈：我好像还没教你这个吧》")


class TestSelfCareUsesRealVideo(unittest.TestCase):
    """轮到"刷视频"那一档时，如果内容源里有货，就真的记成"看了《…》"。"""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from tide.core import TideCore

        self.tmp = tempfile.TemporaryDirectory()
        self.core = TideCore.from_config(
            Path(__file__).resolve().parent.parent / "config",
            state_path=Path(self.tmp.name) / "state.json")
        self.core.reset()

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_video_becomes_what_she_watched(self):
        self.core.media._cache = [{"bvid": "BV1ErHN6KEWc", "title": "猫：你在教我做事？",
                                   "url": "https://www.bilibili.com/video/BV1ErHN6KEWc",
                                   "author": "十四毅", "cover": ""}]
        self.core.last_tick = 1000.0
        self.core.needs.care_log = ["刷了会儿视频"]
        self.core._absorb_self_care(0.0, 1000.0)
        snap = self.core.snapshot(at=1000.0)
        self.assertEqual(snap["auto"]["note"], "看了《猫：你在教我做事？》")
        self.assertEqual(snap["media"]["bvid"], "BV1ErHN6KEWc")
        row = [e for e in self.core.log if e.get("media")]
        self.assertTrue(row and row[-1]["media"]["title"] == "猫：你在教我做事？")

    def test_without_source_she_still_says_something(self):
        self.core.media.enabled = False
        self.core.last_tick = 1000.0
        self.core.needs.care_log = ["刷了会儿视频"]
        self.core._absorb_self_care(0.0, 1000.0)
        self.assertEqual(self.core.snapshot(at=1000.0)["auto"]["note"], "刷了会儿视频")


if __name__ == "__main__":
    unittest.main()