"""情绪状态：离散标签做主，PAD 连续维度做平滑，半衰期衰减。

文档 §4.1：
    E(t) = baseline + (E0 - baseline) * 0.5 ** (Δt / half_life)

标签强度向 0 衰减（没有永久情绪），PAD 向 baseline 回归。
"""
from __future__ import annotations

# 每个离散标签的 PAD 锚点（pleasure, arousal, dominance）
PAD_ANCHOR = {
    "calm": (0.10, 0.30, 0.50),
    "joyful": (0.70, 0.60, 0.50),
    "excited": (0.60, 0.85, 0.55),
    "playful": (0.60, 0.60, 0.60),
    "affectionate": (0.70, 0.35, 0.45),
    "shy": (0.40, 0.45, 0.30),
    "sad": (-0.60, 0.25, 0.25),
    "disappointed": (-0.50, 0.30, 0.30),
    "angry": (-0.60, 0.80, 0.60),
    "annoyed": (-0.40, 0.55, 0.50),
    "tired": (-0.20, 0.15, 0.35),
    "bored": (-0.30, 0.20, 0.40),
    "worried": (-0.40, 0.55, 0.30),
    "nostalgic": (0.20, 0.30, 0.45),
}

# 文档 §4.1 的半衰期（分钟）；未列出的标签用 90
DEFAULT_HALF_LIFE = {
    "angry": 25,
    "annoyed": 40,
    "joyful": 60,
    "excited": 90,
    "playful": 70,
    "shy": 45,
    "sad": 240,
    "disappointed": 360,
    "affectionate": 720,
    "worried": 120,
    "nostalgic": 300,
    "bored": 90,
    "tired": 120,
    "calm": 60,
}

DEFAULT_BASELINE = {"pleasure": 0.15, "arousal": 0.35, "dominance": 0.5}


class Emotion:
    def __init__(self, baseline=None, half_life=None, max_delta=0.4, calm_threshold=0.12):
        self.baseline = dict(baseline or DEFAULT_BASELINE)
        self.half_life = dict(DEFAULT_HALF_LIFE)
        self.half_life.update(half_life or {})
        self.max_delta = float(max_delta)
        self.calm_threshold = float(calm_threshold)
        self.levels = {}  # label -> 0..1

    # ---- 演化 ----
    def decay(self, seconds: float) -> None:
        if seconds <= 0:
            return
        for label, v in list(self.levels.items()):
            hl = max(1.0, float(self.half_life.get(label, 90))) * 60.0
            nv = v * 0.5 ** (seconds / hl)
            if nv < 0.01:
                self.levels.pop(label, None)
            else:
                self.levels[label] = nv

    def add(self, label: str, delta: float) -> float:
        """单次增量受 max_delta 限制（防一句重话把状态打穿）。"""
        label = str(label)
        delta = max(-self.max_delta, min(self.max_delta, float(delta)))
        v = max(0.0, min(1.0, self.levels.get(label, 0.0) + delta))
        if v < 0.01:
            self.levels.pop(label, None)
        else:
            self.levels[label] = v
        return v

    # ---- 读出 ----
    @property
    def label(self) -> str:
        if not self.levels:
            return "calm"
        label, v = max(self.levels.items(), key=lambda kv: kv[1])
        return label if v >= self.calm_threshold else "calm"

    @property
    def peak(self) -> float:
        return max(self.levels.values()) if self.levels else 0.0

    @property
    def intensity(self) -> float:
        """当前主情绪强度；平静时取所有残余里的最大值（用于展示"她有多平静"）。"""
        return round(self.peak if self.label != "calm" else min(self.peak, self.calm_threshold), 4)

    def pad(self):
        total = min(1.0, sum(self.levels.values()))
        if total < 1e-6:
            return [round(self.baseline[k], 3) for k in ("pleasure", "arousal", "dominance")]
        norm = sum(self.levels.values())
        out = []
        for i, dim in enumerate(("pleasure", "arousal", "dominance")):
            avg = sum(PAD_ANCHOR.get(lab, (0.1, 0.3, 0.5))[i] * v for lab, v in self.levels.items()) / norm
            out.append(round(self.baseline[dim] * (1 - total) + avg * total, 3))
        return out

    def to_dict(self) -> dict:
        return {"intensity": {k: round(v, 4) for k, v in self.levels.items()}}

    @classmethod
    def from_dict(cls, data, **kw):
        obj = cls(**kw)
        obj.levels = {k: float(v) for k, v in (data or {}).get("intensity", {}).items()}
        return obj