"""记忆：她记得什么，以及记不清什么。

设计要点（跟"人"对齐，不是跟数据库对齐）：
1. 只记**有分量的事**：凶她、敷衍她、夸她、哄她、喂她、她说过的话。
   每句普通聊天都存，那叫日志，不叫记忆。
2. **越久越糊**：2 小时内记得原话（"你真笨"），超过 12 小时只剩一句概括
   （"你凶了她一次"），超过 3 天连次数都懒得数（"前几天你凶过她"）。
3. 时间一律用模糊说法：刚刚 / 刚才 / 今天早些 / 昨天 / 前两天 / 上周 / 前不久。
   人不会说"49 分钟前"，会说"刚才"。
"""
from __future__ import annotations

import json
from pathlib import Path

# 标签 -> 她记住的说法（第三人称视角，给面板读）
TAG_VERB = {
    "hostile": "凶了一句",
    "dismissive": "敷衍了一句",
    "praise": "夸了一句",
    "care": "哄了一下",
    "tease": "逗了一下",
    "feeding": "喂了吃的",
    "drinking": "倒了杯水",
    "apology": "道了歉",
}

# 这些标签值得记；其余（普通寒暄）不记
MEMORABLE = set(TAG_VERB)

# 分量：越大越难忘
WEIGHT = {"hostile": 1, "apology": 1, "care": 2, "praise": 3, "drinking": 2,
          "dismissive": 2, "tease": 3, "feeding": 3}

# 原话保留多久（小时）；过了就只剩概括
QUOTE_TTL_H = 12.0
# 超过这个时长，连"几次"都不提了
VAGUE_H = 72.0


def phrase_age(at: float, now: float) -> str:
    """模糊时间：她不会报分钟数。"""
    d = max(0.0, now - at)
    h = d / 3600.0
    if h < 0.02:      # 1 分钟
        return "刚刚"
    if h < 0.5:
        return "刚才"
    if h < 1.5:
        return "一个多小时前"
    if h < 4:
        return "今天早些"
    if h < 10:
        return "今天"
    if h < 30:
        return "昨天"
    if h < 52:
        return "前两天"
    if h < 100:
        return "前几天"
    if h < 200:
        return "上周"
    return "前不久"


def phrase_idle(idle_min: float | None) -> str:
    """聊了多久：模糊说法，不是计数。"""
    if idle_min is None:
        return "还没说过话"
    m = float(idle_min)
    if m < 3:
        return "刚说完话"
    if m < 25:
        return "聊了一会儿"
    if m < 70:
        return "聊着聊着就停了"
    if m < 180:
        return "隔了一阵没说话"
    if m < 480:
        return "好一会儿没动静了"
    if m < 1440:
        return "大半天没说话了"
    if m < 4320:
        return "一两天没说话了"
    return "好几天没聊了"


class Memory:
    """她的记忆库：有分量的、会变糊的事。"""

    def __init__(self, path=None, max_items: int = 300, quote_ttl_h=None):
        self.path = Path(path) if path else None
        self.max_items = int(max_items)
        self.quote_ttl_h = float(quote_ttl_h) if quote_ttl_h is not None else QUOTE_TTL_H
        self.items = []

    # ---------- 记 ----------
    def add(self, at: float, kind: str, text: str = "", tags=None,
            person=None, weight: int | None = None) -> dict | None:
        tags = [str(t) for t in (tags or [])]
        tag = next((t for t in tags if t in MEMORABLE), None)
        if tag is None and kind not in ("event", "her_word", "auto_event"):
            return None                      # 没有分量的寒暄不记
        w = int(weight if weight is not None else WEIGHT.get(tag, 3))
        item = {
            "at": round(float(at), 3),
            "kind": kind,
            "text": (text or "").strip(),
            "tags": tags,
            "tag": tag,
            "person": person,
            "w": w,
        }
        # 同一件事 30 秒内不重复记（连发三条"你真笨"不该算三次）
        for old in reversed(self.items[-3:]):
            if (old.get("tag") == tag and old.get("text") == item["text"]
                    and abs(float(old["at"]) - item["at"]) < 30):
                return None
        self.items.append(item)
        if len(self.items) > self.max_items:
            # 先丢最轻、最旧的
            self.items.sort(key=lambda x: (x["w"], x["at"]), reverse=True)
            self.items = self.items[: self.max_items]
        return item

    # ---------- 想 ----------
    def recall(self, now: float, tag=None, tags=None, kind=None,
               within_h: float | None = None, person=None) -> list:
        want = set(tags or ([tag] if tag else []))
        out = []
        for it in self.items:
            if person is not None and it.get("person") not in (None, person):
                continue
            if kind is not None and it.get("kind") != kind:
                continue
            if want and not (want & set(it.get("tags") or [])):
                continue
            if within_h is not None and (now - float(it["at"])) > within_h * 3600:
                continue
            out.append(it)
        return sorted(out, key=lambda x: x["at"])

    def last(self, now: float, tags=None, within_h=None, person=None):
        got = self.recall(now, tags=tags, within_h=within_h, person=person)
        return got[-1] if got else None

    # ---------- 说 ----------
    def describe(self, item: dict, now: float) -> dict:
        """把一条记忆说成人话；久远的丢掉原话。"""
        age_h = (now - float(item["at"])) / 3600.0
        verb = TAG_VERB.get(item.get("tag") or "") or (item.get("text") or "一件事")
        quote = None
        if age_h <= self.quote_ttl_h and item.get("text"):
            quote = item["text"][:24]
        return {
            "at": item["at"],
            "when": phrase_age(float(item["at"]), now),
            "verb": verb,
            "quote": quote,
            "vague": age_h > VAGUE_H,
            "tag": item.get("tag"),
            "by": "you" if item.get("tag") in TAG_VERB else "her",
        }

    def digest(self, now: float, limit: int = 3, person=None) -> list:
        """面板用：她这会儿记得的几件事，最新的在前。

        person 给了就只看这条线上的（主人 / 某个群各算各的），
        没记过人的（全局事件）两边都算。不给就混着看。
        """
        useful = [it for it in self.items
                  if it.get("tag") in TAG_VERB or it.get("kind") == "event"]
        if person is not None:
            useful = [it for it in useful if it.get("person") in (None, person)]
        items = sorted(useful, key=lambda x: x["at"], reverse=True)
        return [self.describe(it, now) for it in items[:limit]]

    # ---------- 存 ----------
    def to_dict(self) -> dict:
        return {"version": 1, "items": self.items}

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        items = data.get("items") if isinstance(data, dict) else data
        if isinstance(items, list):
            self.items = [it for it in items if isinstance(it, dict) and "at" in it]