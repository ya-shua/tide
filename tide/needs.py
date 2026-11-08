"""需求（needs）：0~100，越高越缺。

文档 §4.2：
- hunger 饥饿  +18/h，吃饭回落
- thirst 口渴  +24/h，喝水回落（比饿得快一点，人也是先渴后饿）
- energy 精力 +12/h，深夜 ×1.6（"越高越缺" = 疲劳度）
- boredom 无聊 +20/h，聊天/刷视频回落
- longing 思念 随无互动时长非线性上升：100*(1-exp(-idle_hours/tau))
  tau = 6h，affinity 越高 tau 越小（越亲近越容易想你）

**她大部分时间自己会照顾自己**（AUTO_CARE）：
渴到一定程度自己去倒水，饿了自己找吃的，困了打个盹，无聊了刷会儿视频。
所以这几样会自己回落，不需要有人盯着喂。
只有 longing 自己解决不了——那是"想你"，只能等人。
"""
from __future__ import annotations

import math

# 自理：涨到这个数，她自己就去处理了；处理完回落到 to
AUTO_CARE = {
    "thirst": {"at": 78.0, "to": 22.0, "note": "倒了杯水喝"},
    "hunger": {"at": 80.0, "to": 20.0, "note": "吃了点东西"},
    "energy": {"at": 84.0, "to": 26.0, "note": "打了个盹"},
    "boredom": {"at": 78.0, "to": 28.0, "note": "刷了会儿视频",
                # 无聊有好几种解法：轮到哪个算哪个（不打乱顺序，测试才稳定）
                "notes": ["刷了会儿视频", "听了会儿歌", "出去走了走",
                          "翻了翻以前的聊天记录", "找人随便聊了两句"]},
}

STEP_SEC = 300.0  # 5 分钟一段：一次推进 20 小时也要按顺序发生，不能一步跳过去


