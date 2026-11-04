"""把话真的发到 QQ 上。

走本机 SnowLuma 的 OneBot HTTP 接口（`config/rules.yaml` 的 qq 段）：

    qq:
      enabled: true
      api: "http://127.0.0.1:3000"
      token: "<OneBot accessToken>"
      target: <你的QQ号>        # 发给谁（QQ 号）

三件事保证"不会悄悄失败"：
1. **dry_run**：只生成不发送，用来排练
2. **outbox**：无论发没发出去，都往 data/outbox.jsonl 追加一条，事后能查
3. **返回真实结果**：OneBot 的 retcode / message 原样带回来，不吞错
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API = "http://127.0.0.1:3000"


class QQ:
    def __init__(self, cfg=None, outbox: Path | None = None):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.api = str(cfg.get("api") or DEFAULT_API).rstrip("/")
        self.token = str(cfg.get("token") or "")
        self.target = int(cfg.get("target") or 0)
        self.dry_run = bool(cfg.get("dry_run", False))
        self.timeout = float(cfg.get("timeout_sec", 8))
        self.outbox = Path(outbox) if outbox else None
        self._probe = None       # (ts, ok)
        self.last_error = ""

    # ---------- 底层 ----------
    def _call(self, action: str, params: dict | None = None, timeout=None) -> dict | None:
        body = json.dumps(params or {}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.api}/{action}", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}"},
        )
        try:
            raw = urllib.request.urlopen(req, timeout=timeout or self.timeout).read()
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.last_error = f"HTTP {exc.code}"
            return None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

    def available(self, refresh: bool = False) -> bool:
        """能不能发：接口活着、账号在线、有收件人。"""
        if not (self.enabled and self.target):
            return False
        now = time.time()
        if not refresh and self._probe and now - self._probe[0] < 60:
            return self._probe[1]
        ok = False
        info = self._call("get_login_info", {}, timeout=4)
        if info and info.get("status") == "ok":
            ok = bool((info.get("data") or {}).get("user_id"))
            self.account = (info.get("data") or {}).get("nickname")
        self._probe = (now, ok)
        return ok

    # ---------- 发送 ----------
    def send(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty"}
        self._to_outbox({"dir": "out", "text": text, "target": self.target,
                         "at": round(time.time(), 3), "dry": self.dry_run})
        if self.dry_run:
            return {"ok": True, "dry": True, "text": text}
        if not self.enabled:
            return {"ok": False, "error": "qq disabled"}
        if not self.target:
            return {"ok": False, "error": "no target"}
        res = self._call("send_private_msg",
                         {"user_id": self.target, "message": text})
        if not res:
            return {"ok": False, "error": self.last_error or "no response"}
        ok = res.get("status") == "ok" and res.get("retcode") == 0
        return {"ok": ok, "retcode": res.get("retcode"),
                "message_id": (res.get("data") or {}).get("message_id"),
                "error": None if ok else str(res.get("message") or res.get("wording") or "")}

    def _to_outbox(self, row: dict) -> None:
        if not self.outbox:
            return
        try:
            self.outbox.parent.mkdir(parents=True, exist_ok=True)
            with self.outbox.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass