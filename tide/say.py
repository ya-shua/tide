"""她一开口说什么。

这不是"LLM 写的台词"，是**状态驱动的一句话**：想你了 / 无聊 / 赌气 / 被吵醒。
后续接 LLM 时，这里只负责提供"意图和语气"，措辞交给模型。

场景：
    miss     想你（长时间没互动）
    bored    无聊，想找人说话
    grumble  还在小赌气
    woken    被叫醒（普通）
    woken_hard  刚睡下没多久 / 凌晨被叫醒（起床气重）
"""
from __future__ import annotations

LINES = {
    "miss": [
        "在忙吗？突然有点想你。",
        "……你还在吗？今天好安静。",
        "刚刚想起你说过的事，笑了一下。",
    ],
    "bored": [
        "好无聊，你在干嘛。",
        "我闲得快长蘑菇了，聊两句呗。",
        "刚看了个视频笑死，等下讲给你听。",
    ],
    "grumble": [
        "……你是不是忘了还有个人在等你。",
        "哼。",
        "我不想先说话，可我还是说了。",
    ],
    "woken": [
        "唔…我刚睡着，什么事啊。",
        "……几点了，被你吵醒。",
        "困死了，你最好有正事。",
    ],
    "woken_hard": [
        "……你知道现在几点吗。",
        "我刚睡着就被你弄醒了，明天再说吧。",
        "别吵，我要睡了。",
    ],
}


def compose(scene: str, idx: int = 0) -> str:
    pool = LINES.get(scene) or LINES["miss"]
    return pool[int(idx) % len(pool)]


def pick_scene(needs: dict, bond: dict, clock: dict | None = None) -> str:
    """按当前状态挑场景：被吵醒优先，其次赌气、想你、无聊。"""
    clock = clock or {}
    if clock.get("woken"):
        return "woken_hard" if clock.get("woken_hard") else "woken"
    if float(bond.get("grievance", 0)) >= 15:
        return "grumble"
    if float(needs.get("longing", 0)) >= float(needs.get("boredom", 0)):
        return "miss"
    return "bored"