"""隐私门禁：提交前 / 推送前 / CI 里都跑一遍，把不该见光的东西挡在仓库外面。

用法：
    python tools/privacy_gate.py            # 查工作区所有被 git 跟踪的文件
    python tools/privacy_gate.py --staged   # 只查这次要提交的（pre-commit 用）
    python tools/privacy_gate.py --head     # 查 HEAD 这棵树（pre-push / CI 用）

命中任何一条就退出码 1，并且把"文件:行号 命中了什么规则"列清楚。
确实要放行的行，在行尾加注释 `privacy-allow`（会写进报告，但不拦）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 通用规则：只写"长得像隐私"的形状，不写任何具体的人名 / 昵称 / 账号。
# 规则名 -> (正则, 说明)。顺序就是报告里的顺序。
RULES = [
    ("token", re.compile(r"P_[A-Za-z0-9]{20,}"), "OneBot / SnowLuma 的 access token"),
    ("qq", re.compile(r"(?<![\d.])\d{8,}(?![\d.])"), "8 位以上连续数字（QQ 号、时间戳之类的隐私）"),
    ("home", re.compile(r"[A-Za-z]:\\+(?:AI|Users\\+[A-Za-z]+)\\", re.I), "本机绝对路径"),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"), "邮箱"),
    ("secret", re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}"),
     "别的平台的密钥"),
    ("pem", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"), "私钥"),
]

# 具体的人名、昵称、账号，放在本地文件里，不进仓库：
#   config/privacy.local.txt   一行一条正则，# 开头是注释
# 这个文件已 gitignore，所以"要保护什么"本身不会被公开。
LOCAL_WORDS = ROOT / "config" / "privacy.local.txt"


def load_local_rules() -> list[tuple[str, re.Pattern, str]]:
    if not LOCAL_WORDS.exists():
        return []
    rules = []
    for line in LOCAL_WORDS.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        try:
            rules.append(("私人词", re.compile(word), "本地 privacy.local.txt 里的词"))
        except re.error as e:
            print(f"[privacy] 本地规则写错了，跳过：{word}（{e}）")
    return rules

# 这些文件天然包含规则本身（比如本脚本），整份跳过
SKIP_FILES = {"tools/privacy_gate.py", "config/privacy.local.txt"}
RULES = RULES + load_local_rules()
SKIP_DIRS = (".git/", "data/", ".test_tmp/", "__pycache__/", ".edge-")
ALLOW_MARK = "privacy-allow"


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return out.stdout.decode("utf-8", "replace")


def tracked_files() -> list[str]:
    return [p for p in git("ls-files").splitlines() if p]


def staged_files() -> list[str]:
    return [p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
            if p]


def read_worktree(path: str) -> str | None:
    f = ROOT / path
    if not f.is_file():
        return None
    data = f.read_bytes()
    if b"\0" in data[:4096]:
        return None                      # 二进制，跳过
    return data.decode("utf-8", "replace")


def read_staged(path: str) -> str | None:
    out = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        return None
    data = out.stdout
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", "replace")


def read_head(path: str) -> str | None:
    out = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        return None
    data = out.stdout
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", "replace")


def scan(files: list[str], reader) -> list[tuple[str, int, str, str, str]]:
    hits = []
    for path in files:
        norm = path.replace("\\", "/")
        if norm in SKIP_FILES or any(d in norm for d in SKIP_DIRS):
            continue
        text = reader(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            allowed = ALLOW_MARK in line
            for name, rx, why in RULES:
                m = rx.search(line)
                if not m:
                    continue
                hits.append((norm, lineno, name, m.group(0), why if not allowed else "已放行"))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="只查暂存区（pre-commit）")
    g.add_argument("--head", action="store_true", help="查 HEAD 树（pre-push / CI）")
    args = ap.parse_args(argv)

    if args.staged:
        files, reader, where = staged_files(), read_staged, "暂存区"
    elif args.head:
        files, reader, where = tracked_files(), read_head, "HEAD"
    else:
        files, reader, where = tracked_files(), read_worktree, "工作区"

    hits = [h for h in scan(files, reader) if h[4] != "已放行"]
    allowed = [h for h in scan(files, reader) if h[4] == "已放行"]

    if not hits:
        print(f"[privacy] {where} {len(files)} 个文件，没有发现隐私字符。")
        if allowed:
            print(f"[privacy] 另有 {len(allowed)} 处写了 privacy-allow，按约定放行。")
        return 0

    print(f"[privacy] 拦下了 {len(hits)} 处：\n", file=sys.stderr)
    for path, lineno, name, text, why in hits:
        shown = text if len(text) <= 40 else text[:37] + "..."
        print(f"  {path}:{lineno}  [{name}] {shown}\n      —— {why}", file=sys.stderr)
    print("\n怎么处理：", file=sys.stderr)
    print("  1) 把值挪到 config/local.yaml（已在 .gitignore 里），仓库里只留占位符；", file=sys.stderr)
    print("  2) 确实要保留的，在该行行尾加注释 privacy-allow；", file=sys.stderr)
    print("  3) 已经提交过的，改完再 git add，不要用 --no-verify 绕过。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())