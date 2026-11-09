"""单实例 + 一次开口只记一次。

两件事都是实测踩出来的：

1. Windows 上两个进程能同时绑同一个端口（`allow_reuse_address`），于是两个 Tide
   各跑各的时钟、共用一份 state.json —— 表现就是「刚说完一句，两分钟后又冒一句」。
2. 同一次开口会被记两遍：宿主回执 `report_proactive` 记一次，mood 插件的
   `speech.gate` 又记一次。次数翻倍 → 冷却按递减模式掉到 5 分钟，越聊越黏。
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
T0 = time.mktime(time.strptime("2026-03-01 14:00", "%Y-%m-%d %H:%M"))


class WokeOnce(unittest.TestCase):
    def setUp(self):
        tmp = ROOT / ".test_tmp"
        tmp.mkdir(exist_ok=True)
        self.state_path = tmp / ("state-" + uuid.uuid4().hex + ".json")
        self.core = TideCore.from_config(CFG_DIR, state_path=self.state_path)

    def tearDown(self):
        if self.state_path.exists():
            self.state_path.unlink()

    def test_two_marks_within_30s_count_once(self):
        self.core.mark_woke(T0)
        self.core.mark_woke(T0 + 1)
        self.assertEqual(self.core._wakes_today(T0), 1)

    def test_mark_after_window_counts_again(self):
        self.core.mark_woke(T0)
        self.core.mark_woke(T0 + 31)
        self.assertEqual(self.core._wakes_today(T0), 2)

    def test_dedupe_returns_skipped(self):
        self.core.mark_woke(T0)
        res = self.core.mark_woke(T0 + 2)
        self.assertTrue(res.get("skipped"))

    def test_real_send_blocks_next_ask_for_cooldown(self):
        """说完一句，冷却期里不该再问第二次。"""
        # 先让她「很想找你」，否则挡住的原因是「还不到想你的程度」，测不到冷却
        self.core.needs.last_seen = T0 - 20 * 3600
        self.core.needs.longing_at = T0 - 20 * 3600
        self.core.needs.longing_value = 0.0
        self.core.needs.hold_until = 0.0
        self.core.last_wake_at = T0
        self.core.wake_marks = [T0]
        gate = self.core.should_wake(T0 + 2 * 60)
        self.assertFalse(gate["wake"])
        self.assertIn("冷却", gate["why"])


class LockFile(unittest.TestCase):
    def test_take_lock_refuses_live_other_pid(self):
        from tide import panel

        tmp = ROOT / ".test_tmp"
        tmp.mkdir(exist_ok=True)
        lock = tmp / "panel.lock"
        lock.write_text("4", encoding="ascii")      # pid 4：System，活着但没权限打开
        original = panel.LOCK_FILE
        panel.LOCK_FILE = lock
        try:
            self.assertFalse(panel._take_lock())
        finally:
            panel.LOCK_FILE = original
            lock.unlink(missing_ok=True)

    def test_take_lock_replaces_dead_pid(self):
        from tide import panel

        tmp = ROOT / ".test_tmp"
        tmp.mkdir(exist_ok=True)
        lock = tmp / "panel.lock"
        lock.write_text("999999", encoding="ascii")   # 不存在的进程 privacy-allow（假 PID）
        original = panel.LOCK_FILE
        panel.LOCK_FILE = lock
        try:
            self.assertTrue(panel._take_lock())
            self.assertEqual(lock.read_text(encoding="ascii").strip(), str(__import__("os").getpid()))
        finally:
            panel.LOCK_FILE = original
            lock.unlink(missing_ok=True)

    def test_server_does_not_reuse_address(self):
        from tide import panel

        self.assertFalse(panel._Server.allow_reuse_address)


if __name__ == "__main__":
    unittest.main()
