"""设置：面板上能改的那些数。

存 `data/settings.json`（覆盖 config/*.yaml 里的默认值），改完立刻生效，
不用重启面板。范围都夹在合理区间里——面板是给自己用的，不该让手滑把
冷静期改成负数。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# 键 -> (中文名, 类型, 最小, 最大, 步进, 分组, 单位)
FIELDS = {
    "name":        ("名字", "text", 0, 0, 0, "角色", ""),
    "person":      ("怎么叫你", "text", 0, 0, 0, "角色", ""),
    "tier_mild":   ("有点小情绪的门槛", "num", 5, 60, 1, "脾气", ""),
    "tier_mid":    ("还在赌气的门槛", "num", 10, 85, 1, "脾气", ""),
    "tier_big":    ("气还没消的门槛", "num", 20, 100, 1, "脾气", ""),
    "calm_hours":  ("大生气要冷静多久", "num", 0.5, 72, 0.5, "脾气", "小时"),
    "comfort_cooldown_min": ("哄一次之后多久能再算数", "num", 1, 120, 1, "脾气", "分钟"),
    "quiet_start": ("安静开始", "time", 0, 0, 0, "节奏", ""),
    "quiet_end":   ("安静结束", "time", 0, 0, 0, "节奏", ""),
    "sleep_normal":  ("平时几点睡", "time", 0, 0, 0, "作息", ""),
    "sleep_earliest": ("累狠了最早几点睡", "time", 0, 0, 0, "作息", ""),
    "sleep_latest":  ("心里有事最晚几点睡", "time", 0, 0, 0, "作息", ""),
    "sleep_mood_delay": ("情绪最晚能拖多久", "num", 0, 4, 0.5, "作息", "小时"),
    "sleep_min_h":   ("最少睡多久", "num", 3, 10, 0.5, "作息", "小时"),
    "sleep_max_h":   ("最多睡多久", "num", 4, 12, 0.5, "作息", "小时"),
    "proactive_threshold": ("主动开口的门槛", "num", 10, 150, 5, "主动", ""),
    "proactive_cooldown_min": ("两条主动消息至少隔", "num", 5, 480, 5, "主动", "分钟"),
    "proactive_max_unanswered": ("连发几条没回就停", "num", 1, 5, 1, "主动", "条"),
    "wake_longing": ("想念到多少就叫醒她", "num", 20, 100, 5, "主动", ""),
    "wake_boredom": ("无聊到多少就叫醒她", "num", 20, 100, 5, "主动", ""),
    "wake_worried": ("担心到多少就叫醒她", "num", 20, 100, 5, "主动", ""),
    "wake_auto_dnd_after": ("几条没回就当你在忙", "num", 0, 10, 1, "主动", "条，0 关闭"),
    "wake_max": ("一天最多叫醒几次", "num", 0, 50, 1, "主动", "0 不限"),
    "wake_hold_min": ("开口后想念停涨多久", "num", 0, 720, 10, "主动", "分钟"),
    "wake_cooldown_min": ("两次叫醒至少隔", "num", 5, 480, 5, "主动", "分钟"),
    "wake_cooldown_mode": ("冷却怎么变", "text", 0, 0, 0, "主动", "dec 递减 / fixed 固定 / inc 递增"),
    "memory_quote_hours": ("记得原话保留多久", "num", 0, 168, 1, "记忆", "小时"),
    "refresh_ms":  ("面板刷新间隔", "num", 500, 10000, 500, "面板", "毫秒"),
    "update_repo": ("更新检查的仓库", "text", 0, 0, 0, "面板", "owner/repo，留空就不查"),
}

DEFAULTS = {
    "name": "Tide",
    "person": "主人",
    "tier_mild": 15,
    "tier_mid": 35,
    "tier_big": 65,
    "calm_hours": 6,
    "comfort_cooldown_min": 10,
    "quiet_start": "00:30",
    "quiet_end": "07:30",
    "sleep_normal": "23:30",
    "sleep_earliest": "21:30",
    "sleep_latest": "02:00",
    "sleep_mood_delay": 2,
    "sleep_min_h": 6,
    "sleep_max_h": 9,
    "proactive_threshold": 60,
    "proactive_cooldown_min": 90,
    "proactive_max_unanswered": 2,
    "wake_longing": 60,
    "wake_boredom": 60,
    "wake_worried": 70,
    "wake_auto_dnd_after": 3,
    "wake_max": 6,
    "wake_hold_min": 120,
    "wake_cooldown_min": 90,
    "wake_cooldown_mode": "dec",
    "memory_quote_hours": 12,
    "refresh_ms": 2000,
    "update_repo": "",
}

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.data = dict(DEFAULTS)

    # ---------- 读写 ----------
    def load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            self.data.update({k: v for k, v in raw.items() if k in FIELDS})

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)

    # ---------- 校验 ----------
    def coerce(self, key: str, value):
        spec = FIELDS.get(key)
        if spec is None:
            raise KeyError(f"没有这个设置：{key}")
        _, kind, lo, hi, _, _, _ = spec
        if kind == "text":
            text = str(value).strip()
            if not text:
                raise ValueError(f"{spec[0]}不能是空的")
            return text[:24]
        if kind == "time":
            text = str(value).strip()
            if not _TIME_RE.match(text):
                raise ValueError(f"{spec[0]}要写成 HH:MM")
            return text.zfill(5)
        num = float(value)
        if num != num:  # NaN
            raise ValueError(f"{spec[0]}不是数字")
        num = max(float(lo), min(float(hi), num))
        return int(num) if num == int(num) else round(num, 2)

    def update(self, patch: dict) -> dict:
        """整批校验：有一条不合法就全部不改。"""
        clean = {}
        for key, value in (patch or {}).items():
            clean[str(key)] = self.coerce(str(key), value)
        # 门槛必须递增，否则档位会错乱
        mild = clean.get("tier_mild", self.data["tier_mild"])
        mid = clean.get("tier_mid", self.data["tier_mid"])
        big = clean.get("tier_big", self.data["tier_big"])
        if not (mild < mid < big):
            raise ValueError("三个门槛要依次变大：小情绪 < 赌气 < 气还没消")
        mode = str(clean.get("wake_cooldown_mode", self.data.get("wake_cooldown_mode", "dec"))).lower()
        if mode not in ("dec", "fixed", "inc"):
            raise ValueError("冷却模式只能是 dec（递减）/ fixed（固定）/ inc（递增）")
        clean["wake_cooldown_mode"] = mode
        lo = clean.get("sleep_min_h", self.data.get("sleep_min_h", 6))
        hi = clean.get("sleep_max_h", self.data.get("sleep_max_h", 9))
        if lo > hi:
            raise ValueError("最少睡多久不能比最多还大")
        self.data.update(clean)
        self.save()
        return dict(self.data)

    # ---------- 视图 ----------
    def public(self) -> dict:
        return {
            "values": dict(self.data),
            "fields": [
                {"key": k, "label": v[0], "kind": v[1], "min": v[2],
                 "max": v[3], "step": v[4], "group": v[5], "unit": v[6]}
                for k, v in FIELDS.items()
            ],
        }