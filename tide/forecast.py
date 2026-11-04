"""未来推演：假设"从现在起没人说话"，把状态往后算 N 小时。

面板靠它把"她接下来会怎么样"画成曲线 —— 比看实时数字直观得多：
委屈什么时候爬上闷气线、想念多久到阈值，一眼就能看出来。
纯拷贝计算，不动真实状态。
"""
from __future__ import annotations

import copy

from . import inner_voice


def forecast(core, person=None, hours: float = 24.0, step_h: float = 0.5) -> list:
    pid = str(person or core.default_person)
    emo = copy.deepcopy(core.emotion)
    nd = copy.deepcopy(core.needs)
    bd = copy.deepcopy(core._bond(pid))
    tp = copy.deepcopy(core._topic(pid))
    t0 = core.now()
    step = float(step_h) * 3600.0

    out = []
    steps = int(round(hours / step_h))
    for i in range(steps + 1):
        t = t0 + i * step
        quiet = core.is_quiet(t)
        needs = nd.to_dict(t, bd.affinity)
        bond_d = bd.to_dict(t)
        out.append(
            {
                "h": round(i * step_h, 2),
                "hunger": needs["hunger"],
                "thirst": needs["thirst"],
                "energy": needs["energy"],
                "longing": needs["longing"],
                "boredom": needs["boredom"],
                "grievance": round(bd.grievance, 1),
                "urgency": inner_voice.urgency(needs, bond_d),
                "topic": tp.state,
                "quiet": quiet,
            }
        )
        # 推进一个步长
        nd.advance(step, quiet)
        emo.decay(step)
        bd.decay(step, t + step)
        added = tp.accrual(t + step, bd.affinity, core.is_quiet(t + step))
        if added:
            # 与 core._advance 保持一致：已经在生气时冷落减半
            if bd.tier in ("mid", "big"):
                added *= core._angry_factor
            bd.apply({"grievance": added}, t + step)
        tp.maybe_close(t + step)
    return out