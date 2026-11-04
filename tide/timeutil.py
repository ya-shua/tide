"""时间小工具：本地时钟、HH:MM 解析、跨午夜时段判断。"""
from __future__ import annotations

import time


def epoch() -> float:
    return time.time()


def parse_hhmm(s: str):
    """"00:30" -> (0, 30)"""
    h, _, m = str(s).strip().partition(":")
    return int(h), int(m or 0)


def in_window(ts: float, start: str, end: str) -> bool:
    """ts 是否落在 [start, end) 本地时段内，支持跨午夜。"""
    lt = time.localtime(ts)
    cur = lt.tm_hour * 60 + lt.tm_min
    sh, sm = parse_hhmm(start)
    eh, em = parse_hhmm(end)
    a, b = sh * 60 + sm, eh * 60 + em
    if a <= b:
        return a <= cur < b
    return cur >= a or cur < b


def hhmm(ts: float) -> str:
    lt = time.localtime(ts)
    return f"{lt.tm_hour:02d}:{lt.tm_min:02d}"


def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts))