"""情绪状态：七情账户 + 小标签明细 + 总和恒等 100。

和旧版的区别（2026-11-07 定）：

- 旧：每个标签独立 0~1，自己衰减到 0，总和可以变成 0（"没有情绪"）。
- 新：所有情绪加起来**永远是 100%**，情绪不会消失，只会转移。
  降下去的那部分按转移表分给"平静"和相关情绪（生气 → 平静 + 后悔 + 难过）。

两层结构：

    七情（账户，加起来 100）   小标签（明细，给说话用）
    喜 · 怒 · 忧 · 思 · 悲 · 恐 · 惊 · 平静

    "怒 30" 里面可能是 生气 20 + 嫉妒 10；
    对外只说"生气""嫉妒"，账本在内部。

内部用小数（0~1），显示乘 100 取整。
"""
from __future__ import annotations

# 七情账户（平静是默认池子，不是"没有情绪"）
SEVEN = ("joy", "anger", "worry", "longing", "sorrow", "fear", "surprise", "calm")

SEVEN_LABEL = {
    "joy": "喜", "anger": "怒", "worry": "忧", "longing": "思",
    "sorrow": "悲", "fear": "恐", "surprise": "惊", "calm": "平静",
}

# 每个小标签：属于哪一情、PAD 锚点、半衰期（分钟）
LABELS = {
    # 喜
    "joyful":       ("joy",      (0.70, 0.60, 0.50), 60),
    "excited":      ("joy",      (0.60, 0.85, 0.55), 90),
    "playful":      ("joy",      (0.60, 0.60, 0.60), 70),
    "proud":        ("joy",      (0.65, 0.65, 0.70), 60),
    "grateful":     ("joy",      (0.70, 0.45, 0.45), 300),
    "hopeful":      ("joy",      (0.50, 0.55, 0.55), 180),
    "affectionate": ("joy",      (0.70, 0.35, 0.45), 720),
    # 怒
    "angry":        ("anger",    (-0.60, 0.80, 0.60), 25),
    "annoyed":      ("anger",    (-0.40, 0.55, 0.50), 40),
    "jealous":      ("anger",    (-0.45, 0.65, 0.45), 180),
    # 忧
    "worried":      ("worry",    (-0.40, 0.55, 0.30), 120),
    "uneasy":       ("worry",    (-0.30, 0.45, 0.35), 150),
    # 思
    "nostalgic":    ("longing",  (0.20, 0.30, 0.45), 300),
    "yearning":     ("longing",  (0.05, 0.45, 0.35), 240),
    # 悲
    "sad":          ("sorrow",   (-0.60, 0.25, 0.25), 240),
    "disappointed": ("sorrow",   (-0.50, 0.30, 0.30), 360),
    "lonely":       ("sorrow",   (-0.45, 0.20, 0.30), 200),
    # 恐
    "scared":       ("fear",     (-0.55, 0.65, 0.20), 60),
    "guilty":       ("fear",     (-0.35, 0.45, 0.25), 90),
    "shy":          ("fear",     (0.40, 0.45, 0.30), 45),
    # 惊
    "surprised":    ("surprise", (0.10, 0.80, 0.40), 20),
    "embarrassed":  ("surprise", (-0.25, 0.55, 0.20), 40),
    # 状态
    "tired":        ("calm",     (-0.20, 0.15, 0.35), 120),
    "bored":        ("calm",     (-0.30, 0.20, 0.40), 90),
}

CALM = "calm"

# 兼容旧名字（老测试/旧代码 import 过 PAD_ANCHOR）
PAD_ANCHOR = {k: v[1] for k, v in LABELS.items()}

# 转移表：这个情绪降下去的部分，按比例分给谁（没写的标签 100% 回平静）
DEFAULT_TRANSFER = {
    "angry":        [("calm", 0.55), ("guilty", 0.30), ("sad", 0.15)],
    "annoyed":      [("calm", 0.65), ("angry", 0.10), ("sad", 0.25)],
    "jealous":      [("calm", 0.40), ("sad", 0.35), ("annoyed", 0.25)],
    "worried":      [("calm", 0.70), ("sad", 0.30)],
    "uneasy":       [("calm", 0.75), ("worried", 0.25)],
    "sad":          [("calm", 0.70), ("disappointed", 0.30)],
    "disappointed": [("calm", 0.60), ("sad", 0.40)],
    "lonely":       [("calm", 0.50), ("sad", 0.50)],
    "guilty":       [("calm", 0.55), ("shy", 0.25), ("sad", 0.20)],
    "scared":       [("calm", 0.65), ("worried", 0.35)],
    "embarrassed":  [("calm", 0.60), ("shy", 0.40)],
    "shy":          [("calm", 0.85), ("joyful", 0.15)],
    "proud":        [("calm", 0.85), ("joyful", 0.15)],
    "joyful":       [("calm", 1.0)],
    "excited":      [("calm", 0.90), ("joyful", 0.10)],
    "playful":      [("calm", 1.0)],
    "grateful":     [("calm", 0.80), ("joyful", 0.20)],
    "affectionate": [("calm", 0.85), ("grateful", 0.15)],
    "hopeful":      [("calm", 1.0)],
    "nostalgic":    [("calm", 0.80), ("sad", 0.20)],
    "yearning":     [("calm", 0.50), ("sad", 0.50)],
    "surprised":    [("calm", 1.0)],
    "tired":        [("calm", 1.0)],
    "bored":        [("calm", 0.80), ("annoyed", 0.20)],
}

