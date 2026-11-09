"""版本号：唯一真源。发版脚本从这里读，更新检查也拿它比。"""

__version__ = "1.3.0"

# 更新检查默认指向的仓库（config/rules.yaml 的 update.repo 会覆盖它）
DEFAULT_REPO = "ya-shua/tide"

DATE = "2026-11-09"


def as_tuple(v: str) -> tuple:
    """把 "v0.2.1" / "0.2.1-beta" 变成能比大小的元组。"""
    core = (v or "").lstrip("vV").split("-")[0].split("+")[0]
    parts = []
    for piece in core.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])