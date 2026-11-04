"""生物钟：几点睡不是墙上写死的，由"累不累"决定。

设计要点：
1. **入睡时间跟着疲惫走**：越累睡得越早（最早 21:30），不累就往后拖（最晚次日 02:00）
2. **睡多久也跟疲惫走**：6~9 小时，累得越狠睡得越久
3. **睡着 ≠ 不回复**：睡着了被消息叫醒，她会醒，而且带着起床气；
   睡不到一个半小时（或凌晨 2~5 点）被叫醒，起床气更重。后续接语音时，
   这两个状态可以直接换成"被吵醒的沙哑语气 / 不高兴的语气"。
4. **午觉**：白天累到 85 以上，且人在 13:00~16:30，会自己眯一会儿。
"""
from __future__ import annotations

import time as _time

DEFAULTS = {
    "normal_onset": 23.5,      # 平时 23:30 睡
    "earliest_onset": 21.5,    # 累狠了最早 21:30
    "latest_onset": 26.0,      # 不累最晚到次日 02:00
    "min_hours": 6.0,          # 最少睡 6 小时
    "max_hours": 9.0,          # 最多 9 小时
    "recover_per_hour": 16.0,  # 睡着以后疲惫每小时降多少（100 分制）
    "deep_sleep_min": 1.5,     # 睡够这么久才算"睡沉了"，被叫醒会比较不高兴
    "nap_window": [13.0, 16.5],
    "nap_tired": 85.0,
    "nap_hours": 0.75,
    "wake_block_min": 12.0,    # 被叫醒后这段时间不会再自己睡回去
}

# 凌晨这几个小时被吵醒，起床气最重
HARD_WAKE_HOURS = (1.0, 5.5)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _in_window(h: float, start: float, end: float) -> bool:
    """小时数是否落在 [start, end) 这个环形区间里。"""
    if start <= end:
        return start <= h < end
    return h >= start or h < end


def hour_of(ts: float) -> float:
    """本地时间的小时数（含小数），用来判断作息。"""
    t = _time.localtime(ts)
    return t.tm_hour + t.tm_min / 60.0


class Circadian:
    def __init__(self, cfg=None):
        cfg = dict(DEFAULTS)
        cfg.update(cfg or {})
        self.cfg = cfg
        self.asleep = False
        self.since = 0.0
        self.plan_hours = 0.0
        self.is_nap = False
        self.block_sleep_until = 0.0
        self.woken_at = 0.0
        self.woken_hard = False
        self.last_event = ""

    # ---------- 推算 ----------
    def onset_hour(self, energy: float) -> float:
        """越累睡得越早；energy 是疲惫度（越高越累）。"""
        c = self.cfg
        shift = (50.0 - float(energy)) / 50.0 * 1.5   # 很累 -1.5h，不累 +1.5h
        return _clamp(c["normal_onset"] + shift, c["earliest_onset"], c["latest_onset"])

    def plan_sleep(self, energy: float) -> float:
        c = self.cfg
        h = c["min_hours"] + (float(energy) / 100.0) * (c["max_hours"] - c["min_hours"])
        return round(_clamp(h, c["min_hours"], c["max_hours"]), 2)

    def slept_hours(self, now: float) -> float:
        return round(max(0.0, now - self.since) / 3600.0, 2) if self.since else 0.0

    def should_fall_asleep(self, now: float, energy: float) -> bool:
        if self.asleep or now < self.block_sleep_until:
            return False
        if energy < 35:
            return False           # 不困就是睡不着，别按墙上时间硬睡
        h = hour_of(now)
        # 入睡窗口：从入睡点起算，最长睡满上限就醒（跨零点要按环形算）
        start = self.onset_hour(energy) % 24.0
        end = (start + self.cfg["max_hours"]) % 24.0
        if _in_window(h, start, end):
            return True
        # 午觉
        lo, hi = self.cfg["nap_window"]
        return lo <= h <= hi and energy >= self.cfg["nap_tired"]

    def should_wake(self, now: float, energy: float) -> bool:
        if not self.asleep:
            return False
        if self.slept_hours(now) >= self.plan_hours:
            return True
        return energy <= 8.0   # 睡饱了

    # ---------- 推进 ----------
    def step(self, chunk_sec: float, now: float, energy: float) -> list:
        """推进一小段，返回这段时间里发生的事（入睡/醒来）。"""
        events = []
        if self.asleep:
            if self.should_wake(now, energy):
                slept = self.slept_hours(now)
                self.asleep = False
                self.last_event = "wake"
                events.append(("wake", slept))
                self.since = 0.0
                self.is_nap = False
                self.plan_hours = 0.0
        elif self.should_fall_asleep(now, energy):
            self.asleep = True
            self.since = now
            h = hour_of(now)
            lo, hi = self.cfg["nap_window"]
            self.is_nap = lo <= h <= hi and energy >= self.cfg["nap_tired"]
            self.plan_hours = (self.cfg["nap_hours"] if self.is_nap
                               else self.plan_sleep(energy))
            self.last_event = "sleep"
            events.append(("nap" if self.is_nap else "sleep", self.plan_hours))
        return events

    # ---------- 被吵醒 ----------
    def wake_by_message(self, now: float) -> dict | None:
        """睡着时收到消息：会醒，而且不一定高兴。"""
        if not self.asleep:
            return None
        slept = self.slept_hours(now)
        h = hour_of(now)
        deep = slept >= self.cfg["deep_sleep_min"]
        hard = (not deep) or (HARD_WAKE_HOURS[0] <= h <= HARD_WAKE_HOURS[1])
        self.asleep = False
        self.since = 0.0
        self.plan_hours = 0.0
        self.is_nap = False
        self.woken_at = now
        self.woken_hard = hard
        self.block_sleep_until = now + self.cfg["wake_block_min"] * 60.0
        self.last_event = "woken"
        return {"slept_h": slept, "hard": hard, "hour": round(h, 2)}

    # ---------- 存档 ----------
    def state(self, now: float) -> dict:
        return {
            "asleep": self.asleep,
            "since": self.since,
            "slept_h": self.slept_hours(now),
            "plan_hours": self.plan_hours,
            "is_nap": self.is_nap,
            "woken": bool(self.woken_at) and (now - self.woken_at) < 3 * 3600,
            "woken_hard": self.woken_hard,
            "onset_hour": round(self.onset_hour(50.0), 1),
        }

    def save(self) -> dict:
        return {"asleep": self.asleep, "since": self.since,
                "plan_hours": self.plan_hours, "is_nap": self.is_nap,
                "block_sleep_until": self.block_sleep_until,
                "woken_at": self.woken_at, "woken_hard": self.woken_hard}

    def load(self, data: dict) -> None:
        data = data or {}
        self.asleep = bool(data.get("asleep", False))
        self.since = float(data.get("since", 0.0))
        self.plan_hours = float(data.get("plan_hours", 0.0))
        self.is_nap = bool(data.get("is_nap", False))
        self.block_sleep_until = float(data.get("block_sleep_until", 0.0))
        self.woken_at = float(data.get("woken_at", 0.0))
        self.woken_hard = bool(data.get("woken_hard", False))