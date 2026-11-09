"""情绪：把 Tide（汐）接进海螺，让她知道自己此刻什么状态。

分工（2026-11-07 定，别再搞反）
------------------------------
**Tide 是她的身体，海螺是她的嘴。**

    Tide   只负责"我现在什么心情、缺什么、想不想找他"——一个状态源
    海螺   决定说不说、说什么、怎么说——嘴和判断都在这边
    她     想不想开口，是她自己的事

所以这条线**没有否决权**：Tide 不拦话、不开关麦、不替她决定发不发。
它只做三件事：

    message.observed  有人说话 → 告诉她"你经历了一件事"
    speech.prompt     开口前 → 把"你现在的心情"写进提示词（第一人称，陈述句）
    speech.gate       发出去之前 → 只记一笔"她说了这句"（不改 allow）

别的插件（或规则）想拦话是它们的事；这里永远 allow 原样返回。

Tide 面板不在时，这里全部静默跳过：不注入、不记账，聊天照常。

配置（config.json）
-------------------
    enabled      true
    panel_url    http://127.0.0.1:7880
    timeout_s    1.5
"""
from __future__ import annotations

import asyncio
import importlib.util
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load_backend():
    spec = importlib.util.spec_from_file_location("qqbridge_tide_client", _HERE / "tide_backend.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"加载适配层失败：{_HERE / 'tide_backend.py'}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _card_of(cfg, uid: str):
    """这个号是不是某个「自己人」（称呼卡上的号）。"""
    if not uid:
        return None
    for card in (getattr(cfg, "admins", None) or []):
        ids = getattr(card, "ids", None) or (card.get("ids") if isinstance(card, dict) else None) or []
        if uid in {str(x) for x in ids}:
            return card
    return None


def person_for(ctx, conv_id: str, sender_id: str = "") -> str:
    """按「是不是同一个人」记，不按会话记。

    - 自己人（称呼卡上的任何号，含同一个人的几个号）→ "" 用 Tide 默认那个人，
      所以他在 A 号、B 号、群里说的，都是同一个人、同一份关系
    - 别的私聊 / 群里别人 → 按 QQ 号一个人；群里换了人就换了人
      （以前整群记成一个人，群里所有人共用一份好感）
    """
    cfg = getattr(ctx, "cfg", None)
    uid = str(sender_id or "")
    if not uid and conv_id.startswith("private:"):
        uid = conv_id.split(":", 1)[1]
    if _card_of(cfg, uid) is not None:
        return ""
    if uid:
        return f"qq:{uid}"
    return conv_id or ""


async def _call(fn, *args):
    """HTTP 很短，但也不能卡住事件循环。"""
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception:
        return None


async def setup(ctx) -> None:
    cfg = dict(ctx.config or {})
    if not cfg.get("enabled", True):
        ctx.log.info("情绪插件关着，跳过")
        return

    client = _load_backend().TideClient(
        base_url=str(cfg.get("panel_url") or "http://127.0.0.1:7880"),
        timeout=float(cfg.get("timeout_s") or 1.5),
    )
    ctx.services["mood"] = {"client": client, "seen": 0, "spoke": 0}

    ok = await _call(client.alive)
    if ok:
        st = await _call(client.state)
        feel = ((st or {}).get("snapshot") or {}).get("feelings") or ""
        ctx.log.info("情绪接上了 Tide：%s", feel or "（没说话）")
    else:
        ctx.log.warning("Tide 面板没起来（%s），心情暂时不生效；面板起来后自动接上",
                        client.base)

    ctx.on("message.observed", lambda p: observe(ctx, p), priority=50)
    ctx.on("speech.prompt", lambda p: prompt_hook(ctx, p), priority=50)
    ctx.on("speech.gate", lambda p: gate_hook(ctx, p), priority=50)


async def teardown(ctx) -> None:
    ctx.services.pop("mood", None)


async def observe(ctx, payload: dict) -> None:
    """每来一条消息都让她经历一次。"""
    text = str(payload.get("text") or "").strip()
    runtime = ctx.services.get("mood")
    if not text or not runtime:
        return
    person = person_for(ctx, str(payload.get("conv_id") or ""), str(payload.get("sender_id") or ""))
    speaker = str(payload.get("speaker") or "other")
    await _call(runtime["client"].observe, text, person or None, speaker, False)
    runtime["seen"] += 1


async def prompt_hook(ctx, payload: dict) -> None:
    """把"你现在的心情"写进提示词——第一人称，不是体检报告。"""
    runtime = ctx.services.get("mood")
    if not runtime:
        return
    person = person_for(ctx, str(payload.get("conv_id") or ""), str(payload.get("sender_id") or ""))
    st = await _call(runtime["client"].state, person or None)
    if not st:
        return
    plan = st.get("plan") or {}
    snap = st.get("snapshot") or {}
    bits = [str(plan.get("prompt") or "").strip()]
    feel = str(snap.get("feelings") or "").strip()
    if feel and feel not in bits[0]:
        bits.insert(0, "你现在的心情：" + feel)
    if snap.get("quiet"):
        bits.append("这个点你本来已经睡了，是被这条消息吵醒的。")
    extra = "\n\n".join(b for b in bits if b)
    if extra:
        payload["extra"] = str(payload.get("extra") or "") + "\n\n" + extra
    payload["plan"] = plan
    payload["tide"] = {"feelings": feel, "wake": (snap.get("wake") or {}).get("wake")}


async def gate_hook(ctx, payload: dict) -> None:
    """发出去之前：只记一笔"她说了这句"，**不改 allow**。

    这里以前会按"她在睡觉 / 免打扰 / 时机不到"拦话——那是 Tide 在替她决定。
    现在不拦了：Tide 是身体，不是老板；说不说是海螺和她自己的事。
    """
    runtime = ctx.services.get("mood")
    if not runtime:
        return
    if not payload.get("allow", True):
        return                      # 别的插件已经拦了，不用记
    conv_id = str(payload.get("conv_id") or "")
    sender_id = str(payload.get("sender_id") or "")
    feature = str(payload.get("feature") or "chat")
    person = person_for(ctx, conv_id, sender_id)

    # 她说出口了：告诉 Tide（主动开口会开启缓解期、也算一次叫醒）
    await _call(runtime["client"].observe, str(payload.get("text") or ""),
                person or None, "self", feature == "proactive")
    if feature == "proactive":
        await _call(runtime["client"].woke)
    runtime["spoke"] = int(runtime.get("spoke", 0)) + 1