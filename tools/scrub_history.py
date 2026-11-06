"""把历史提交里的私人词清掉（只删包含这些词的那几行）。

私人词从本地文件读：config/privacy.local.txt（一行一条，已 gitignore），
所以这个脚本本身不含任何具体的人名 / 昵称 / 账号。

用法（仓库根目录）：
    python tools/scrub_history.py            # 只看会改哪些
    python tools/scrub_history.py --apply    # 真改：重建提交，并搬动分支与 tag
"""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDS_FILE = ROOT / "config" / "privacy.local.txt"
TEXT_SUFFIX = (".py", ".md", ".yaml", ".yml", ".txt", ".json")


def git(*args: str, data: bytes | None = None) -> bytes:
    r = subprocess.run(["git", *args], capture_output=True, input=data, cwd=ROOT)
    if r.returncode:
        raise SystemExit(r.stderr.decode("utf-8", "replace"))
    return r.stdout


def words() -> list[str]:
    if not WORDS_FILE.exists():
        return []
    out = []
    for line in WORDS_FILE.read_text(encoding="utf-8-sig").splitlines():
        w = line.strip()
        if not w or w.startswith("#"):
            continue
        for piece in w.split("|"):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def commit_parts(sha: str):
    raw = git("cat-file", "commit", sha).decode("utf-8", "replace")
    head, _, msg = raw.partition("\n\n")
    tree, parents, env_lines = "", [], {}
    for line in head.splitlines():
        if line.startswith("tree "):
            tree = line[5:].strip()
        elif line.startswith("parent "):
            parents.append(line[7:].strip())
        elif line.startswith(("author ", "committer ")):
            key = "AUTHOR" if line.startswith("author ") else "COMMITTER"
            who = line.split(" ", 1)[1]
            name, _, rest = who.partition(" <")
            email, _, when = rest.partition("> ")
            env_lines[key] = (name, email, when)
    return tree, parents, msg, env_lines


def scrub_blob(blob: str, hit: list[str]) -> str | None:
    content = git("cat-file", "blob", blob).decode("utf-8", "replace")
    lines = content.splitlines(keepends=True)
    keep = [ln for ln in lines if not any(w in ln for w in hit)]
    if len(keep) == len(lines):
        return None
    return git("hash-object", "-w", "--stdin",
               data="".join(keep).encode("utf-8")).decode().strip()


def ls_tree(sha: str):
    out = []
    for line in git("ls-tree", sha).decode("utf-8", "replace").splitlines():
        meta, _, name = line.partition("\t")
        mode, kind, oid = meta.split()
        out.append((mode, kind, oid, name))
    return out


def scrub_tree(tree: str, hit: list[str], prefix: str = "", dry: bool = True):
    entries = ls_tree(tree)
    changed, fresh = False, []
    for mode, kind, oid, name in entries:
        path = f"{prefix}{name}"
        if kind == "blob" and name.endswith(TEXT_SUFFIX):
            content = git("cat-file", "blob", oid).decode("utf-8", "replace")
            if any(w in content for w in hit):
                print(f"    命中 {path}")
                changed = True
                if not dry:
                    new = scrub_blob(oid, hit)
                    if new:
                        oid = new
        elif kind == "tree":
            oid, sub = scrub_tree(oid, hit, path + "/", dry)
            changed = changed or sub
        fresh.append((mode, kind, oid, name))
    if not changed or dry:
        return tree, changed
    payload = "".join(f"{m} {k} {o}\t{n}\n" for m, k, o, n in fresh)
    return git("mktree", data=payload.encode("utf-8")).decode().strip(), True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    hit = words()
    if not hit:
        print(f"没有私人词：{WORDS_FILE} 不存在或是空的")
        return 1
    print(f"要清掉的词：{len(hit)} 条（来自 {WORDS_FILE.name}）")

    shas = git("rev-list", "--reverse", "--topo-order", "--all").decode().split()
    mapping: dict[str, str] = {}

    for sha in shas:
        tree, parents, msg, env_lines = commit_parts(sha)
        subject = msg.strip().splitlines()[0] if msg.strip() else ""
        print(f"  {sha[:8]} {subject[:46]}")

        new_tree, changed = scrub_tree(tree, hit, dry=not args.apply)
        parents_changed = any(mapping.get(p, p) != p for p in parents)
        if not changed and not parents_changed:
            mapping[sha] = sha
            continue
        if not args.apply:
            continue

        env = dict(os.environ)
        for key, (name, email, when) in env_lines.items():
            env[f"GIT_{key}_NAME"] = name
            env[f"GIT_{key}_EMAIL"] = email
            env[f"GIT_{key}_DATE"] = when
        cmd = ["git", "commit-tree", new_tree]
        for p in parents:
            cmd += ["-p", mapping.get(p, p)]
        # 用 -F 写文件：这样提交消息末尾不带换行，和 GitHub 存的一致，sha 才对得上
        import tempfile
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(msg.rstrip("\n").encode("utf-8"))
            msgfile = f.name
        try:
            out = subprocess.run(cmd + ["-F", msgfile],
                                 capture_output=True, env=env, cwd=ROOT)
        finally:
            os.unlink(msgfile)
        if out.returncode:
            raise SystemExit(out.stderr.decode("utf-8", "replace"))
        mapping[sha] = out.stdout.decode().strip()

    if not args.apply:
        print("\n（只看模式。加 --apply 真的重写）")
        return 0

    for ref in git("for-each-ref", "--format=%(refname)", "refs/heads").decode().split():
        old = git("rev-parse", ref).decode().strip()
        if mapping.get(old, old) != old:
            git("update-ref", ref, mapping[old])
            print(f"{ref} -> {mapping[old][:12]}")

    for tag in git("tag").decode().split():
        old = git("rev-parse", f"{tag}^{{}}").decode().strip()
        target = mapping.get(old, old)
        git("tag", "-f", "-a", tag, "-m", tag, target)
        print(f"tag {tag} -> {target[:12]}")

    print("\n改完了。接下来 force push + gc。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())