DEFAULT_BASELINE = {"pleasure": 0.15, "arousal": 0.35, "dominance": 0.5}

EPS = 1e-9


class Emotion:
    """守恒情绪：levels 里所有标签之和恒为 1.0，calm 是默认池子。"""

    def __init__(self, baseline=None, half_life=None, max_delta=0.4,
                 calm_threshold=0.12, transfer=None):
        self.baseline = dict(baseline or DEFAULT_BASELINE)
        self.half_life = {k: v[2] for k, v in LABELS.items()}
        self.half_life.update(half_life or {})
        self.max_delta = float(max_delta)
        self.calm_threshold = float(calm_threshold)
        self.transfer = {k: list(v) for k, v in DEFAULT_TRANSFER.items()}
        for label, table in (transfer or {}).items():
            self.transfer[label] = [(str(a), float(b)) for a, b in table]
        self.levels = {CALM: 1.0}

    # ---------- 内部：守衡 ----------
    def _total(self) -> float:
        return sum(v for v in self.levels.values() if v > 0)

    def _rebalance(self) -> None:
        """总和超过 1.0 就按比例压回去。

        正常路径（add/decay/from_dict）本身就守衡，这里只是保险；
        测试会直接往 levels 里塞值，那种情况不补平静。
        """
        total = self._total()
        if total <= EPS:
            self.levels = {CALM: 1.0}
            return
        if total <= 1.0 + 1e-7:
            return
        k = 1.0 / total
        for label in list(self.levels):
            v = self.levels[label] * k
            if v < 1e-6:
                self.levels.pop(label, None)
            else:
                self.levels[label] = v

    def _take(self, amount: float, exclude: str | None = None) -> float:
        """从别的标签里抽走 amount，返回实际抽到多少。平静优先，其余按比例。"""
        amount = max(0.0, float(amount))
        if amount <= EPS:
            return 0.0
        taken = 0.0
        calm_v = self.levels.get(CALM, 0.0)
        if CALM != exclude and calm_v > 0:
            give = min(calm_v, amount)
            self.levels[CALM] = calm_v - give
            taken += give
            amount -= give
        if amount <= EPS:
            self._cleanup()
            return taken
        pool = {k: v for k, v in self.levels.items()
                if k != CALM and k != exclude and v > 0}
        pool_total = sum(pool.values())
        if pool_total <= EPS:
            return taken
        for label, v in pool.items():
            give = v * min(1.0, amount / pool_total)
            self.levels[label] = v - give
            taken += give
        self._cleanup()
        return taken

    def _give(self, label: str, amount: float) -> None:
        if amount <= EPS:
            return
        self.levels[label] = self.levels.get(label, 0.0) + amount

    def _cleanup(self) -> None:
        for label in list(self.levels):
            if self.levels[label] < 1e-6:
                self.levels.pop(label, None)

    def _spread(self, src: str, amount: float) -> None:
        """把 amount 从 src 转出去：按转移表分给平静和关联情绪。"""
        table = self.transfer.get(src)
        if not table:
            self._give(CALM, amount)
            return
        rest = amount
        for dest, ratio in table:
            if dest == src:
                continue
            piece = amount * float(ratio)
            if piece <= EPS:
                continue
            self._give(dest, piece)
            rest -= piece
        if rest > EPS:
            self._give(CALM, rest)

    # ---------- 演化 ----------
    def decay(self, seconds: float) -> None:
        """时间冲淡：每种情绪按自己的半衰期降，降下来的按转移表转走。"""
        if seconds <= 0:
            return
        for label in list(self.levels):
            if label == CALM:
                continue
            v = self.levels.get(label, 0.0)
            if v <= EPS:
                continue
            hl = max(1.0, float(self.half_life.get(label, 90))) * 60.0
            gone = v * (1.0 - 0.5 ** (seconds / hl))
            if gone <= EPS:
                continue
            self.levels[label] = v - gone
            self._spread(label, gone)
        self._cleanup()
        self._rebalance()

    def add(self, label: str, delta: float) -> float:
        """加减：涨的那部分从别的情绪里挤出来，不会凭空多出来。"""
        label = str(label)
        delta = max(-self.max_delta, min(self.max_delta, float(delta)))
        if abs(delta) <= EPS:
            return self.levels.get(label, 0.0)

        if delta > 0:
            got = self._take(delta, exclude=label)
            got = min(got, delta)
            if got <= EPS:
                return self.levels.get(label, 0.0)
            self._give(label, got)
        else:
            v = self.levels.get(label, 0.0)
            gone = min(v, -delta)
            if gone <= EPS:
                return v
            self.levels[label] = v - gone
            # 缓解：大部分回平静，剩下按转移表走
            calm_part = gone * 0.75
            self._give(CALM, calm_part)
            self._spread(label, gone - calm_part)
        self._cleanup()
        self._rebalance()
        return self.levels.get(label, 0.0)

    # ---------- 读出 ----------
    @property
    def label(self) -> str:
        top, v = self.top()
        if v < self.calm_threshold:
            return CALM
        return top

    def top(self) -> tuple:
        """最强的非平静标签（平静是池子，不参与"主情绪"评选）。"""
        best, best_v = CALM, 0.0
        for label, v in self.levels.items():
            if label == CALM:
                continue
            if v > best_v:
                best, best_v = label, v
        return best, best_v

    @property
    def peak(self) -> float:
        return round(self.top()[1], 6)

    @property
    def intensity(self) -> float:
        top, v = self.top()
        return round(v if top != CALM else 0.0, 4)

    @property
    def family(self) -> str:
        """决定语气的那一情（怒气压过一切：人在气头上，别的情绪都得让路）。"""
        return self.dominant()[0]

    def dominant(self) -> tuple:
        """此刻哪个情绪说了算 —— 返回 (七情, 强度)。

        光看"最强的那一情"不够：喜欢一个人喜欢久了（affectionate 半衰期 12 小时），
        数值会一直很高，气头上也压不过它，说出来的分寸就成了"心情好"。
        所以怒气单独先判：只要在气头上，语气就按怒气算。
        """
        anger = max(
            self.levels.get("angry", 0.0),
            self.levels.get("annoyed", 0.0),
            self.levels.get("jealous", 0.0),
        )
        if anger >= self.calm_threshold:
            return "anger", round(anger, 4)
        top, v = self.top()
        if v < self.calm_threshold or top == CALM:
            return "calm", 0.0
        return str((LABELS.get(top) or ("calm",))[0]), round(v, 4)

    def accounts(self) -> dict:
        """七情账户（0~100 整数），加起来 100。"""
        sums = {k: 0.0 for k in SEVEN}
        for label, v in self.levels.items():
            acc = LABELS.get(label, (CALM,))[0]
            sums[acc] = sums.get(acc, 0.0) + v
        return {k: round(v * 100) for k, v in sums.items()}

    def breakdown(self, limit: int = 6) -> list:
        """小标签明细（0~100 整数），给展示/记忆用。"""
        items = sorted(((k, v) for k, v in self.levels.items() if k != CALM),
                       key=lambda kv: -kv[1])[:limit]
        return [{"label": k, "value": round(v * 100), "seven": SEVEN_LABEL.get(
            LABELS.get(k, (CALM,))[0], "")} for k, v in items]

    def pad(self):
        """PAD 只按"有情绪的那部分"算；只剩平静时就是基线。"""
        used = {k: v for k, v in self.levels.items() if k != CALM and v > EPS}
        total = sum(used.values())
        if total <= EPS:
            return [round(self.baseline[k], 3) for k in ("pleasure", "arousal", "dominance")]
        out = []
        for i, dim in enumerate(("pleasure", "arousal", "dominance")):
            avg = sum(ANCHOR(k)[i] * v for k, v in used.items()) / total
            out.append(round(self.baseline[dim] * (1 - min(1.0, total)) + avg * min(1.0, total), 3))
        return out

    def to_dict(self) -> dict:
        return {"intensity": {k: round(v, 6) for k, v in self.levels.items()}}

    @classmethod
    def from_dict(cls, data, **kw):
        obj = cls(**kw)
        raw = {str(k): float(v) for k, v in ((data or {}).get("intensity") or {}).items()}
        # 旧状态不是守衡的（总和可能 0.27）：把差额补进平静
        if raw:
            obj.levels = raw
            total = sum(raw.values())
            if total < 1.0:
                obj.levels[CALM] = obj.levels.get(CALM, 0.0) + (1.0 - total)
            obj._rebalance()
        return obj


def ANCHOR(label: str) -> tuple:
    return LABELS.get(label, (CALM, (0.10, 0.30, 0.50), 90))[1]


def calm_v_label() -> str:
    return CALM