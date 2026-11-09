"""宿主桥：把「我该找他了」交给宿主去说。

Tide 只判断，不替角色开口 —— 这是 2026-11-07 定下来的分工：
Tide 是身体（想不想、难不难受），宿主是嘴（说什么、什么口吻、有没有人设）。

所以这里只做两件事：

    notify(payload)     告诉宿主「我想找他说句话」，把该给的理由一起给过去
    report(...)         （由面板端点转进来）宿主说完了没、成没成

约定（对外一样，别的宿主照着实现就行）：

    POST {host.url}/api/proactive/say
    {
      "event_id": "...",          # 这一次的唯一号，回执带着它对上
      "why": "想你 91",           # 为什么想开口（给人看的）
      "urgency": 87.4,            # 急不急
      "needs": {...},             # 当下的需求快照
      "report_url": "http://.../api/proactive-report",   # 宿主说完往哪儿回执
      "person": "主人"
    }

    → {"ok": true, "accepted": true}          # 接了，正在说
    → {"ok": false, "error": "..."}            # 不接（关掉了 / 没有这个插件）

回执（宿主 → Tide）:

    POST /api/proactive-report
    {"event_id": "...", "sent": true,  "text": "在吗", "error": ""}
    {"event_id": "...", "sent": false, "text": "",     "error": "QQ 断线"}

**失败也必须回执**：Tide 只有收到 sent=true 才算「她说过这句话」，
才算冷却、没回音；报成功但其实没发出去，她会以为你在冷落她。

没配宿主时，退回 Tide 自带的那张嘴（qq 通道，`wake.auto_send`）——
插件单独拿出去、没有宿主，也能自己跑。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class HostBridge:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.url = str(cfg.get("url") or "").rstrip("/")
        self.token = str(cfg.get("token") or "")
        self.timeout = float(cfg.get("timeout_sec", 5))
        # 没写 enabled 时：配了地址就算开
        self.enabled = bool(cfg.get("enabled", bool(self.url)))
        self.last_error = ""

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.url)

    def notify(self, payload: dict) -> dict:
        """让宿主开口。只负责「送到了没有」，不负责「说没说成」。"""
        if not self.ready:
            return {"ok": False, "error": "没配宿主"}
        # report_url 由 core 填（它知道面板端口），这里不猜
        data = json.dumps(dict(payload or {}), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.url}/api/proactive/say",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-console-token": self.token,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            out = json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            self.last_error = f"HTTP {exc.code}"
            return {"ok": False, "error": self.last_error}
        except Exception as exc:  # noqa: BLE001 - 宿主没起来就是连不上
            self.last_error = str(exc)[:160]
            return {"ok": False, "error": self.last_error}
        if not isinstance(out, dict):
            return {"ok": False, "error": "宿主回了看不懂的东西"}
        if not out.get("ok"):
            return {"ok": False, "error": str(out.get("error") or "宿主没收")}
        return {"ok": True, "accepted": bool(out.get("accepted", True))}