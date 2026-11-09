"""海螺 ↔ Tide（汐）的线：只发 HTTP，不搬逻辑。

为什么走 HTTP 而不是在进程里再 import 一份 TideCore
------------------------------------------------
Tide 是她的本体，状态只有一份（`tide/data/state.json`，面板看得见的那份）。
海螺再 import 一个 TideCore 就会变成两个脑子：面板上显示的心情
和聊天时用的心情对不上，改了一边另一边不知道。

所以这里只当"电话线"：

    Tide 面板在 → 问它（这是她真实的此刻）
    Tide 面板不在 → 什么都不加，聊天照常（不拦话、不编心情）

面板的接口（tide/tide/panel.py）：
    GET  /api/state?person=…   快照 + 给模型的那段话
    POST /api/observe          听来一句话（speaker=other / self / initiated）
    POST /api/woke             她真的开口了，记一次叫醒
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import quote


class TideClient:
    name = "tide-http"

    def __init__(self, base_url: str = "http://127.0.0.1:7880", timeout: float = 1.5):
        self.base = (base_url or "").rstrip("/")
        self.timeout = max(0.3, float(timeout or 1.5))

    # ── 底层 ─────────────────────────────────────────────
    def _call(self, path: str, payload: dict | None = None) -> dict | None:
        url = self.base + path
        data = None
        headers = {"User-Agent": "conch-tide-bridge"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            return json.loads(body) if body else {}
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return None

    # ── 给插件用的三个动作 ────────────────────────────────
    def state(self, person: str | None = None) -> dict | None:
        """面板在 → {snapshot, plan}；不在 → None。"""
        path = "/api/state" + (f"?person={quote(person)}" if person else "")
        return self._call(path)

    def observe(self, text: str, person: str | None = None,
                speaker: str = "other", initiated: bool = False) -> dict | None:
        return self._call("/api/observe", {
            "text": text,
            "person": person or "",
            "speaker": speaker,
            "initiated": bool(initiated),
        })

    def woke(self) -> dict | None:
        return self._call("/api/woke", {})

    def alive(self) -> bool:
        return self._call("/api/health") is not None