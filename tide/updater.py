"""更新：查 GitHub Release、下载、落地，然后重启面板。

只依赖标准库。查不到（没网、仓库没发版）时状态写进 self.state，面板照常能用。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .version import DEFAULT_REPO, as_tuple, __version__

CHECK_INTERVAL = 6 * 3600      # 查过之后 6 小时内不重复查
USER_AGENT = "tide-updater"


class Updater:
    def __init__(self, cfg: dict, root: Path, panel_port: int = 7880):
        cfg = cfg or {}
        self.repo = (cfg.get("repo") or DEFAULT_REPO).strip()
        self.api = (cfg.get("api") or "https://api.github.com").rstrip("/")
        self.root = Path(root)
        self.port = panel_port
        self.work = self.root / "data" / "_update"
        self.state = {
            "current": __version__,
            "latest": "",
            "has_update": False,
            "notes": "",
            "checked_at": 0,
            "error": "",
            "applying": False,
        }
        self._lock = threading.Lock()

    # ---------- 查 ----------
    def _get_json(self, url: str, timeout: float = 15.0) -> dict:
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def check(self, force: bool = False) -> dict:
        if not self.repo or "/" not in self.repo:
            self.state.update(error="", latest="", has_update=False)
            return dict(self.state)
        with self._lock:
            fresh = time.time() - float(self.state.get("checked_at") or 0) < CHECK_INTERVAL
            if fresh and not force:
                return dict(self.state)
            try:
                data = self._get_json(f"{self.api}/repos/{self.repo}/releases/latest")
                tag = str(data.get("tag_name") or "")
                latest = tag
                self.state.update({
                    "latest": latest,
                    "tag": tag,
                    "notes": (data.get("body") or "").strip()[:800],
                    "url": data.get("zipball_url") or "",
                    "page": data.get("html_url") or "",
                    "published_at": data.get("published_at") or "",
                    "has_update": as_tuple(latest) > as_tuple(__version__),
                    "error": "",
                    "checked_at": time.time(),
                })
            except urllib.error.HTTPError as e:
                # 404 = 还没有任何 Release，不算错误
                msg = "还没有发布过版本" if e.code == 404 else f"GitHub 返回 {e.code}"
                self.state.update({"error": msg if e.code != 404 else "",
                                   "latest": "", "has_update": False,
                                   "checked_at": time.time()})
            except Exception as e:                      # 断网、超时
                self.state.update({"error": f"检查更新失败：{type(e).__name__}",
                                   "checked_at": time.time()})
            return dict(self.state)

    def check_async(self) -> None:
        threading.Thread(target=self.check, daemon=True).start()

    # ---------- 下载并铺开 ----------
    def download(self, timeout: float = 90.0) -> Path:
        st = self.check()
        url = st.get("url") or ""
        if not st.get("has_update") or not url:
            raise RuntimeError("没有可用的新版本")
        self.work.mkdir(parents=True, exist_ok=True)
        zip_path = self.work / f"tide-{st['tag']}.zip"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            zip_path.write_bytes(r.read())
        unpack = self.work / "new"
        if unpack.exists():
            _rmtree(unpack)
        unpack.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(unpack)
        tops = [p for p in unpack.iterdir() if p.is_dir()]
        if len(tops) != 1:
            raise RuntimeError("下载包结构不对")
        return tops[0]

    # ---------- 覆盖 + 重启 ----------
    def apply(self) -> dict:
        """下载新版本，写一个 updater 批处理，然后让面板退出由它接手。"""
        if self.state.get("applying"):
            return dict(self.state)
        self.state["applying"] = True
        try:
            src = self.download()
            bat = self._write_bat(src)
            self.state["error"] = ""
            self.state["bat"] = str(bat)
            threading.Thread(target=self._run_bat, args=(bat,), daemon=True).start()
            return dict(self.state)
        except Exception as e:
            self.state.update({"applying": False, "error": f"更新失败：{e}"})
            return dict(self.state)

    def _write_bat(self, src: Path) -> Path:
        bat = self.work / "apply_update.bat"
        skip_dirs = "data .git .test_tmp __pycache__"
        skip_files = "local.yaml local.example.yaml"
        python = sys.executable
        lines = [
            "@echo off",
            "chcp 65001 >nul",
            "timeout /t 2 /nobreak >nul",
            f'robocopy "{src}" "{self.root}" /E /NFL /NDL /NJH /NJS '
            f"/XD {skip_dirs} /XF {skip_files} >nul",
            f'start "" "{python}" -m tide.panel --port {self.port}',
            "exit",
        ]
        bat.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        return bat

    def _run_bat(self, bat: Path) -> None:
        try:
            subprocess.Popen(["cmd", "/c", str(bat)], cwd=str(self.root),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        finally:
            time.sleep(0.4)
            os._exit(0)          # 让位给批处理：文件被占用时它才换得动


def _rmtree(path: Path) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)