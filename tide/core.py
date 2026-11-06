"""TideCore 门面：把情绪 / 需求 / 关系 / 话题 / 表达 串起来。

设计上的两个关键决定：

1. **懒 tick**：所有状态都只在"读"或"被喂"的时候按 Δt 一次性推进。
   不跑后台线程、不需要心跳。服务停了、电脑关一夜，回来读到的照样是对的。
2. **状态落盘**：`data/state.json`，每次变更后原子写。挂掉最多丢一条消息的影响。

对外形状（给将来的 QQ 桥接 / MCP 工具用）：

    core.observe(text="你终于回我了", speaker="other", at=now)
    core.observe(text="我刚在忙呀，怎么啦", speaker="self", at=now)
    core.tick(now)
    core.plan_reply()      # 给 LLM 的软约束 + 给 TTS 的参数
    core.snapshot()        # 全量状态
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import appraisal as app_mod
from . import bond as bond_mod
from . import emotion as emo_mod
from . import circadian as clock_mod
from . import updater as upd_mod
from . import inner_voice, media as media_mod
from .version import __version__
from . import memory as mem_mod, qq as qq_mod, say as say_mod
from . import needs as needs_mod, settings as set_mod
from . import timeutil, voice
from . import topic as topic_mod
from . import yaml_mini

STATE_VERSION = 1


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    try:
        import yaml  # 有就用，没有就跑极简解析器
        return yaml.safe_load(text) or {}
    except Exception:
        return yaml_mini.loads(text)


def _deep_merge(base: dict, extra: dict) -> dict:
    """小的覆盖大的：local.yaml 里写什么就改什么，没写的保持原样。"""
    out = dict(base or {})
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class TideCore:
    def __init__(self, cfg: dict, state_path=None):
        self.cfg = cfg or {}
        self.char = self.cfg.get("char") or {}
        self.rules = self.cfg.get("rules") or {}
        self.state_path = Path(state_path) if state_path else None
        self.offset = 0.0
        self.last_tick = 0.0
        self.unanswered_proactive = 0
        self.last_proactive_at = 0.0
        self.log = []
        self.default_person = str(self.rules.get("default_person") or "主人")
        self._angry_factor = float((self.rules.get("neglect") or {}).get("angry_factor", 0.5))

        emo_cfg = (self.cfg.get("emotion") or {})
        self.emotion = emo_mod.Emotion(
            baseline=emo_cfg.get("baseline") or self.char.get("baseline"),
            half_life=emo_cfg.get("half_life_min"),
            max_delta=emo_cfg.get("max_delta_per_event", 0.4),
            calm_threshold=emo_cfg.get("calm_threshold", 0.12),
        )
        self.needs = needs_mod.Needs(self.rules.get("needs") or {})
        self.appraiser = app_mod.Appraiser(self.cfg.get("stimuli") or {})
        self.bonds = {}
        self.topics = {}
        data_dir = self.state_path.parent if self.state_path else None
        self.last_auto_note = ""
        self.last_auto_at = 0.0
        self.media = media_mod.Media(self.rules.get("media") or {})
        self.last_media = None
        self.clock = clock_mod.Circadian(self.rules.get("circadian") or {})
        self.qq = qq_mod.QQ(self.rules.get("qq") or {},
                           outbox=(data_dir / "outbox.jsonl") if data_dir else None)
        self.just_woken = None
        self.media.prefetch()          # 后台先备一条，真到无聊时手边就有
        self.memory = mem_mod.Memory(path=(data_dir / "memory.json") if data_dir else None)
        self.settings = set_mod.Settings(path=(data_dir / "settings.json") if data_dir else None)
        self.root = self.state_path.parent.parent if self.state_path else Path.cwd()
        self.updater = upd_mod.Updater(self.rules.get("update") or {}, self.root)
        self.settings.load()
        self._apply_settings()

        if self.state_path and self.state_path.exists():
            self.load()
        self.memory.load()

    # ---------- 构造 ----------
    @classmethod
    def from_config(cls, config_dir, state_path=None) -> "TideCore":
        config_dir = Path(config_dir)
        rules = _load_yaml(config_dir / "rules.yaml") if (config_dir / "rules.yaml").exists() else {}
        # 本地私有配置（不进仓库）：token、QQ 号这类东西只写在这里
        local = _load_yaml(config_dir / "local.yaml") if (config_dir / "local.yaml").exists() else {}
        if local:
            rules = _deep_merge(rules, local)
        cfg = {
            "char": _load_yaml(config_dir / "character.yaml") if (config_dir / "character.yaml").exists() else {},
            "emotion": _load_yaml(config_dir / "emotion.yaml") if (config_dir / "emotion.yaml").exists() else {},
            "rules": rules,
            "stimuli": _load_yaml(config_dir / "stimuli.yaml") if (config_dir / "stimuli.yaml").exists() else {},
        }
        if state_path is None and config_dir.parent.name:
            state_path = config_dir.parent / "data" / "state.json"
        return cls(cfg, state_path=state_path)

    # ---------- 时钟 ----------
    def now(self) -> float:
        return timeutil.epoch() + self.offset

    @property
    def quiet_hours(self):
        hours = self.rules.get("quiet_hours") or ["00:30", "07:30"]
        return hours[0], hours[1]

    def is_quiet(self, t: float) -> bool:
        if self.clock.asleep:
            return True          # 睡着了当然不主动说话
        start, end = self.quiet_hours
        return timeutil.in_window(t, start, end)

    def advance(self, hours: float):
        """面板时光机：把虚拟时钟往前拨，用来快速看衰减。"""
        self.offset += float(hours) * 3600.0
        return self.tick()

    # ---------- 状态对象 ----------
    def _apply_settings(self) -> None:
        """把设置写回各个模块；改完立刻生效，不用重启。"""
        st = self.settings.data
        if not st.get("update_repo"):
            st["update_repo"] = (self.rules.get("update") or {}).get("repo", "")
        self.char["name"] = st["name"]
        self.default_person = str(st["person"])
        self.rules["quiet_hours"] = [st["quiet_start"], st["quiet_end"]]
        bond_cfg = dict(self.rules.get("bond") or {})
        bond_cfg["tiers"] = {"mild": st["tier_mild"], "mid": st["tier_mid"],
                             "big": st["tier_big"]}
        bond_cfg["calm_hours"] = st["calm_hours"]
        bond_cfg["comfort_cooldown_min"] = st["comfort_cooldown_min"]
        self._bond_cfg = bond_cfg
        pro = dict(self.rules.get("proactive") or {})
        pro["urgency_threshold"] = st["proactive_threshold"]
        pro["cooldown_min"] = st["proactive_cooldown_min"]
        pro["max_unanswered"] = st["proactive_max_unanswered"]
        self.rules["proactive"] = pro
        self.memory.quote_ttl_h = st["memory_quote_hours"]
        repo = str(st.get("update_repo") or "").strip()
        if repo and repo != self.updater.repo:
            self.updater.repo = repo
            self.updater.state["checked_at"] = 0
            self.updater.check_async()
        for b in self.bonds.values():          # 已经捏好的对象也套一遍
            b.mild, b.mid, b.big = (float(st["tier_mild"]), float(st["tier_mid"]),
                                    float(st["tier_big"]))
            b.calm_hours = float(st["calm_hours"])
            b.comfort_cooldown_min = float(st["comfort_cooldown_min"])

    def update_settings(self, patch: dict) -> dict:
        self.settings.update(patch)
        self._apply_settings()
        self.save()
        return self.settings.public()

    def _bond(self, pid: str):
        if pid not in self.bonds:
            self.bonds[pid] = bond_mod.Bond(getattr(self, "_bond_cfg", None)
                                        or (self.rules.get("bond") or {}))
        return self.bonds[pid]

    def _topic(self, pid: str):
        if pid not in self.topics:
            self.topics[pid] = topic_mod.Topic(self.rules)
        return self.topics[pid]

    def _apply_bond(self, bond, deltas: dict, tags, t: float) -> None:
        """把关系增量落到 bond 上——消气要看档位。

        小生气：一句哄 / 一句道歉直接清零（哄一哄就好）
        中生气：数字不动，只记"道歉过 / 哄过"；两样齐了地板才打开
        大生气：数字不动，只缩短冷静时间；真正的解药是等
        加委屈（冷落、被凶）则各档都照加。
        """
        d = dict(deltas or {})
        g = d.pop("grievance", None)
        if g is not None:
            if g >= 0:
                d["grievance"] = g
            elif bond.tier == "mild":
                d["grievance"] = -1000.0
        bond.apply(d, t)
        bond.note(tags, t)

    def _boredom_mood(self, secs: float) -> None:
        """闲久了是真的会无聊：需求上的"无聊"高了，情绪上的"无聊"就浮上来。

        以前 bored 这个情绪只有定义、没有任何来源，永远不会出现。
        """
        excess = max(self.needs.boredom, getattr(self.needs, 'last_peak_boredom', 0.0)) - 55.0
        if excess <= 0:
            return
        hours = secs / 3600.0
        self.emotion.add("bored", min(0.30, 0.005 * excess * hours))

    def _on_sleep_event(self, kind: str, value, t: float) -> None:
        """她睡了 / 醒了：写进日志和记忆，面板上看得见。"""
        if kind == "sleep":
            text = "去睡了"
        elif kind == "nap":
            text = "困得不行，眯了一会儿"
        elif kind == "wake":
            text = "睡醒了"
        else:
            return
        self.last_auto_note = text.replace("（", "").replace("）", "")
        self.last_auto_at = t
        self.log.append({"at": round(t, 3), "speaker": "self", "kind": "auto",
                         "text": text, "person": self.default_person})
        if len(self.log) > 60:
            self.log = self.log[-60:]

    def _absorb_self_care(self, secs: float, t: float) -> None:
        """她渴了自己倒水、饿了自己吃、困了打盹——这些不写进对话，但要留痕。"""
        notes = list(self.needs.care_log)[-3:]
        self.needs.care_log = []
        if not notes:
            return
        for note in notes:
            item = None
            if "视频" in note:                 # 轮到"刷视频"这一档，就真的去看一条
                item = self.media.take()
                if item:
                    note = media_mod.describe(item)
            self.last_auto_note = note
            self.last_auto_at = t
            if item:
                self.last_media = item
            self.memory.add(t, "auto_event", note, person=self.default_person, weight=4)
            entry = {"at": round(t, 3), "speaker": "self", "kind": "auto",
                     "text": note, "person": self.default_person}
            if item:
                entry["media"] = {"title": item.get("title"), "bvid": item.get("bvid"),
                                  "url": item.get("url"), "author": item.get("author"),
                                  "cover": item.get("cover")}
            self.log.append(entry)
        if len(self.log) > 60:
            self.log = self.log[-60:]

    # ---------- 时间推进 ----------
    def _advance(self, t: float) -> None:
        if not self.last_tick:
            self.last_tick = t
            return
        secs = t - self.last_tick
        if secs <= 0:
            self.last_tick = t
            return

        # 先做整段的衰减（纯指数，分不分段结果一样），再算冷落
        quiet = self.is_quiet(t)
        self.emotion.decay(secs)
        for pid in list(self.bonds.keys()):
            self.bonds[pid].decay(secs, t)

        # 分段推进：中途她可能睡着、也可能醒来（睡眠影响疲惫/饿/渴的走法）
        recover = float((self.rules.get("circadian") or {}).get("recover_per_hour", 16.0))
        remaining, ts = secs, self.last_tick
        while remaining > 1e-9:
            chunk = min(1800.0, remaining)
            remaining -= chunk
            ts += chunk
            asleep = self.clock.asleep
            quiet_chunk = self.is_quiet(ts) or asleep
            self.needs.advance(chunk, quiet_chunk, asleep=asleep, recover_per_hour=recover)
            for kind, val in self.clock.step(chunk, ts, self.needs.energy):
                self._on_sleep_event(kind, val, ts)
            for pid in list(self.topics.keys()):
                topic = self.topics[pid]
                bd = self._bond(pid)
                added = topic.accrual(ts, bd.affinity, quiet_chunk)
                if added:
                    # 她已经在生气（中/大）时，冷落加得慢一半：不至于一次就顶满
                    if bd.tier in ("mid", "big"):
                        added *= self._angry_factor
                    bd.apply({"grievance": added}, ts)

        for pid in list(self.topics.keys()):
            self.topics[pid].maybe_close(t)   # 收尾判断按整段做一次，不要每段都判
        self._boredom_mood(secs)
        self._absorb_self_care(secs, t)

        self.last_tick = t

    # ---------- 输入 ----------
    def observe(self, text=None, speaker="other", person=None, at=None) -> dict:
        t = float(at) if at is not None else self.now()
        self._advance(t)
        pid = str(person or self.default_person)
        bond, topic = self._bond(pid), self._topic(pid)
        record = {"at": round(t, 3), "speaker": speaker, "text": text or "", "person": pid}

        # 她在睡觉吗？睡着被叫醒要有反应（后续接语音：这里是"沙哑/不高兴"的语气入口）
        woke = self.clock.wake_by_message(t) if speaker != "self" else None
        if woke:
            self.just_woken = {"at": t, **woke}
            self.emotion.add("annoyed", 0.32 if woke["hard"] else 0.14)
            self.emotion.add("tired", 0.18)
            if woke["hard"]:
                self._apply_bond(bond, {"grievance": 8.0}, ["woken"], t)
            note = ("睡得正沉被吵醒了" if woke["hard"]
                    else "被叫醒了（才睡了 %.1f 小时）" % woke["slept_h"])
            self.memory.add(t, "event", note, person=pid, tags=["woken"], weight=3)
            self.log.append({"at": round(t, 3), "speaker": "self", "kind": "auto",
                             "text": note, "person": pid})
            record["woken"] = woke

        if speaker == "self":
            topic.on_self(text or "", t)
            record["kind"] = "self_message"
        else:
            topic.on_other(text or "", t)
            res = self.appraiser.evaluate(text or "")
            for label, delta in res.emotion.items():
                self.emotion.add(label, delta)
            # 哄人有冷却：10 分钟内连发十条"抱抱"只算一次
            if "care" in res.tags:
                if bond.comfort_ready(t):
                    bond.mark_comfort(t)
                else:
                    res.bond.pop("grievance", None)
            self._apply_bond(bond, res.bond, res.tags, t)
            self.needs.apply(res.needs)
            self.needs.touched(t)
            self.unanswered_proactive = 0
            record.update(
                {
                    "kind": "other_message",
                    "tags": res.tags,
                    "mood": res.mood,
                    "directed": res.directed,
                    "deltas": {
                        "emotion": {k: round(v, 3) for k, v in res.emotion.items()},
                        "bond": {k: round(v, 2) for k, v in res.bond.items()},
                        "needs": {k: round(v, 2) for k, v in res.needs.items()},
                    },
                }
            )

        if speaker == "self":
            self.memory.add(t, "her_word", text or "", person=pid, weight=4)
        else:
            self.memory.add(t, "said", text or "", tags=record.get("tags"), person=pid)
        self._log(record)
        self.save()
        return record

    def event(self, name: str, person=None, at=None) -> dict:
        """非消息事件：feed / sleep / video / nap。"""
        t = float(at) if at is not None else self.now()
        self._advance(t)
        pid = str(person or self.default_person)
        bond = self._bond(pid)
        name = str(name)

        if name == "feed":
            self.needs.apply({"hunger": -35, "thirst": -12})
            self.emotion.add("joyful", 0.2)
            bond.apply({"affinity": 1}, t)
            note = "吃了点东西"
        elif name == "drink":
            self.needs.apply({"thirst": -45})
            self.emotion.add("joyful", 0.1)
            bond.apply({"affinity": 1}, t)
            note = "喝了点水"
        elif name in ("sleep", "nap"):
            self.needs.apply({"energy": -55})
            note = "睡了一觉"
        elif name == "video":
            self.needs.apply({"boredom": -30})
            note = "刷了会儿视频"
        elif name == "apologize":
            self._apply_bond(bond, {"grievance": -30, "affinity": 3}, ["apology"], t)
            self.emotion.add("sad", -0.2)
            note = "收到道歉"
        else:
            raise ValueError(f"不认识的动作：{name}")

        record = {"at": round(t, 3), "kind": "event:" + name, "text": note, "person": pid}
        self.memory.add(t, "event", note, tags=[name], person=pid, weight=3)
        self._log(record)
        self.save()
        return record

    def tick(self, at=None) -> dict:
        t = float(at) if at is not None else self.now()
        self._advance(t)
        self.save()
        return self.snapshot(at=t)

    # ---------- 输出 ----------
    # ---------- 主动开口 & 发出去 ----------
    def pending_message(self, at=None) -> dict | None:
        """现在该不该开口？该的话说什么。不发，只算。"""
        t = float(at) if at is not None else self.now()
        bd = self._bond(self.default_person)
        needs = self.needs.to_dict(t, bd.affinity)
        bond = bd.to_dict(t)
        prox = inner_voice.decide(
            needs, bond, self.rules.get("proactive") or {},
            self.is_quiet(t), self.unanswered_proactive, self.last_proactive_at, t)
        if not prox.get("should_send"):
            return None
        scene = say_mod.pick_scene(needs, bond, clock=self.clock.state(t))
        said = len([x for x in self.log if x.get("kind") == "proactive"])
        return {"at": t, "text": say_mod.compose(scene, said), "scene": scene,
                "urgency": prox.get("urgency"), "reason": prox.get("reason")}

    def send_proactive(self, at=None) -> dict:
        """真的发到 QQ，并记账（发了什么、成没成、算不算"没回音"）。"""
        msg = self.pending_message(at)
        if not msg:
            return {"ok": False, "sent": False, "reason": "还不到开口的时候"}
        res = self.qq.send(msg["text"])
        ok = bool(res.get("ok"))
        entry = {"at": round(msg["at"], 3), "speaker": "self", "kind": "proactive",
                 "text": msg["text"], "person": self.default_person,
                 "sent": ok, "scene": msg["scene"]}
        if res.get("error"):
            entry["error"] = res["error"]
        self.log.append(entry)
        if len(self.log) > 60:
            self.log = self.log[-60:]
        if ok:
            self.last_proactive_at = msg["at"]
            self.unanswered_proactive += 1
            self.memory.add(msg["at"], "event", "主动找你：" + msg["text"],
                            person=self.default_person, weight=2)
        self.save()
        return {**msg, **res, "sent": ok}

    def snapshot(self, person=None, at=None) -> dict:
        t = float(at) if at is not None else self.now()
        self._advance(t)
        pid = str(person or self.default_person)
        bond, topic = self._bond(pid), self._topic(pid)
        needs = self.needs.to_dict(t, bond.affinity)
        idle_min = round((t - topic.last_msg_at) / 60.0, 1) if topic.last_msg_at else None
        return {
            "now": timeutil.iso(t),
            "version": __version__,
            "update": dict(self.updater.state),
            "person": pid,
            "name": self.char.get("name", "Tide"),
            "quiet": self.is_quiet(t),
            "emotion": {
                "label": self.emotion.label,
                "intensity": self.emotion.intensity,
                "pad": self.emotion.pad(),
                "raw": {k: round(v, 3) for k, v in self.emotion.levels.items()},
            },
            "needs": needs,
            "bond": bond.to_dict(t),
            "topic": {
                "state": topic.state,
                "waiting_reply": topic.her_last_asked,
                "idle_min": idle_min,
                "neglect": round(topic.neglect(t, bond.affinity, self.is_quiet(t)), 1),
            },
            "clock": self.clock.state(t),
            "just_woken": self.just_woken,
            "media": self.last_media,
            "auto": {
                "note": self.last_auto_note,
                "ago_min": (round((t - self.last_auto_at) / 60.0, 1)
                            if self.last_auto_at else None),
            },
            "log": self.log[-8:],
            "memory": self._memory_view(pid, t, idle_min),
            "settings": dict(self.settings.data),
        }

    def _memory_view(self, pid: str, t: float, idle_min) -> dict:
        neg = self.memory.last(t, tags=["hostile", "dismissive", "apology"], person=pid)
        pos = self.memory.last(t, tags=["praise", "care", "tease", "feeding"], person=pid)
        return {
            "digest": self.memory.digest(t, limit=3),
            "last_neg": self.memory.describe(neg, t) if neg else None,
            "last_pos": self.memory.describe(pos, t) if pos else None,
            "talk": {"idle_min": idle_min, "phrase": mem_mod.phrase_idle(idle_min)},
        }

    def plan_reply(self, person=None, at=None) -> dict:
        t = float(at) if at is not None else self.now()
        self._advance(t)
        pid = str(person or self.default_person)
        bond, topic = self._bond(pid), self._topic(pid)
        needs = self.needs.to_dict(t, bond.affinity)
        label = self.emotion.label
        tone = bond.tone
        mood = bond.mood

        if mood == "cold":
            max_chars = 6
        elif mood == "sulky":
            max_chars = 25
        elif mood == "slight" or label == "tired" or needs["energy"] > 70:
            max_chars = 40
        else:
            max_chars = 60

        banned = [str(x) for x in (self.char.get("boundaries") or [])]
        if bond.tier == "big" and not any("道歉" in b for b in banned):
            banned.append("讨好式道歉")
        if mood in ("cold", "sulky") and not any("追问" in b for b in banned):
            banned.append("连续追问")

        v = voice.voice_for(label, self.emotion.intensity, tone)
        prox = inner_voice.decide(
            needs, bond.to_dict(t), self.rules.get("proactive") or {},
            self.is_quiet(t), self.unanswered_proactive, self.last_proactive_at, t,
        )

        prompt = (
            f"当前情绪：{label}（强度 {self.emotion.intensity:.2f}）\n"
            f"需求：饿 {needs['hunger']:.0f}｜累 {needs['energy']:.0f}｜想你 {needs['longing']:.0f}｜无聊 {needs['boredom']:.0f}\n"
            f"关系：亲和 {bond.affinity:.0f}｜委屈 {bond.grievance:.0f}（{mood}"
            + (f"·{bond.hint(t)}" if bond.hint(t) else "")
            + "）\n"
            f"话题：{topic.state}｜{'在等你回答' if topic.her_last_asked else '没在等'}\n"
            f"→ 回复长度上限：{max_chars} 字\n"
            f"→ 语气：{tone}\n"
            f"→ 禁止：{'；'.join(banned) if banned else '无'}"
        )

        return {
            "tone": tone,
            "max_chars": max_chars,
            "banned": banned,
            "voice": v,
            "proactive": prox,
            "prompt": prompt,
        }

    def _log(self, record: dict) -> None:
        self.log.append(record)
        if len(self.log) > 60:
            self.log = self.log[-60:]

    # ---------- 持久化 ----------
    def save(self) -> None:
        if not self.state_path:
            return
        data = {
            "version": STATE_VERSION,
            "last_tick": self.last_tick,
            "offset": self.offset,
            "unanswered_proactive": self.unanswered_proactive,
            "last_proactive_at": self.last_proactive_at,
            "emotion": self.emotion.to_dict(),
            "needs": self.needs.save(),
            "bonds": {pid: b.save() for pid, b in self.bonds.items()},
            "topics": {pid: t.save() for pid, t in self.topics.items()},
            "log": self.log[-60:],
            "clock": self.clock.save(),
        }
        self.memory.save()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.state_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.clock.load(data.get("clock") or {})
        self.last_tick = float(data.get("last_tick", 0.0))
        self.offset = float(data.get("offset", 0.0))
        self.unanswered_proactive = int(data.get("unanswered_proactive", 0))
        self.last_proactive_at = float(data.get("last_proactive_at", 0.0))
        self.log = data.get("log") or []

        emo_cfg = self.cfg.get("emotion") or {}
        self.emotion = emo_mod.Emotion.from_dict(
            data.get("emotion"),
            baseline=emo_cfg.get("baseline") or self.char.get("baseline"),
            half_life=emo_cfg.get("half_life_min"),
            max_delta=emo_cfg.get("max_delta_per_event", 0.4),
            calm_threshold=emo_cfg.get("calm_threshold", 0.12),
        )
        self.needs.load(data.get("needs"))
        for pid, b in (data.get("bonds") or {}).items():
            self._bond(pid).load(b)
        for pid, tp in (data.get("topics") or {}).items():
            self._topic(pid).load(tp)

    def reset(self) -> dict:
        if self.state_path and self.state_path.exists():
            self.state_path.unlink()
        self.offset = 0.0
        self.last_tick = 0.0
        self.unanswered_proactive = 0
        self.last_proactive_at = 0.0
        self.log = []
        self.emotion = emo_mod.Emotion(
            baseline=(self.cfg.get("emotion") or {}).get("baseline") or self.char.get("baseline"),
            half_life=(self.cfg.get("emotion") or {}).get("half_life_min"),
            max_delta=(self.cfg.get("emotion") or {}).get("max_delta_per_event", 0.4),
            calm_threshold=(self.cfg.get("emotion") or {}).get("calm_threshold", 0.12),
        )
        self.needs = needs_mod.Needs(self.rules.get("needs") or {})
        self.clock = clock_mod.Circadian(self.rules.get("circadian") or {})
        self.just_woken = None
        self.last_media = None
        self.bonds, self.topics = {}, {}
        self.memory.items = []
        if self.memory.path and self.memory.path.exists():
            self.memory.path.unlink()
        return self.snapshot()