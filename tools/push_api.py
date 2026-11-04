"""当 github.com:443 连不上时，用 api.github.com（通常还通）把提交推上去。

把远端还没的每个提交按原样重建（同样的树、父提交、作者和提交时间），
所以推完收到的 sha 和本地完全一致，不会让历史分叉。

    python tools/push_api.py --repo ya-shua/tide --token-file <path> [--tag v0.1.1]
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args: str) -> bytes:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "replace").strip())
    return out.stdout


def git_text(*args: str) -> str:
    return git(*args).decode("utf-8", "replace").strip()


def api(url: str, token: str, payload=None, method="GET") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"token {token}", "User-Agent": "tide-push-api",
        "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def meta_of(sha: str) -> dict:
    parts = git_text("log", "-1", "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI",
                     sha).split("\x00")
    return {"author": {"name": parts[0], "email": parts[1], "date": parts[2]},
            "committer": {"name": parts[3], "email": parts[4], "date": parts[5]}}


def push_one(base: str, token: str, sha: str, base_tree: str) -> str:
    """把一个提交原样搬到远端，返回远端新提交 sha（应当等于本地 sha）。"""
    parent = git_text("rev-parse", f"{sha}^")
    entries = []
    for line in git_text("diff", "--name-status", parent, sha).splitlines():
        status, _, path = line.partition("\t")
        if status == "D":
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        mode = git_text("ls-tree", sha, "--", path).split()[0]
        blob = git("show", f"{sha}:{path}")
        created = api(f"{base}/git/blobs", token,
                      {"content": base64.b64encode(blob).decode(), "encoding": "base64"},
                      method="POST")
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": created["sha"]})

    tree = api(f"{base}/git/trees", token, {"base_tree": base_tree, "tree": entries},
               method="POST")
    tree_local = git_text("rev-parse", f"{sha}^{{tree}}")
    if tree["sha"] != tree_local:
        raise RuntimeError(f"树对不上：远端 {tree['sha']}，本地 {tree_local}")

    m = meta_of(sha)
    commit = api(f"{base}/git/commits", token, {
        "message": git_text("log", "-1", "--format=%B", sha),
        "tree": tree["sha"], "parents": [git_text("rev-parse", f"{sha}^")],
        "author": m["author"], "committer": m["committer"],
    }, method="POST")
    if commit["sha"] != sha:
        raise RuntimeError(f"提交 sha 对不上：远端 {commit['sha'][:12]}，本地 {sha[:12]}")
    return commit["sha"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="ya-shua/tide")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--tag", action="append", default=[])
    args = ap.parse_args(argv)

    token = Path(args.token_file).read_text(encoding="utf-8").strip()
    base = f"https://api.github.com/repos/{args.repo}"

    remote = api(f"{base}/commits/{args.branch}", token)
    remote_sha = remote["sha"]
    head = git_text("rev-parse", "HEAD")

    todo = git_text("rev-list", "--reverse", f"{remote_sha}..{head}").splitlines()
    if not todo:
        print("远端已经是最新的。")
        return 0

    base_tree = remote["commit"]["tree"]["sha"]
    for sha in todo:
        print(f"推 {sha[:12]} {git_text('log', '-1', '--format=%s', sha)}")
        base_tree = push_one(base, token, sha, base_tree)

    api(f"{base}/git/refs/heads/{args.branch}", token,
        {"sha": head, "force": False}, method="PATCH")
    print(f"已更新 {args.branch} -> {head[:12]}")

    for tag in args.tag:
        msg = git_text("tag", "-l", "--format=%(contents)", tag) or tag
        obj = api(f"{base}/git/tags", token,
                  {"tag": tag, "message": msg or tag, "object": head, "type": "commit"},
                  method="POST")
        api(f"{base}/git/refs", token, {"ref": f"refs/tags/{tag}", "sha": obj["sha"]},
            method="POST")
        print(f"已建远端 tag {tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())