class Needs:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.hunger_rate = float(cfg.get("hunger_per_hour", 18))
        self.thirst_rate = float(cfg.get("thirst_per_hour", 24))
        self.energy_rate = float(cfg.get("energy_per_hour", 12))
        self.night_mult = float(cfg.get("energy_night_multiplier", 1.6))
        self.boredom_rate = float(cfg.get("boredom_per_hour", 20))
        self.tau_hours = float(cfg.get("longing_tau_hours", 6.0))
        self.affinity_boost = float(cfg.get("longing_affinity_boost", 0.8))
        # 表达缓解：她开口之后，想念暂停上涨这么久（分钟）
        self.hold_min = float(cfg.get("hold_min", 120.0))
        # 想念是个存量：自己慢慢涨，被回应按"这句有多实"往下削，
        # 削完还会接着涨——不会因为你回了个"嗯"就不想你了。
        self.longing_value = 0.0
        self.longing_at = 0.0

        self.hunger = float(cfg.get("init_hunger", 10))
        self.thirst = float(cfg.get("init_thirst", 12))
        self.energy = float(cfg.get("init_energy", 20))
        self.boredom = float(cfg.get("init_boredom", 20))
        self.last_seen = 0.0  # 上一次互动的时间戳
        self.last_tick = 0.0
        # 缓解期（她开口后的冻结窗口）与余温
        self.hold_until = 0.0
        self.hold_value = 0.0

        # 配置里可以调阈值；不配就用默认
        self.auto = {k: dict(v) for k, v in AUTO_CARE.items()}
        for key, val in (cfg.get("auto_care") or {}).items():
            if key in self.auto and isinstance(val, dict):
                self.auto[key].update(val)

        self.care_log = []  # 最近一次推进里她为自己做了什么
        self.last_peak_boredom = self.boredom
        self.boredom_care_count = 0

    # ---- 演化 ----
    def advance(self, seconds: float, night: bool, asleep: bool = False,
                recover_per_hour: float = 16.0) -> None:
        """asleep=True 时她真的在睡：疲惫快速下降，饿/渴慢下来，不会自己起来找事做。"""
        if seconds <= 0:
            return
        self.last_peak_boredom = max(self.last_peak_boredom, self.boredom)
        if asleep:
            hours = float(seconds) / 3600.0
            self.energy = _clamp(self.energy - recover_per_hour * hours)
            self.hunger = _clamp(self.hunger + self.hunger_rate * 0.25 * hours)
            self.thirst = _clamp(self.thirst + self.thirst_rate * 0.25 * hours)
            return
        remaining = float(seconds)
        while remaining > 1e-9:
            step = min(STEP_SEC, remaining)
            remaining -= step
            hours = step / 3600.0
            self.hunger = _clamp(self.hunger + self.hunger_rate * hours)
            self.thirst = _clamp(self.thirst + self.thirst_rate * hours)
            mult = self.night_mult if night else 1.0
            self.energy = _clamp(self.energy + self.energy_rate * hours * mult)
            self.boredom = _clamp(self.boredom + self.boredom_rate * hours)
            self.last_peak_boredom = max(self.last_peak_boredom, self.boredom)
            for note in self._self_care():
                self.care_log.append(note)
                if len(self.care_log) > 12:
                    self.care_log = self.care_log[-12:]

    def _self_care(self) -> list:
        """她自己解决掉的那几样；返回这次做了什么。"""
        done = []
        for key, rule in self.auto.items():
            if getattr(self, key) >= float(rule["at"]):
                setattr(self, key, _clamp(float(rule["to"])))
                notes = rule.get("notes")
                if notes:
                    # 无聊的解法轮着来，不要每次都是"刷视频"
                    note = notes[self.boredom_care_count % len(notes)]
                    self.boredom_care_count += 1
                    done.append(note)
                else:
                    done.append(rule["note"])
        return done

    def _tau(self, affinity: float) -> float:
        return self.tau_hours * max(0.3, 1.4 - self.affinity_boost * (affinity / 100.0))

    def _value_at(self, now: float, affinity: float) -> float:
        """现在的想念：缓解期里冻结，缓解期结束从冻结值接着涨。"""
        if self.hold_until:
            if now < self.hold_until:
                return self.hold_value
            hours = max(0.0, (now - self.hold_until) / 3600.0)
            return 100.0 - (100.0 - self.hold_value) * math.exp(-hours / self._tau(affinity))
        anchor = self.longing_at or self.last_seen
        if not anchor:
            return self.longing_value
        hours = max(0.0, (now - anchor) / 3600.0)
        return 100.0 - (100.0 - self.longing_value) * math.exp(-hours / self._tau(affinity))

    def longing(self, now: float, affinity: float) -> float:
        return round(_clamp(self._value_at(now, affinity)), 1)

    def spoke(self, now: float, affinity: float) -> None:
        """她主动开口了：想念不降，但从现在起暂停上涨（缓解期）。"""
        self.longing_value = self._value_at(now, affinity)
        self.longing_at = now
        self.hold_value = _clamp(self.longing_value)
        self.hold_until = now + self.hold_min * 60.0

    def touched(self, now: float, affinity: float = 0.0, quality: float = 0.06) -> None:
        """你回了一句：按这句有多"实"削一点；没聊够的，剩下的会自己涨回来。

        敷衍一句（"嗯"）只削几个点，真聊一场才削得多。
        """
        cur = self._value_at(now, affinity)
        cut = min(cur * 0.6, max(0.06, quality) * 70.0)
        self.longing_value = _clamp(cur - cut)
        self.longing_at = now
        self.last_seen = now
        self.boredom = _clamp(self.boredom - 25.0)
        # 刚聊完有个"缓一缓"：聊得越多，缓得越久（不是固定时长）
        grace_min = min(240.0, cut * 6.0)
        if grace_min >= 1.0:
            self.hold_value = self.longing_value
            self.hold_until = now + grace_min * 60.0
        else:
            self.hold_until = 0.0
            self.hold_value = 0.0
        return round(cur - self.longing_value, 1)

    def apply(self, deltas: dict) -> None:
        for key, val in (deltas or {}).items():
            if key == "hunger":
                self.hunger = _clamp(self.hunger + float(val))
            elif key == "thirst":
                self.thirst = _clamp(self.thirst + float(val))
            elif key == "energy":
                self.energy = _clamp(self.energy + float(val))
            elif key == "boredom":
                self.boredom = _clamp(self.boredom + float(val))

    # ---- 读出 ----
    def to_dict(self, now: float, affinity: float) -> dict:
        return {
            "hunger": round(self.hunger, 1),
            "thirst": round(self.thirst, 1),
            "energy": round(self.energy, 1),
            "longing": self.longing(now, affinity),
            "boredom": round(self.boredom, 1),
        }

    def save(self) -> dict:
        return {
            "hunger": self.hunger,
            "thirst": self.thirst,
            "energy": self.energy,
            "boredom": self.boredom,
            "last_seen": self.last_seen,
            "hold_until": self.hold_until,
            "hold_value": self.hold_value,
            "longing_value": self.longing_value,
            "longing_at": self.longing_at,
        }

    def load(self, data: dict) -> None:
        data = data or {}
        self.hunger = float(data.get("hunger", self.hunger))
        self.thirst = float(data.get("thirst", self.thirst))
        self.energy = float(data.get("energy", self.energy))
        self.boredom = float(data.get("boredom", self.boredom))
        self.last_seen = float(data.get("last_seen", 0.0))
        self.hold_until = float(data.get("hold_until", 0.0))
        self.hold_value = float(data.get("hold_value", 0.0))
        self.longing_value = float(data.get("longing_value", 0.0))
        self.longing_at = float(data.get("longing_at", 0.0))
        # 旧状态没有存量：用"距上次互动多久"补一个起点，别让她一觉醒来归零
        if not self.longing_at and self.last_seen:
            self.longing_at = self.last_seen
            self.longing_value = 0.0
        self.comfort = float(data.get("comfort", 0.0))
        self.comfort_at = float(data.get("comfort_at", 0.0))


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))