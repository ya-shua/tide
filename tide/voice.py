"""表达层：情绪 → TTS 参数（文档 §7.1）。

同一个 voice，情绪不同 → instruct / speed / pitch 不同。
音色不变，语气在变 —— 这是"她有自己的情绪"，不是"换了个人"。

注意：instruct 是给 EmotiVoice / IndexTTS2 / CosyVoice2 这类支持指令的引擎用的。
你现在接的 MiMo / Seed-VC 只吃 speed / pitch，instruct 会作为软提示带出去，不用也不碍事。
"""
from __future__ import annotations

EMOTION_VOICE = {
    "calm":         ("自然、平稳", 1.00, 0),
    "joyful":       ("开心、轻快、带笑意", 1.08, 2),
    "excited":      ("亢奋、上扬、快", 1.12, 3),
    "playful":      ("轻快、带笑、俏皮", 1.06, 1),
    "affectionate": ("温柔、放软、贴身", 0.95, -1),
    "shy":          ("小声、迟疑、软", 0.94, -1),
    "sad":          ("低、慢、气声", 0.88, -3),
    "disappointed": ("低、叹气、慢", 0.90, -2),
    "angry":        ("压低、带气、短促", 1.05, 1),
    "annoyed":      ("平、短、不带起伏", 1.00, 0),
    "tired":        ("含糊、拖尾、懒", 0.90, -2),
    "bored":        ("平、略拖、没劲", 0.96, -1),
    "worried":      ("轻、紧、稍快", 1.00, 0),
    "nostalgic":    ("慢、轻、留白", 0.94, -1),
}


def voice_for(label: str, intensity: float = 0.0, tone: str = "neutral") -> dict:
    instruct, speed, pitch = EMOTION_VOICE.get(label, EMOTION_VOICE["calm"])

    # 强度会把参数再推一点：强度低时更接近基线
    k = max(0.0, min(1.0, float(intensity)))
    speed = round(1.0 + (speed - 1.0) * (0.4 + 0.6 * k), 3)
    pitch = int(round(pitch * (0.4 + 0.6 * k)))

    # 闷气/冷战：语气压平、变短；但如果是负面情绪，别把"带气"抹掉
    if tone == "cool":
        if label in ("angry", "annoyed", "sad", "disappointed", "tired"):
            speed = round(min(speed, 1.0), 3)
            pitch = min(pitch, 0)
        else:
            instruct = "平、短、不带起伏"
            speed = 1.0
            pitch = 0

    return {"instruct": instruct, "speed": speed, "pitch": pitch}