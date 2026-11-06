"""极简 YAML 子集解析器（零依赖）。

只支持本插件配置里用到的写法：
- 缩进映射
- `- ` 标量列表
- `- key: value` 之后的映射列表（含嵌套映射）
- 标量：字符串（可带引号）、整数、浮点、true/false/null
- 行内列表 `[a, b, c]`，**可以跨行**（配置里就有长的）
- `#` 注释（引号内的 # 不算）

够用即可，不是通用 YAML。若环境里有 PyYAML，core 会优先用它。
"""
from __future__ import annotations


def loads(text: str) -> dict:
    rows = []
    pending = None          # 还没闭合的行内列表，攒到闭合为止
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if pending is not None:
            indent, body = pending[0], pending[1] + " " + line.strip()
            if _balanced(body):
                rows.append([indent, body])
                pending = None
            else:
                pending = [indent, body]
            continue
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if body.count("[") > body.count("]"):
            pending = [indent, body]
            continue
        rows.append([indent, body])
    if pending is not None:                 # 括号没配对，就当普通行收下
        rows.append([pending[0], pending[1]])
    if not rows:
        return {}
    value, _ = _block(rows, 0, rows[0][0])
    return value


def _balanced(s: str) -> bool:
    return s.count("[") <= s.count("]")


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out)


def _block(rows, i, indent):
    if i >= len(rows):
        return {}, i
    if rows[i][1].startswith("- "):
        return _list(rows, i, indent)
    return _map(rows, i, indent)


def _map(rows, i, indent):
    out = {}
    while i < len(rows) and rows[i][0] == indent and not rows[i][1].startswith("- "):
        key, _, rest = rows[i][1].partition(":")
        key, rest = key.strip(), rest.strip()
        i += 1
        if rest:
            out[key] = _scalar(rest)
        elif i < len(rows) and rows[i][0] > indent:
            out[key], i = _block(rows, i, rows[i][0])
        else:
            out[key] = None
    return out, i


def _list(rows, i, indent):
    out = []
    inner = indent + 2
    while i < len(rows) and rows[i][0] == indent and rows[i][1].startswith("- "):
        body = rows[i][1][2:].strip()
        i += 1
        sub_rows = [[inner, body]]
        while i < len(rows) and rows[i][0] > indent:
            sub_rows.append([rows[i][0], rows[i][1]])
            i += 1
        if len(sub_rows) == 1 and ":" not in body:
            out.append(_scalar(body))
        else:
            val, _ = _block(sub_rows, 0, inner)
            out.append(val)
    return out, i


def _split_flow(inner: str) -> list:
    """按逗号切，引号里的逗号不算。"""
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            continue
        if ch == ",":
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return parts


def _scalar(s: str):
    s = s.strip()
    if not s:
        return None
    if s[0] in "\"'" and len(s) > 1 and s[-1] == s[0]:
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [] if not inner else [_scalar(x) for x in _split_flow(inner)]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def load_file(path) -> dict:
    from pathlib import Path

    return loads(Path(path).read_text(encoding="utf-8-sig"))