"""关系（bond）：亲和 / 信任 / 委屈。按人一套。

委屈不是一条直线，而是**分档**的。每档有自己的"地板"：
时间只能把她磨到地板，再往下走要靠对应的解法。

| 档位 | 委屈 | 怎么好 | 地板 |
|---|---|---|---|
| 小生气 | 15~34 | 哄一句就化（也经得起时间磨） | 0 |
| 中生气 | 35~64 | 必须**道歉 + 哄**两样都出现；少一样就停在这儿 | 36 |
| 大生气 | ≥65 | 道歉和哄都只**缩短冷静时间**，真正的解药是等 | 66（未冷静完） |

设计意图：
- 小生气哄一哄就好 —— 不用道歉，别把小摩擦升级成大事故。
- 中生气光哄不动 —— 但也不至于要熬，认错+哄，门就开了。
- 大生气认错也没用 —— 她需要时间。你越急着哄，也只会把冷却缩短一点，
  这个机制防的是"一句对不起就想把大事抹平"。

地板之上按 90 分钟半衰期往下走（来得快）；到了地板就停住，等解锁。
"""
from __future__ import annotations


class Bond:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        tiers = cfg.get("tiers") or {}
        self.mild = float(tiers.get("mild", 15))
        self.mid = float(tiers.get("mid", 35))
        self.big = float(tiers.get("big", 65))

        self.hl_min = float(cfg.get("grievance_half_life_min", 90))
        self.calm_hours = float(cfg.get("calm_hours", 6))
        self.calm_min_hours = float(cfg.get("calm_min_hours", 1.5))
        self.apology_shorten = float(cfg.get("apology_shorten", 0.6))
        self.comfort_shorten = float(cfg.get("comfort_shorten", 0.8))
        self.comfort_cooldown_min = float(cfg.get("comfort_cooldown_min", 10))
        self.floor_pad = float(cfg.get("floor_pad", 1))

        # 档位显示名：按"她能怎么好"命名，默认哄得动 / 要认错 / 要时间
        self.names = {"mild": "有点小情绪", "mid": "还在赌气", "big": "气还没消", "none": "没事"}
        for k, v in (cfg.get("tier_names") or {}).items():
            self.names[str(k)] = str(v)

        self.affinity = float(cfg.get("init_affinity", 50))
        self.trust = float(cfg.get("init_trust", 60))
        self.grievance = float(cfg.get("init_grievance", 0))

        # 解锁状态
        self.apology_seen = False
        self.comfort_seen = False
        self.calm_until = 0.0
        self.last_comfort_at = 0.0

    # ---------- 档位 ----------
    @property
    def tier(self) -> str:
        if self.grievance >= self.big:
            return "big"
        if self.grievance >= self.mid:
            return "mid"
        if self.grievance >= self.mild:
            return "mild"
        return "none"

    def floor(self, now: float) -> float:
        """当前档位下，光靠时间最多能降到哪儿。"""
        tier = self.tier
        if tier == "big":
            if now >= self.calm_until > 0:
                return 0.0
            return self.big + self.floor_pad
        if tier == "mid":
            if self.apology_seen and self.comfort_seen:
                return 0.0
            return self.mid + self.floor_pad
        return 0.0

    def cool_left_h(self, now: float) -> float:
        return round(max(0.0, self.calm_until - now) / 3600.0, 1)

    # ---------- 演化 ----------
    def decay(self, seconds: float, now: float) -> None:
        if seconds <= 0 or self.grievance <= 0:
            return
        fl = self.floor(now)
        g = self.grievance * 0.5 ** (seconds / max(1.0, self.hl_min * 60.0))
        self.grievance = max(g, fl)
        if fl <= 0 and self.grievance <= 0.5:
            self.grievance = 0.0
            self._clear()

    def apply(self, deltas: dict, now: float) -> None:
        if not deltas:
            return
        if "affinity" in deltas:
            self.affinity = _clamp(self.affinity + float(deltas["affinity"]))
        if "trust" in deltas:
            self.trust = _clamp(self.trust + float(deltas["trust"]))
        if "grievance" in deltas:
            before = self.tier
            self.grievance = _clamp(self.grievance + float(deltas["grievance"]))
            # 刚跨进大生气：开始冷静倒计时
            if self.tier == "big" and before != "big":
                self.calm_until = now + self.calm_hours * 3600.0
                self.apology_seen = False
                self.comfort_seen = False

    def note(self, tags, now: float) -> None:
        """记录"道歉过/哄过"，大生气时顺便缩短冷静时间。"""
        tags = tags or []
        if "apology" in tags:
            if self.tier == "big" and not self.apology_seen:
                self._shorten(now, self.apology_shorten)
            self.apology_seen = True
        if "care" in tags:
            if self.tier == "big" and not self.comfort_seen:
                self._shorten(now, self.comfort_shorten)
            self.comfort_seen = True

    def _shorten(self, now: float, factor: float) -> None:
        if not self.calm_until:
            return
        left = max(0.0, self.calm_until - now)
        new_left = min(max(left * factor, self.calm_min_hours * 3600.0), left)
        self.calm_until = now + new_left

    def comfort_ready(self, now: float) -> bool:
        return now - self.last_comfort_at >= self.comfort_cooldown_min * 60.0

    def mark_comfort(self, now: float) -> None:
        self.last_comfort_at = now

    def _clear(self) -> None:
        self.apology_seen = False
        self.comfort_seen = False
        self.calm_until = 0.0

    # ---------- 读出 ----------
    @property
    def mood(self) -> str:
        return {"none": "normal", "mild": "slight", "mid": "sulky", "big": "cold"}[self.tier]

    @property
    def tone(self) -> str:
        if self.tier in ("mid", "big"):
            return "cool"
        if self.affinity >= 70:
            return "warm"
        return "neutral"

    def hint(self, now: float) -> str:
        tier = self.tier
        if tier == "none":
            return ""
        if tier == "mild":
            return "哄一哄就好"
        if tier == "mid":
            need = []
            if not self.apology_seen:
                need.append("道歉")
            if not self.comfort_seen:
                need.append("哄")
            return "还差：" + " + ".join(need) if need else "哄好了"
        left = self.cool_left_h(now)
        return f"还要冷静 {int(round(left))}h" if left > 0 else "冷静完了"

    def tier_range(self) -> str:
        """这一档的数值范围，面板上直接写出来，不让人猜。"""
        if self.tier == "mild":
            return f"{self.mild:.0f}~{self.mid - 1:.0f}"
        if self.tier == "mid":
            return f"{self.mid:.0f}~{self.big - 1:.0f}"
        if self.tier == "big":
            return f"{self.big:.0f}~100"
        return ""

    def to_dict(self, now: float) -> dict:
        return {
            "affinity": round(self.affinity, 1),
            "trust": round(self.trust, 1),
            "grievance": round(self.grievance, 1),
            "mood": self.mood,
            "tier": self.tier,
            "tier_name": self.names.get(self.tier, "没事"),
            "tier_range": self.tier_range(),
            "tone": self.tone,
            "floor": round(self.floor(now), 1),
            "cool_left_h": self.cool_left_h(now),
            "apology_seen": self.apology_seen,
            "comfort_seen": self.comfort_seen,
            "hint": self.hint(now),
        }

    def save(self) -> dict:
        return {
            "affinity": self.affinity,
            "trust": self.trust,
            "grievance": self.grievance,
            "apology_seen": self.apology_seen,
            "comfort_seen": self.comfort_seen,
            "calm_until": self.calm_until,
            "last_comfort_at": self.last_comfort_at,
        }

    def load(self, data: dict) -> None:
        data = data or {}
        self.affinity = float(data.get("affinity", self.affinity))
        self.trust = float(data.get("trust", self.trust))
        self.grievance = float(data.get("grievance", self.grievance))
        self.apology_seen = bool(data.get("apology_seen", False))
        self.comfort_seen = bool(data.get("comfort_seen", False))
        self.calm_until = float(data.get("calm_until", 0.0))
        self.last_comfort_at = float(data.get("last_comfort_at", 0.0))


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))