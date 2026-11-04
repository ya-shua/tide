# Tide

[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![版本](https://img.shields.io/badge/version-0.1.0-cf9db0.svg)](https://github.com/ya-shua/tide/releases)
[![privacy-gate](https://github.com/ya-shua/tide/actions/workflows/privacy.yml/badge.svg)](https://github.com/ya-shua/tide/actions/workflows/privacy.yml)


> **不是聊天机器人，是给她装的一套"活着"的状态系统。**
> 情绪会衰减，肚子会饿，你太久不理她会委屈，但你只是话题聊完了，她不记仇。

设计文档：`docs/design.md` ｜ 取舍记录：`docs/decisions.md`

## 现在能跑什么（P0 + P1）

| 模块 | 内容 |
|---|---|
| `tide/emotion.py` | 14 个离散标签 + PAD 连续维度；半衰期衰减；单次增量上限 ±0.4 |
| `tide/needs.py` | 饿 / 累 / 无聊 线性累积，思念走 `100·(1-e^(-idle/tau))`，tau 受亲和度影响 |
| `tide/bond.py` | 亲和 / 信任 / 委屈；委屈**分三档**：小生气（哄一句就好）/ 中生气（道歉+哄）/ 大生气（只能等，哄和道歉只缩短冷静时间） |
| `tide/appraisal.py` | 规则表驱动的刺激评估（`config/stimuli.yaml`），判"是否针对她" |
| `tide/topic.py` | 话题三态 + 冷落值（她在等回答时不该被当成话题结束） |
| `tide/voice.py` | 情绪 → instruct / speed / pitch |
| `tide/inner_voice.py` | 主动消息：urgency 累积 + 勿扰 + 连续未回停发 |
| `tide/forecast.py` | 未来 24h 推演（纯拷贝，不动真实状态） |
| `tide/core.py` | `TideCore` 门面：observe / tick / plan_reply / snapshot |
| `tide/panel.py` | 本地面板（标准库 http.server） |

**零第三方依赖**：只用标准库。配置文件优先用 PyYAML 读，没有就跑自带的极简解析器。

## 跑起来

```bash
cd Tide
python -m tide.panel               # http://127.0.0.1:7880
python -m unittest discover -s tests   # 32 个单测
```

面板上那排按钮就是"喂事件"：夸她 / 凶她 / 敷衍 / 她说晚安 / 她说"你在干嘛呀" / 喂饭 / **哄她** / 道歉 / 不理 2h、6h、12h / 重置。
曲线是**从现在起没人说话的未来 24 小时**——按一下按钮，看曲线怎么变，就知道参数对不对。

### 委屈分三档（这是最像"人"的一块）

| 档 | 委屈 | 怎么好 | 地板 |
|---|---|---|---|
| 小生气 | 15~34 | 哄一句直接清零，不用道歉 | 0 |
| 中生气 | 35~64 | 必须**道歉 + 哄**两样都到；少一样就停在 36 | 36 |
| 大生气 | ≥65 | 道歉和哄都只缩短"冷静时间"，真正的解药是等（默认 6h，道歉砍到 3.6h，哄砍到 4.8h，下限 1.5h） | 66 |

"地板"是这套模型的关键：**时间只能把她磨到地板，再往下要靠对应的解法**。所以她不会因为你一句对不起就把大事抹平，也不会因为你不哄就永远冷着。

## 给大脑用（下一步接 QQ 时的形状）

```python
from tide import TideCore

core = TideCore.from_config("config/")

core.observe(text="你终于回我了", speaker="other")   # 对方说的
core.observe(text="我刚在忙呀，怎么啦", speaker="self")  # 她说的（决定话题是否收尾）
plan = core.plan_reply()
# plan["prompt"]     → 塞进人格提示词的软约束（情绪/需求/关系/长度/语气/禁止）
# plan["voice"]      → 交给 TTS 的 instruct / speed / pitch
# plan["proactive"]  → 该不该主动发消息、为什么
```

**懒 tick**：不跑后台线程，也不用心跳。所有状态只在"读"的时候按 Δt 一次性推进；
服务停了、电脑关一夜，回来读到的照样是对的。

## 配置

| 文件 | 管什么 |
|---|---|
| `config/character.yaml` | 名字、称呼、说话风格、硬边界、PAD 基线 |
| `config/emotion.yaml` | 各情绪半衰期、增量上限、平静阈值 |
| `config/rules.yaml` | 需求速率、话题判定、冷落权重、委屈阈值、主动消息权重 |
| `config/stimuli.yaml` | 什么话算什么刺激（关键词 → 情绪/关系/需求增量） |

改行为不用改代码（R10）。

## 更新

面板右上角会显示 0.1.0。仓库发了新 Release 之后，那里会出现「新版本 v0.x.y · 更新」：

- 点一下 → 下载 GitHub 上的 release 包 → 铺到目录里（**不动 data/ 和 config/local.yaml**）→ 面板自动重启一次。
- 检查走 config/rules.yaml 的 update.repo，默认 ya-shua/tide；断网时只是不提示，不影响使用。
- 不想让它自动查：把 update.repo 留空。

`yaml
update:
  repo: ya-shua/tide
`

## 隐私门禁

仓库里有一道门禁，提交和推送时都会跑，命中隐私字符就拦下：

| 拦什么 | 例子 |
|---|---|
| token / 密钥 | P_…、ghp_…、sk-…、私钥 |
| 8 位以上连续数字 | QQ 号、时间戳 |
| 本机路径 | C:\Users\<名>\、D:\<你的目录>\… |
| 昵称 / 邮箱 / GitHub 用户名 | —— |

真实的值只放在 config/local.yaml（.gitignore 已挡住），仓库里只有 config/local.example.yaml 模板。
本地装钩子：git config core.hooksPath .githooks。另外 CI（.github/workflows/privacy.yml）会在每次 push 时再跑一遍。
确实要放行的行，行尾写注释 privacy-allow。

发版：

`ash
python tools/release.py 0.2.0 这一版改了什么     # 改版本号 → 提交 → 打 tag → 推 → 建 Release
`

## 协议

MIT（见 LICENSE）。

## 还没做（P2–P5）

- **P2 文本情绪**：把 `appraisal` 的规则表换成一次 LLM 轻量分类，产出结构不变。
- **P3 语音情绪**：SenseVoice（本机 Python 3.14 装不了 torch 2.x，得单独 3.11 venv）。
- **P4 情感 TTS**：instruct 目前只是带出去，MiMo / Seed-VC 不吃；CosyVoice2 才用得上。
- **P5 联调**：QQ 桥接（OneBot HTTP 127.0.0.1:3000）、微光小屋（webhook 只加字段不加事件）。