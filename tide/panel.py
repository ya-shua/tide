"""Tide · 本地面板（纯标准库，零依赖）。

    python -m tide.panel            # 默认 127.0.0.1:7880
    python -m tide.panel --port 7881

面板做两件事：
1. 把当前状态摊开（情绪 / 需求 / 关系 / 话题 / 给 LLM 的那段软约束）
2. 画"从现在起没人说话，未来 24 小时她怎么变" —— 这是 P0/P1 唯一能验收的地方
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import TideCore
from .forecast import forecast


def payload(core: TideCore) -> dict:
    return {
        "snapshot": core.snapshot(),
        "plan": core.plan_reply(),
        "series": forecast(core, hours=24.0, step_h=0.5),
    }


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
                self._send(200, json.dumps(payload(core), ensure_ascii=False))
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
                    core.observe(text=data.get("text", ""), speaker=data.get("speaker", "other"))
                elif path == "/api/event":
                    core.event(data.get("name", ""))
                elif path == "/api/advance":
                    core.advance(float(data.get("hours", 1)))
                elif path == "/api/reset":
                    core.reset()
                elif path == "/api/settings":
                    result = core.update_settings(data)
                elif path == "/api/say":
                    result = core.send_proactive()
                elif path == "/api/update":
                    result = core.updater.apply()
                self._send(200, json.dumps(result if result is not None else payload(core),
                                           ensure_ascii=False))
            except (KeyError, ValueError) as exc:
                self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False))
            except Exception as exc:  # 面板不该把异常吞掉
                self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False))

    return Handler


def brain_loop(core: TideCore, every: float = 60.0) -> None:
    """她的心跳：定期看一眼"现在该不该开口"。发不出去也不影响面板。"""
    import time as _t
    while True:
        _t.sleep(every)
        try:
            core.send_proactive()   # 该开口就发
            core.save()             # 顺手把这段时间的状态落盘，别等出事才想起存档
        except Exception:
            pass


def serve(core: TideCore, host: str = "127.0.0.1", port: int = 7880) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(core))
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
    if "--brain" in argv or core.qq.enabled:
        # 她自己的心跳：每分钟看一眼该不该开口（睡着时会被 is_quiet 拦住）
        threading.Thread(target=brain_loop, args=(core,), daemon=True).start()
    core.updater.check_async()          # 后台查一次有没有新版本，不挡启动
    serve(core, port=int(arg("--port", 7880)))


# 页面本体在 web_ui.py（HTML/CSS/JS 都在那边）
from .web_ui import HTML  # noqa: E402


if __name__ == "__main__":
    main()
