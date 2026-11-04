"""发版：改版本号 → 提交 → 打 tag → 推 → 建 GitHub Release。

用法：
    python tools/release.py 0.2.0 "这一版修了什么"        # 指定版本和说明
    python tools/release.py --next patch "修了个 bug"      # 自动 +1

token 从环境变量 GITHUB_TOKEN 读；没有就读 C:\\Users\\<你>\\Desktop\\token.txt？
不——不猜路径，第二个参数可以给文件：python tools/release.py ... --token-file <path>

这个脚本只负责本地 git 和 GitHub API，不打印 token。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "tide" / "version.py"


def git(*args: str) -> str:
    exe = "git"
    for cand in (exe, r"D:\Git\cmd\git.exe"):
        try:
            out = subprocess.run([cand, *args], cwd=ROOT, capture_output=True)
            if out.returncode == 0:
                return out.stdout.decode("utf-8", "replace")
        except FileNotFoundError:
            continue
    raise RuntimeError(f"git 执行失败: {' '.join(args)}")


def read_version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', VERSION_FILE.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("version.py 里找不到 __version__")
    return m.group(1)


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split(".")[:3])
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_version(new: str) -> None:
    s = VERSION_FILE.read_text(encoding="utf-8")
    s = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{new}"', s, count=1)
    VERSION_FILE.write_text(s, encoding="utf-8")


def token_from(args) -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok and args.token_file:
        tok = Path(args.token_file).read_text(encoding="utf-8").strip()
    if not tok:
        raise RuntimeError("没有 token：设 GITHUB_TOKEN，或者 --token-file 指一个文件")
    return tok


def api(url: str, token: str, payload: dict | None = None, method="GET") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"token {token}",
        "User-Agent": "tide-release",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?", help="新版本号，比如 0.2.0")
    ap.add_argument("notes", nargs="?", default="", help="这一版干了什么（一句话也行）")
    ap.add_argument("--next", choices=["patch", "minor", "major"],
                    help="不给版本号就自动 +1")
    ap.add_argument("--repo", default="ya-shua/tide")
    ap.add_argument("--token-file", default=None)
    ap.add_argument("--no-push", action="store_true", help="只提交和打 tag，不推")
    args = ap.parse_args(argv)

    cur = read_version()
    new = args.version or (bump(cur, args.next) if args.next else None)
    if not new or not re.fullmatch(r"\d+\.\d+\.\d+", new):
        print("版本号要写成 x.y.z，比如 0.2.0", file=sys.stderr)
        return 2

    token = token_from(args)
    tag = f"v{new}"
    print(f"{cur} -> {new}")

    write_version(new)
    git("add", "-A")
    msg = f"chore(release): {tag}" + (f" {args.notes}" if args.notes else "")
    git("commit", "-m", msg)
    git("tag", "-a", tag, "-m", msg)

    if not args.no_push:
        # token 只在内存里拼进 URL，不落进 .git/config
        push_url = f"https://x-access-token:{token}@github.com/{args.repo}.git"
        print(git("push", push_url, "HEAD:main"))
        print(git("push", push_url, tag))

        body = args.notes or f"## {tag}\n\n见提交记录。"
        rel = api(f"https://api.github.com/repos/{args.repo}/releases", token, {
            "tag_name": tag, "name": tag, "body": body, "draft": False,
            "prerelease": False,
        }, method="POST")
        print("Release:", rel.get("html_url"))

    print(f"完成：{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())