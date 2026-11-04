"""主动消息判定（文档 §6.3）。

    urgency = w1*longing + w2*boredom + w3*energy - w4*grievance

判定顺序：
1. 先看有没有硬性拦阻：勿扰时段 / 连着发了几条没回音 / 冷却中 / 还在委屈
2. 想念有个"硬门槛"：想你想得厉害（默认 ≥ 88）就直接够格开口，
   不必再靠无聊和累凑分——这是最像人的那个理由，不该被算术卡住
3. 其余情况按加权总分和阈值比
"""
from __future__ import annotations


def urgency(needs: dict, bond: dict, weights=None) -> float:
    w = {"longing": 0.70, "boredom": 0.30, "energy": 0.28, "grievance": 0.40}
    w.update(weights or {})
    val = (
        w["longing"] * float(needs.get("longing", 0))
        + w["boredom"] * float(needs.get("boredom", 0))
        + w["energy"] * float(needs.get("energy", 0))
        - w["grievance"] * float(bond.get("grievance", 0))
    )
    return round(max(0.0, val), 1)


def decide(
    needs: dict,
    bond: dict,
    cfg: dict,
    quiet: bool,
    unanswered: int,
    last_proactive_at: float,
    now: float,
) -> dict:
    cfg = cfg or {}
    weights = cfg.get("weights") or {}
    threshold = float(cfg.get("urgency_threshold", 60))
    grievance_gate = float(cfg.get("grievance_gate", 80))
    max_unanswered = int(cfg.get("max_unanswered", 2))
    cooldown_min = float(cfg.get("cooldown_min", 90))
    longing_gate = float(cfg.get("longing_gate", 88))

    u = urgency(needs, bond, weights)
    grievance = float(bond.get("grievance", 0))
    longing = float(needs.get("longing", 0))

    # ---- 硬性拦阻 ----
    blockers = []
    if quiet:
        blockers.append("勿扰时段")
    if unanswered >= max_unanswered:
        blockers.append(f"已有 {unanswered} 条主动消息没回音，停发")
    if last_proactive_at and now - last_proactive_at < cooldown_min * 60:
        blockers.append("冷却中")
    if grievance > 0 and u < grievance_gate:
        blockers.append("还在委屈，不想先开口")

    craving = longing >= longing_gate  # 想你想得厉害

    if blockers:
        should = False
        reason = "；".join(blockers)
    elif u >= threshold:
        should = True
        reason = "想你了，可以开口"
    elif craving:
        should = True
        reason = f"想你想得厉害（{longing:.0f}），不用凑分也想开口"
    else:
        should = False
        reason = f"还没够着开口（{u} < {threshold}）"

    return {
        "should_send": should,
        "urgency": u,
        "threshold": threshold,
        "craving": craving,
        "tone": "cool" if grievance > 0 else bond.get("tone", "neutral"),
        "reason": reason,
    }