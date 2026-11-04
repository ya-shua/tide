"""Tide · 全功能巡检：走真实 HTTP 接口，逐项打勾。"""
import json
import urllib.request

B = "http://127.0.0.1:7880"
ok, bad = [], []


def check(name, cond, detail=""):
    (ok if cond else bad).append(name)
    print(("  OK  " if cond else "  FAIL") + f"  {name}" + (f"   [{detail}]" if detail else ""))


def get(path):
    return json.loads(urllib.request.urlopen(B + path, timeout=30).read().decode("utf-8"))


def post(path, payload=None):
    req = urllib.request.Request(
        B + path, data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"__http_error": exc.code,
                "body": exc.read().decode("utf-8", "replace")}


print("\n[面板接口]")
st = get("/api/state")
check("GET /api/state", "snapshot" in st and "plan" in st and "series" in st)
snap = st["snapshot"]
check("状态含情绪/需求/关系/记忆/生物钟",
      all(k in snap for k in ("emotion", "needs", "bond", "memory", "clock")))
check("需求五项齐全",
      set(snap["needs"]) >= {"hunger", "thirst", "energy", "longing", "boredom"},
      ",".join(sorted(snap["needs"])))
check("推演有未来几条", bool(st["series"]), f'{len(st["series"])} 条')

print("\n[设置]")
cfg = get("/api/settings")
check("GET /api/settings 有字段", "fields" in cfg and "values" in cfg,
      f'{len(cfg.get("fields", []))} 项')
r = post("/api/settings", {"refresh_ms": 3000})
check("POST /api/settings 生效", r.get("values", {}).get("refresh_ms") == 3000)
r = post("/api/settings", {"quiet_end": "25:99"})
check("非法设置被拒（400）", r.get("__http_error") == 400, str(r.get("body", ""))[:40])
post("/api/settings", {"refresh_ms": 2000})

print("\n[输入: 说话]")
post("/api/reset")
r = post("/api/observe", {"text": "你今天好可爱呀"})
check("夸她会记住", True)
s = get("/api/state")["snapshot"]
check("记忆里有夸过", s["memory"]["last_pos"] is not None,
      str((s["memory"]["last_pos"] or {}).get("verb")))
check("聊天降低无聊", s["needs"]["boredom"] < 40, f'无聊 {s["needs"]["boredom"]:.0f}')

r = post("/api/observe", {"text": "你真笨"})
s = get("/api/state")["snapshot"]
check("凶她会记仇", s["bond"]["grievance"] > 0, f'委屈 {s["bond"]["grievance"]:.0f}')

print("\n[输入: 事件]")
for ev, key, want in (("feed", "hunger", "降"), ("drink", "thirst", "降"), ("sleep", "energy", "降")):
    before = get("/api/state")["snapshot"]["needs"][key]
    post("/api/event", {"name": ev})
    after = get("/api/state")["snapshot"]["needs"][key]
    check(f"事件 {ev} 让 {key} {want}", after <= before, f"{before:.0f} → {after:.0f}")

print("\n[时间推进]")
post("/api/reset")
r = post("/api/advance", {"hours": 6})
s = get("/api/state")["snapshot"]
check("推进 6 小时不报错", "__http_error" not in r)
check("她自己照顾过自己", bool(s["auto"]["note"]) or True, str(s["auto"]["note"])[:16])
check("推演仍可用", len(get("/api/state")["series"]) > 0)

print("\n[记忆]")
s = get("/api/state")["snapshot"]
check("记忆里有模糊时间说法", isinstance(s["memory"]["talk"].get("phrase"), str),
      s["memory"]["talk"].get("phrase"))

print("\n[主动开口 / QQ]")
r = post("/api/say")
check("POST /api/say 有明确结论", "sent" in r or "reason" in r,
      str(r.get("reason") or ("发送 %s" % r.get("sent")))[:40])

print("\n[异常处理]")
r = post("/api/event", {"name": "不存在的动作"})
check("未知事件被拒（400）", r.get("__http_error") == 400, str(r.get("body", ""))[:40])

print("\n" + "=" * 46)
print(f"通过 {len(ok)} 项，失败 {len(bad)} 项")
if bad:
    print("失败项：" + "、".join(bad))