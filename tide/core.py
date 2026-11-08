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


def _person_label(pid: str) -> str:
    """面板/提示词里给人看的名字（id 本身是稳定键，别拿它当名字）。"""
    pid = str(pid or "")
    if pid.startswith("group:"):
        return "群 " + pid.split(":", 1)[1]
    if pid.startswith("qq:"):
        return "QQ " + pid.split(":", 1)[1]
    return pid


# 情绪的小标签 → 七情里的哪一情（提示词里说人话用）
_MOOD_FAMILY = {
    "joy": "开心", "anger": "生气", "worry": "担心", "longing": "想你",
    "sorrow": "难过", "fear": "怕", "surprise": "意外", "calm": "平静",
}


def _tone_line(affinity: float, family: str, intensity: float = 0.0) -> str:
    """好感 × 心情 → 一句「说话的分寸」。

    好感是底盘（这个人值不值得客气），心情是当天的脾气。同样的气，对着好感高的
    人她会压着，对着好感低的人就直接炸；同样是高兴，熟的人面前才黏。
    """
    near = affinity >= 70
    far = affinity < 35
    strong = intensity >= 0.5

    if family == "anger":
        if far:
            return "说话的分寸：火已经上来了，对他也没什么好气——可以冲，话要短，别哄。"
        if near:
            return "说话的分寸：在生气，但跟他关系近——压着火说，别撂狠话。"
        return "说话的分寸：在生气，克制着说，别翻旧账。"

    if family == "joy":
        if near:
            return "说话的分寸：心情好，也喜欢他——可以黏一点、多说两句。" if strong else "说话的分寸：心情不错，跟他亲近——放松点说。"
        if far:
            return "说话的分寸：心情不错，但跟他关系一般——客气点，不必热络。"
        return "说话的分寸：心情不错，正常说就行。"

    if family in ("sorrow", "worry", "fear"):
        what = {"sorrow": "难过", "worry": "担心", "fear": "有点怕"}[family]
        if near:
            return f"说话的分寸：心里{what}，他是能说的人——可以露一点，别演。"
        if far:
            return f"说话的分寸：心里{what}，跟他没那么熟——收着点，别倒苦水。"
        return f"说话的分寸：心里{what}，正常说，别硬撑也别夸张。"

    if family == "longing":
        if near:
            return "说话的分寸：想他了——可以直接说想，别绕。"
        return "说话的分寸：有点想聊，但跟他没那么熟——正常说，别提想念。"

    return "说话的分寸：心里平静，正常说话就行。"
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

        # 主动打扰那一套：阈值 / 冷却三模式 / 打扰上限 / 自动免打扰
        wk = dict(self.rules.get("wake") or {})
        self.wake_cfg = {
            "longing": float(wk.get("longing", 60)),
            "boredom": float(wk.get("boredom", 60)),
            "worried": float(wk.get("worried", 70)),
            "cooldown_mode": str(wk.get("cooldown_mode", "dec")),
            "cooldown_min": float(wk.get("cooldown_min", 90)),
            "cooldown_step": float(wk.get("cooldown_step", 20)),
            "max_wakes": int(wk.get("max_wakes", 6)),
            "auto_dnd_after": int(wk.get("auto_dnd_after", 3)),
            "dnd_manual_rate": float(wk.get("dnd_manual_rate", 1.0)),
            "dnd_auto_rate": float(wk.get("dnd_auto_rate", 2.0)),
            "dnd_none_rate": float(wk.get("dnd_none_rate", 4.0)),
        }
        self.dnd = "off"                 # off / manual / auto
        self.wake_marks = []             # 今天叫醒过几次（时间戳）
        self.last_wake_at = 0.0

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
        # 作息：几点睡、睡多久，跟累和情绪走
        def _hm(text):
            h, m = str(text).split(":")
            return int(h) + int(m) / 60.0
        clock = self.clock.cfg
        clock["normal_onset"] = _hm(st["sleep_normal"])
        clock["earliest_onset"] = _hm(st["sleep_earliest"])
        latest = _hm(st["sleep_latest"])
        if latest < clock["earliest_onset"]:
            latest += 24.0          # 02:00 这种跨零点的写法
        clock["latest_onset"] = latest
        clock["min_hours"] = float(st["sleep_min_h"])
        clock["max_hours"] = float(st["sleep_max_h"])
        clock["mood_delay_max"] = float(st["sleep_mood_delay"])
        # 面板上的"主动"那组：直接改叫醒条件，不用重启
        for key, field in (("longing", "wake_longing"), ("boredom", "wake_boredom"),
                           ("worried", "wake_worried"),
                           ("cooldown_min", "wake_cooldown_min"),
                           ("auto_dnd_after", "wake_auto_dnd_after")):
            if field in st:
                self.wake_cfg[key] = float(st[field])
        if "wake_max" in st:
            self.wake_cfg["max_wakes"] = int(st["wake_max"])
        if st.get("wake_cooldown_mode") in ("dec", "fixed", "inc"):
            self.wake_cfg["cooldown_mode"] = st["wake_cooldown_mode"]
        if "wake_hold_min" in st:
            self.needs.hold_min = float(st["wake_hold_min"])
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
            for kind, val in self.clock.step(chunk, ts, self.needs.energy,
                                             self.emotion.levels):
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
        self._refresh_dnd()
        self._dnd_flow(secs, t)
        self._absorb_self_care(secs, t)

        self.last_tick = t

    # ---------- 免打扰 ----------
    def _refresh_dnd(self) -> str:
        """manual 由人按按钮；auto 是"连着几条没回，她开始觉得你在忙"。"""
        if self.dnd == "manual":
            return self.dnd
        need = self.wake_cfg["auto_dnd_after"]
        if need > 0 and self.unanswered_proactive >= need:
            self.dnd = "auto"
        elif self.unanswered_proactive == 0:
            self.dnd = "off"
        return self.dnd

    def set_dnd(self, on: bool) -> str:
        self.dnd = "manual" if on else "off"
        return self.dnd

    def _dnd_flow(self, secs: float, t: float) -> None:
        """等回音的时候委屈在涨；免打扰只是让它涨得慢一点，不是不涨。"""
        if secs <= 0 or self.unanswered_proactive <= 0:
            return
        key = {"manual": "dnd_manual_rate", "auto": "dnd_auto_rate"}.get(
            self.dnd, "dnd_none_rate")
        rate = float(self.wake_cfg.get(key, 4.0))
        add = rate * secs / 3600.0
        if add <= 0:
            return
        self._apply_bond(self._bond(self.default_person),
                         {"grievance": add}, ["dnd:" + self.dnd], t)

    def _reply_quality(self, text: str, res) -> float:
        """你这一句有多"实"：长句、有来有回、有关心，才算真聊上了。

        回一句"嗯"只算 0.06，聊开了单句能到 0.2~0.3。
        """
        body = (text or "").strip()
        q = 0.06
        n = len(body)
        if n >= 10:
            q += 0.04
        if n >= 30:
            q += 0.06
        if n >= 60:
            q += 0.06
        if "？" in body or "?" in body:
            q += 0.04
        if "care" in (getattr(res, "tags", None) or []):
            q += 0.08
        return round(min(0.30, q), 3)

    # ---------- 输入 ----------
    def observe(self, text=None, speaker="other", person=None, at=None,
                initiated: bool = False) -> dict:
        """initiated=True：她自己主动开口（不是回你），会开启缓解期。"""
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
            if initiated:
                # 她主动开口：想念不降，但开始"缓一缓"；等回音期间委屈会涨
                self.needs.spoke(t, bond.affinity)
                self.unanswered_proactive += 1
                self._refresh_dnd()
                record["kind"] = "self_initiated"
                record["hold_until"] = round(self.needs.hold_until, 1)
        else:
            idle_h = max(0.0, (t - self.needs.last_seen) / 3600.0) if self.needs.last_seen else 0.0
            # 只有"她真的在等你回音"的时候，久等才算委屈；一般聊天间隔不算
            waiting = self.unanswered_proactive > 0
            was_dnd = self._refresh_dnd()
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
            # 你终于回了：按这句有多"实"降想念；聊不够的，剩下的会自己涨回来
            quality = self._reply_quality(text or "", res)
            cut = self.needs.touched(t, bond.affinity, quality)
            if quality >= 0.12:
                # 被认真回应 → 亲近感上来（想念不是消失，是变成了踏实）
                self.emotion.add("affectionate", round(0.05 + quality * 0.3, 3))
                self.emotion.add("joyful", round(quality * 0.25, 3))
            late = min(50.0, 6.0 * idle_h) if (waiting and idle_h >= 0.5) else 0.0
            if late > 0:
                self._apply_bond(bond, {"grievance": late}, ["replied_late"], t)
                self.emotion.add("annoyed", min(0.25, late / 200.0))
                # 久别重逢：先高兴一下，再算委屈的账
                self.emotion.add("joyful", 0.2)
                record["late_grievance"] = round(late, 1)
            self.unanswered_proactive = 0
            self.dnd = "off"
            record.update(
                {
                    "kind": "other_message",
                    "tags": res.tags,
                    "mood": res.mood,
                    "directed": res.directed,
                    "idle_h": round(idle_h, 2),
                    "was_dnd": was_dnd,
                    "quality": quality,
                    "longing_drop": cut,
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

    # ---------- 该不该叫醒她 ----------
    def _wakes_today(self, t: float) -> int:
        import time as _time
        day = _time.strftime("%Y-%m-%d", _time.localtime(t))
        return sum(1 for x in self.wake_marks
                   if _time.strftime("%Y-%m-%d", _time.localtime(x)) == day)

    def _cooldown_now(self, t: float) -> float:
        """冷却三模式：递减（越等越急）/ 固定 / 递增（越等越克制）。"""
        mode = str(self.wake_cfg.get("cooldown_mode") or "dec")
        base = float(self.wake_cfg.get("cooldown_min") or 90)
        step = float(self.wake_cfg.get("cooldown_step") or 20)
        n = max(0, self._wakes_today(t) - 1) if self.wake_marks else 0
        if mode == "dec":
            return max(5.0, base - step * n)
        if mode == "inc":
            return base + step * n
        return base

    def should_wake(self, at=None) -> dict:
        """现在要不要叫醒她（只判断，不叫）。"""
        t = float(at) if at is not None else self.now()
        self._refresh_dnd()
        pid = self.default_person
        bond = self._bond(pid)
        needs = self.needs.to_dict(t, bond.affinity)
        worried = self.emotion.levels.get("worried", 0.0) * 100
        cfg = self.wake_cfg
        wishes = {
            "longing": needs["longing"] >= cfg["longing"],
            "boredom": needs["boredom"] >= cfg["boredom"],
            "worried": worried >= cfg["worried"],
        }
        count = self._wakes_today(t)
        cooldown = self._cooldown_now(t)
        out = {
            "wake": False, "why": "", "dnd": self.dnd,
            "wishes": wishes, "needs": needs, "worried": round(worried, 1),
            "count_today": count, "max_wakes": cfg["max_wakes"],
            "cooldown_min": round(cooldown, 1),
            "next_in_min": None,
        }
        if self.dnd == "manual":
            out["why"] = "你开了免打扰，她知道你在忙"
            return out
        if self.is_quiet(t):
            out["why"] = "休息时间"
            return out
        if not any(wishes.values()):
            out["why"] = "还不到想找你的程度"
            return out
        if cfg["max_wakes"] > 0 and count >= cfg["max_wakes"]:
            out["why"] = f"今天已经找过你 {count} 次，忍住了"
            return out
        wait = cooldown - (t - self.last_wake_at) / 60.0 if self.last_wake_at else 0.0
        if wait > 0:
            out["why"] = f"还在冷却（还要 {wait:.0f} 分钟）"
            out["next_in_min"] = round(wait, 1)
            return out
        out["wake"] = True
        hit = [k for k, v in wishes.items() if v]
        out["why"] = "；".join(
            {"longing": f"想你 {needs['longing']:.0f}",
             "boredom": f"无聊 {needs['boredom']:.0f}",
             "worried": f"担心 {worried:.0f}"}[k] for k in hit)
        return out

    def mark_woke(self, at=None) -> dict:
        t = float(at) if at is not None else self.now()
        self.last_wake_at = t
        self.wake_marks.append(t)
        self.wake_marks = self.wake_marks[-50:]
        self.save()
        return {"at": t, "count_today": self._wakes_today(t)}

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
        scene = say_mod.pick_scene(needs, bond, clock=self.clock.state(
            t, self.needs.energy, self.emotion.levels))
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
            self.mark_woke(msg["at"])
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
                "accounts": self.emotion.accounts(),
                "breakdown": self.emotion.breakdown(),
                "raw": {k: round(v, 3) for k, v in self.emotion.levels.items()},
            },
            "feelings": self._feelings(t, pid),
            "dnd": self.dnd,
            "wake": self.should_wake(t),
            "needs": needs,
            "bond": bond.to_dict(t),
            "topic": {
                "state": topic.state,
                "waiting_reply": topic.her_last_asked,
                "idle_min": idle_min,
                "neglect": round(topic.neglect(t, bond.affinity, self.is_quiet(t)), 1),
            },
            "clock": self.clock.state(t, self.needs.energy, self.emotion.levels),
            "just_woken": self.just_woken,
            "media": self.last_media,
            "auto": {
                "note": self.last_auto_note,
                "ago_min": (round((t - self.last_auto_at) / 60.0, 1)
                            if self.last_auto_at else None),
            },
            "log": self.log[-8:],
            "memory": self._memory_view(pid, t, idle_min),
            "persons": self._person_list(t, pid),
            "settings": dict(self.settings.data),
        }

    def _person_list(self, t: float, active: str) -> list:
        """面板上能切的人/群：有关系的都列出来。"""
        out = []
        for pid in self.bonds:
            bond = self.bonds[pid]
            topic = self.topics.get(pid)
            last = float(getattr(topic, "last_msg_at", 0.0) or 0.0)
            label = _person_label(pid)
            out.append({
                "id": pid,
                "label": label,
                "affinity": round(float(getattr(bond, "affinity", 0.0)), 1),
                "tier_name": str(getattr(bond, "tier_name", "") or ""),
                "topic": str(getattr(topic, "state", "") or ""),
                "idle_min": (round((t - last) / 60.0, 1) if last else None),
            })
        # 正在看的排最前，其余按「刚说过话」排
        out.sort(key=lambda x: (x["id"] != active, x["idle_min"] is None, x["idle_min"] or 0.0))
        return out

    def _memory_view(self, pid: str, t: float, idle_min) -> dict:
        neg = self.memory.last(t, tags=["hostile", "dismissive", "apology"], person=pid)
        pos = self.memory.last(t, tags=["praise", "care", "tease", "feeding"], person=pid)
        return {
            "digest": self.memory.digest(t, limit=3, person=pid),
            "last_neg": self.memory.describe(neg, t) if neg else None,
            "last_pos": self.memory.describe(pos, t) if pos else None,
            "talk": {"idle_min": idle_min, "phrase": mem_mod.phrase_idle(idle_min)},
        }

    # ---------- 表达 ----------
    FEEL_WORD = {
        "angry": "生气", "annoyed": "闷", "jealous": "有点吃醋",
        "worried": "担心", "uneasy": "不太安心", "sad": "难过",
        "disappointed": "失望", "lonely": "孤单", "nostalgic": "有点怀念",
        "yearning": "想他", "scared": "害怕", "guilty": "心虚",
        "shy": "害羞", "proud": "得意", "joyful": "开心", "excited": "兴奋",
        "playful": "想闹", "grateful": "感动", "hopeful": "期待",
        "surprised": "意外", "embarrassed": "尴尬", "tired": "累", "bored": "没劲", "affectionate": "想亲近他",
    }

    def _feelings(self, t: float, pid: str) -> str:
        """把状态翻译成第一人称的感受，不是体检报告。"""
        bond = self._bond(pid)
        needs = self.needs.to_dict(t, bond.affinity)
        bits = []
        for item in self.emotion.breakdown(limit=3):
            v = item["value"]
            if v < 12:
                continue
            word = self.FEEL_WORD.get(item["label"], item["label"])
            bits.append(("有点" if v < 35 else "很") + word)
        if needs["longing"] >= 55 and "longing" not in [b for b in bits]:
            bits.append("想他" if needs["longing"] < 80 else "很想他")
        if needs["hunger"] >= 70:
            bits.append("饿")
        if needs["energy"] >= 70:
            bits.append("累")
        if needs["boredom"] >= 55:
            bits.append("闲得慌")
        if not bits:
            return "没什么特别的心情，挺平静的。"
        text = "，".join(bits)
        if self.unanswered_proactive > 0:
            text += "。刚才找过他，还没回音"
        return "心里" + text + "。"

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

        # 不写"上限多少字""禁止说什么"——那些是拿规则压她；
        # 只把此刻的心情用第一人称说给她听，剩下的交给性格。
        prompt = (
            f"你现在的心情：{self._feelings(t, pid)}\n"
            f"需求：饿 {needs['hunger']:.0f}｜累 {needs['energy']:.0f}｜"
            f"想你 {needs['longing']:.0f}｜无聊 {needs['boredom']:.0f}\n"
            f"关系：亲和 {bond.affinity:.0f}｜委屈 {bond.grievance:.0f}（{mood}"
            + (f"·{bond.hint(t)}" if bond.hint(t) else "")
            + "）\n"
            + _tone_line(bond.affinity, *self.emotion.dominant()) + "\n"
            f"话题：{topic.state}｜{'在等你回答' if topic.her_last_asked else '没在等'}"
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
            "dnd": self.dnd,
            "wake_marks": self.wake_marks[-50:],
            "last_wake_at": self.last_wake_at,
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
        self.dnd = str(data.get("dnd", "off")) if data.get("dnd") in ("off", "manual", "auto") else "off"
        self.wake_marks = [float(x) for x in (data.get("wake_marks") or [])][-50:]
        self.last_wake_at = float(data.get("last_wake_at", 0.0))
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
        self.dnd = "off"
        self.wake_marks = []
        self.last_wake_at = 0.0
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