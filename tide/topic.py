"""话题生命周期 + 冷落值（文档 §6，本插件最核心的一段）。

    active ──(密度下降/收尾语)──▶ winding_down ──(超时)──▶ closed
       ▲                                                    │
       └────────────(新消息带来新话题)───────────────────────┘

冷落值的意义（R9）：
    她问"你在干嘛呀"你没回 → 算冷落
    她说"那我先睡啦"，你没回 → 不算
"""
from __future__ import annotations


class Topic:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        topic = cfg.get("topic") or {}
        neglect = cfg.get("neglect") or {}

        self.closing_phrases = [str(x) for x in (topic.get("closing_phrases") or [])]
        self.explicit_end = [str(x) for x in (topic.get("explicit_end") or [])]
        self.question_tails = [str(x) for x in (topic.get("question_tails") or ["?"])]
        self.idle_to_closed_min = float(topic.get("idle_to_closed_min", 20))

        self.active_per_hour = float(neglect.get("active_per_hour", 18))
        self.winding_per_hour = float(neglect.get("winding_per_hour", 6))
        self.question_multiplier = float(neglect.get("question_multiplier", 1.8))
        self.affinity_threshold = float(neglect.get("affinity_threshold", 70))
        self.affinity_factor = float(neglect.get("affinity_factor", 1.3))
        self.cap = float(neglect.get("cap", 80))
        self.quiet_factor = float(cfg.get("quiet_factor", 0.2))

        self.state = "closed"
        self.last_msg_at = 0.0
        self.last_other_at = 0.0
        self.her_last_asked = False
        self.her_asked_at = 0.0
        self.prev_neglect = 0.0

    # ---- 消息事件 ----
    def on_other(self, text: str, now: float) -> None:
        """对方说话。"""
        text = text or ""
        self.last_msg_at = now
        self.last_other_at = now
        self.prev_neglect = 0.0
        self.her_last_asked = False
        if any(p and p in text for p in self.explicit_end):
            self.state = "closed"
        elif any(p and p in text for p in self.closing_phrases):
            self.state = "winding_down"
        else:
            self.state = "active"

    def on_self(self, text: str, now: float) -> None:
        """她说话。含问句 → 话题仍然开着，并且"在等回答"。

        注意：她说话**不重置冷落计时**。冷落是"对方没接话"，
        从对方最后一条算起 —— 否则她越催，计时越被清零，反而越不委屈。
        """
        text = text or ""
        self.last_msg_at = now
        asked = any(t and t in text for t in self.question_tails)
        self.her_last_asked = asked
        if asked:
            self.her_asked_at = now
            self.state = "active"
        else:
            self.state = "winding_down"

    # ---- 冷落值 ----
    def neglect(self, now: float, affinity: float, quiet: bool) -> float:
        if self.state == "closed":
            return 0.0
        anchor = self.last_other_at or self.last_msg_at
        idle_h = max(0.0, (now - anchor) / 3600.0)
        base = self.active_per_hour if self.state == "active" else self.winding_per_hour
        n = base * idle_h
        if self.her_last_asked:
            n *= self.question_multiplier
        if quiet:
            n *= self.quiet_factor
        if affinity >= self.affinity_threshold:
            n *= self.affinity_factor
        return min(n, self.cap)

    def accrual(self, now: float, affinity: float, quiet: bool) -> float:
        """自上次结算以来新增的冷落值（要加到 grievance 上的量）。"""
        cur = self.neglect(now, affinity, quiet)
        added = max(0.0, cur - self.prev_neglect)
        self.prev_neglect = cur
        return added

    # ---- 超时收尾 ----
    def maybe_close(self, now: float) -> None:
        if self.state == "closed" or not self.last_msg_at:
            return
        if self.her_last_asked:
            return  # 她在等回答，不算话题结束——这正是冷落
        if now - self.last_msg_at >= self.idle_to_closed_min * 60.0:
            self.state = "closed"
            self.prev_neglect = 0.0

    # ---- 读出 ----
    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "idle_min": None,
            "waiting_reply": self.her_last_asked,
        }

    def save(self) -> dict:
        return {
            "state": self.state,
            "last_msg_at": self.last_msg_at,
            "last_other_at": self.last_other_at,
            "her_last_asked": self.her_last_asked,
            "her_asked_at": self.her_asked_at,
            "prev_neglect": self.prev_neglect,
        }

    def load(self, data: dict) -> None:
        data = data or {}
        self.state = data.get("state", self.state)
        self.last_msg_at = float(data.get("last_msg_at", 0.0))
        self.last_other_at = float(data.get("last_other_at", self.last_msg_at))
        self.her_last_asked = bool(data.get("her_last_asked", False))
        self.her_asked_at = float(data.get("her_asked_at", 0.0))
        self.prev_neglect = float(data.get("prev_neglect", 0.0))