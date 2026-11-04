"""真实的娱乐内容源：她无聊时真的去看一条视频，而不是假装。

现在的接法是"借用"刷B站插件的运行环境：
    C:\\Users\\<你>\\.dsh\\bili-duty\\.venv   ← 有 bilibili_api、有登录态
Tide自己是零依赖的，所以由 `tide/_bili_search.py` 在那个 venv 里跑一次搜索，
拿回真实的标题 / BV 号 / UP主 / 封面。

三条原则：
1. 只搜不看：不点赞、不投币、不关注，不碰任何写接口
2. 绝不卡住面板：搜索放在后台线程，结果进缓存；缓存空就退回文字
3. 拿不到就承认拿不到：源不可用时返回 None，让上层用普通文案
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE") or Path.home())
DEFAULT_PY = HOME / ".dsh" / "bili-duty" / ".venv" / "Scripts" / "python.exe"
HELPER = Path(__file__).with_name("_bili_search.py")


class Media:
    def __init__(self, cfg=None, py_path=None, enabled=None):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True)) if enabled is None else bool(enabled)
        self.keywords = [str(k) for k in (cfg.get("keywords") or ["猫", "搞笑", "美食"])]
        self.py_path = Path(py_path or cfg.get("python") or DEFAULT_PY)
        self.timeout = float(cfg.get("timeout_sec", 25))
        self._cache = []
        self._lock = threading.Lock()
        self._busy = False
        self.last_error = ""

    # ---------- 探路 ----------
    def available(self) -> bool:
        return bool(self.enabled and self.py_path.exists() and HELPER.exists())

    # ---------- 后台取 ----------
    def prefetch(self, keyword: str | None = None) -> bool:
        """起一个线程去搜；不阻塞调用方。返回是否真的起了线程。"""
        if not self.available():
            return False
        with self._lock:
            if self._busy or self._cache:
                return False
            self._busy = True
        kw = keyword or self.keywords[int(time.time() // 60) % len(self.keywords)]
        threading.Thread(target=self._run, args=(kw,), daemon=True).start()
        return True

    def _run(self, keyword: str) -> None:
        try:
            out = subprocess.run(
                [str(self.py_path), "-X", "utf8", str(HELPER), keyword],
                capture_output=True, timeout=self.timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw = (out.stdout or b"").decode("utf-8", "replace").strip()
            data = json.loads(raw.splitlines()[-1]) if raw else {}
            if data.get("ok"):
                items = [it for it in data.get("items") or [] if it.get("bvid")]
                with self._lock:
                    self._cache = items
                self.last_error = ""
            else:
                self.last_error = str(data.get("error") or "unknown")
        except Exception as exc:
            self.last_error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            with self._lock:
                self._busy = False

    # ---------- 取一条 ----------
    def take(self, keyword: str | None = None) -> dict | None:
        """拿一条"她刚看的"，缓存空就顺手补一次后台搜索。"""
        with self._lock:
            if self._cache:
                item = self._cache.pop(0)
                return dict(item)
        self.prefetch(keyword)
        return None


def describe(item: dict) -> str:
    """她怎么跟人说这件事。"""
    title = str(item.get("title") or "一个视频")
    return f"看了《{title}》"