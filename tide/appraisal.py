"""刺激评估（appraisal）：把一条消息翻译成 情绪/关系/需求 的增量。

文档 §5 原本打算用 LLM 做一次轻量分类；P0/P1 阶段先走规则表
（`config/stimuli.yaml`），一个 key 都不用，P2 再把 LLM 接进来做同一件事。

"是否针对我"是这里最要紧的一步：
    "你真笨"     → 针对她，anger + grievance
    "这软件真笨" → 不针对，减半或不计
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 出现这些词，说明话头指向第三方而不是她
THIRD_PARTY = [
    "这软件", "这项目", "这东西", "这个程序", "那个程序", "这个插件", "那个插件",
    "公司", "同事", "老板", "领导", "老师", "同学", "室友",
    "这", "那", "它", "他", "她",
]

# 这些词出现在情绪词前面时，说明是哄人（"别生气"），不是对方在生气
NEGATIONS = ("别", "不要", "甭", "不用", "无需", "没那么")

# 对方情绪 → 她的反应（对方低落她会担心）
MOOD_EFFECTS = {
    "sad": ({"worried": 0.25}, {"affinity": 1}),
    "angry": ({"worried": 0.15}, {"grievance": 3}),
    "anxious": ({"worried": 0.20}, {}),
    "tired": ({"worried": 0.10}, {}),
    "happy": ({"joyful": 0.15}, {"affinity": 1}),
    "excited": ({"joyful": 0.15}, {}),
}


@dataclass
class Appraisal:
    emotion: dict = field(default_factory=dict)
    bond: dict = field(default_factory=dict)
    needs: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    mood: str = ""
    directed: bool = True

    def merge(self, emotion=None, bond=None, needs=None):
        for k, v in (emotion or {}).items():
            self.emotion[k] = self.emotion.get(k, 0.0) + float(v)
        for k, v in (bond or {}).items():
            self.bond[k] = self.bond.get(k, 0.0) + float(v)
        for k, v in (needs or {}).items():
            self.needs[k] = self.needs.get(k, 0.0) + float(v)


class Appraiser:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.rules = cfg.get("rules") or []
        self.moods = cfg.get("moods") or {}

    def detect_mood(self, text: str) -> str:
        text = text or ""
        best, best_hits = "", 0
        for label, words in self.moods.items():
            hits = 0
            for w in (words or []):
                if not w:
                    continue
                idx = text.find(w)
                while idx != -1:
                    # "别生气""不要难过"是哄人，不是对方在生气
                    pre = text[max(0, idx - 3):idx]
                    if not any(n in pre for n in NEGATIONS):
                        hits += 1
                    idx = text.find(w, idx + 1)
            if hits > best_hits:
                best, best_hits = label, hits
        return best

    @staticmethod
    def is_directed(text: str) -> bool:
        text = text or ""
        if "你" in text:
            return True
        return not any(m in text for m in THIRD_PARTY)

    def evaluate(self, text: str) -> Appraisal:
        text = text or ""
        result = Appraisal(directed=self.is_directed(text))
        short = len(text.strip()) <= 3

        for rule in self.rules:
            keywords = [str(k) for k in (rule.get("keywords") or [])]
            strong = [str(k) for k in (rule.get("strong") or [])]
            if not (any(k and k in text for k in keywords)
                    or any(k and k in text for k in strong)):
                continue
            if rule.get("requires_short") and not short:
                continue
            if rule.get("skip_if_question") and text.rstrip().endswith(("？", "?")):
                continue           # "晚上想吃点什么？"是在问她，不是喂了她
            if rule.get("needs_you") and "你" not in text:
                continue           # 只有明着冲她说才算
            if rule.get("need_target") and not result.directed:
                continue
            if rule.get("only_if_directed") and not result.directed:
                continue
            result.tags.append(rule.get("id", "rule"))
            result.merge(rule.get("emotion"), rule.get("bond"), rule.get("needs"))
            if rule.get("mood"):
                result.mood = str(rule["mood"])

        if not result.mood:
            result.mood = self.detect_mood(text)

        effects = MOOD_EFFECTS.get(result.mood)
        if effects:
            result.tags.append("mood:" + result.mood)
            result.merge(effects[0], effects[1])

        # 不针对她的话，情绪影响减半（但仍然说明对方心情）
        if not result.directed:
            result.emotion = {k: v * 0.5 for k, v in result.emotion.items()}
            result.bond.pop("grievance", None)

        return result