"""Tide · 本地面板（纯标准库，零依赖）。

    python -m tide.panel            # 默认 127.0.0.1:7880
    python -m tide.panel --port 7881

面板做两件事：
1. 把当前状态摊开（情绪 / 需求 / 关系 / 话题 / 给 LLM 的那段软约束）
2. 画"从现在起没人说话，未来 24 小时她怎么变" —— 这是 P0/P1 唯一能验收的地方
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import TideCore
from .forecast import forecast
from .version import __version__


LOCK = threading.Lock()
STARTED_AT = time.time()
SERVER: ThreadingHTTPServer | None = None
ROOT = Path(__file__).resolve().parent.parent


def _metadata() -> dict:
    try:
        return json.loads((ROOT / "metadata.json").read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


# ── 单实例锁：同一台机器只能有一个 Tide 在推进时间 ──

LOCK_FILE = ROOT / "data" / "panel.lock"


class _Server(ThreadingHTTPServer):
    """不允许两个实例抢同一个端口（Windows 默认是允许的，这正是双开的原因）。"""

    allow_reuse_address = False
    daemon_threads = True


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
        if handle:
            k32.CloseHandle(handle)
            return True
        # 5 = 拒绝访问：进程确实在，只是不归我们管 —— 也算活着
        return k32.GetLastError() == 5
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _take_lock() -> bool:
    try:
        got = int(LOCK_FILE.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        got = 0
    if got and got != os.getpid() and _alive(got):
        return False
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCK_FILE.write_text(str(os.getpid()), encoding="ascii")
    except OSError:
        return True          # 写不了锁文件就别挡着启动
    return True


def _drop_lock() -> None:
    try:
        if LOCK_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            LOCK_FILE.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def payload(core: TideCore, person: str | None = None) -> dict:
    with LOCK:
        snap = core.snapshot(person=person)
        plan = core.plan_reply(person=person)
    return {
        "snapshot": snap,
        "plan": plan,
        "series": forecast(core, hours=24.0, step_h=0.5),
    }


def _query(path: str) -> dict:
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(path).query)
    return {k: v[0] for k, v in q.items() if v}


def make_handler(core: TideCore):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, code: int, body, ctype="application/json; charset=utf-8"):
            raw = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, HTML, "text/html; charset=utf-8")
            elif path == "/api/state":
                person = _query(self.path).get("person")
                if person:
                    with LOCK:
                        snap = core.snapshot(person=person)
                        plan = core.plan_reply(person=person)
                    body = json.dumps({"snapshot": snap, "plan": plan}, ensure_ascii=False)
                else:
                    body = json.dumps(payload(core), ensure_ascii=False)
                self._send(200, body)
            elif path == "/api/health":
                # 契约见海螺 docs/插件对接契约.md：只报「进程活着」
                self._send(200, json.dumps({
                    "ok": True,
                    "id": "tide",
                    "version": __version__,
                    "person": core.default_person,
                    "uptime_s": round(time.time() - STARTED_AT, 1),
                }, ensure_ascii=False))
            elif path == "/api/manifest":
                self._send(200, json.dumps({
                    "ok": True,
                    "metadata": _metadata(),
                    "runtime": {
                        "port": SERVER.server_address[1] if SERVER else 0,
                        "pid": os.getpid(),
                        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(STARTED_AT)),
                    },
                    "capabilities": [
                        {"name": "情绪与关系账本", "kind": "http", "how": "GET /api/state、POST /api/observe"},
                        {"name": "判断该不该主动开口", "kind": "http", "how": "POST /api/woke（宿主回报发没发成）"},
                        {"name": "主动消息对接（让宿主开口）", "kind": "http", "how": "见 docs/主动消息-对接.md"},
                        {"name": "喂提示词（说话分寸）", "kind": "mcp", "how": "插件 plugins/mood 的 speech.prompt"},
                        {"name": "设置与更新", "kind": "http", "how": "GET /api/settings、GET /api/update"},
                    ],
                }, ensure_ascii=False))
            elif path == "/api/settings":
                self._send(200, json.dumps(core.settings.public(), ensure_ascii=False))
            elif path == "/api/update":
                self._send(200, json.dumps(core.updater.check(force="force" in self.path),
                                           ensure_ascii=False))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(length) or b"{}")
            except Exception:
                data = {}
            path = self.path.split("?")[0]
            result = None
            try:
                if path == "/api/observe":
                    person = data.get("person") or None
                    with LOCK:
                        core.observe(
                            text=data.get("text", ""),
                            speaker=data.get("speaker", "other"),
                            person=person,
                            initiated=bool(data.get("initiated", False)),
                        )
                elif path == "/api/woke":
                    with LOCK:
                        result = core.mark_woke()
                elif path == "/api/event":
                    with LOCK:
                        core.event(data.get("name", ""))
                elif path == "/api/advance":
                    with LOCK:
                        core.advance(float(data.get("hours", 1)))
                elif path == "/api/reset":
                    with LOCK:
                        core.reset()
                elif path == "/api/settings":
                    with LOCK:
                        result = core.update_settings(data)
                elif path == "/api/say":
                    with LOCK:
                        result = core.send_proactive()
                elif path == "/api/proactive-report":
                    # 宿主说完了没：成功/失败都要回，失败不能当成功记账
                    with LOCK:
                        result = core.report_proactive(
                            str(data.get("event_id") or ""),
                            bool(data.get("sent")),
                            text=str(data.get("text") or ""),
                            error=str(data.get("error") or ""),
                        )
                elif path == "/api/update":
                    result = core.updater.apply()
                self._send(200, json.dumps(result if result is not None else payload(core),
                                           ensure_ascii=False))
            except (KeyError, ValueError) as exc:
                self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False))
            except Exception as exc:  # 面板不该把异常吞掉
                self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False))

    return Handler


def brain_loop(core: TideCore, every: float = 60.0, send: bool = False) -> None:
    """她的心跳：定期把状态往前推、落盘。

    开口这件事现在统一走 core.tick()：
      · 配了宿主（海螺）→ 只通知一句，由宿主用自己的嘴说
      · 没配宿主、又开了 wake.auto_send → 退回自带的那张嘴
    所以这里不再分叉，免得两条路各记各的账。
    """
    import time as _t
    while True:
        _t.sleep(every)
        try:
            core.tick()        # 推进时间 + 存档 + 到线时通知宿主
        except Exception:
            pass


def serve(core: TideCore, host: str = "127.0.0.1", port: int = 7880) -> None:
    global SERVER
    # Windows 上 SO_REUSEADDR 会让第二个实例**也能绑上同一个端口**，
    # 于是两个 Tide 各跑各的时钟、共用一份 state.json —— 表现就是
    # 「刚说完一句，两分钟后又冒一句」「冷却像没生效」。所以这里自己锁死单例。
    if not _take_lock():
        print(f"Tide · 已经有一个面板在跑了，这个实例退出（端口 {port}）")
        return
    server_cls = _Server
    try:
        httpd = server_cls((host, port), make_handler(core))
    except OSError as exc:
        print(f"Tide · 端口 {port} 起不来：{exc}（可能已经有一个在跑）")
        _drop_lock()
        return
    SERVER = httpd
    print(f"Tide · 面板已起： http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parent.parent

    def arg(name, default):
        if name in argv:
            return argv[argv.index(name) + 1]
        return default

    core = TideCore.from_config(
        arg("--config", root / "config"),
        state_path=Path(arg("--state", root / "data" / "state.json")),
    )
    auto_send = bool((core.rules.get("wake") or {}).get("auto_send", False))
    if auto_send and ("--brain" in argv or core.qq.enabled):
        # 只有显式开了 auto_send 才让她自己往外发；默认只推进状态
        threading.Thread(target=brain_loop, args=(core, 60.0, True), daemon=True).start()
    elif "--brain" in argv or core.qq.enabled:
        threading.Thread(target=brain_loop, args=(core, 60.0, False), daemon=True).start()
    port = int(arg("--port", 7880))
    core.updater.port = port            # 更新完要重启回同一个端口
    core.updater.check_async()          # 后台查一次有没有新版本，不挡启动
    serve(core, port=port)


# 页面本体在 web_ui.py（HTML/CSS/JS 都在那边）
from .web_ui import HTML  # noqa: E402


if __name__ == "__main__":
    main()
