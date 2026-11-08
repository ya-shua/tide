"""好感 × 心情 → 说话的分寸。

好感是底盘，心情是当天的脾气：同样的火，对亲近的人会压着，对不熟的人直接炸。
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tide.core import TideCore, _tone_line  # noqa: E402

CFG_DIR = Path(__file__).resolve().parents[1] / "config"
STATE = Path(__file__).resolve().parents[1] / "data" / "state.json"


def test_angry_low_affinity_explodes():
    line = _tone_line(10, "anger", 0.8)
    assert "冲" in line and "别哄" in line


def test_angry_high_affinity_holds_back():
    line = _tone_line(90, "anger", 0.8)
    assert "压着火" in line and "别撂狠话" in line


def test_joy_high_is_sticky_low_is_polite():
    assert "黏" in _tone_line(90, "joy", 0.7)
    assert "客气" in _tone_line(10, "joy", 0.7)


def test_calm_is_neutral():
    assert "正常说话" in _tone_line(50, "calm", 0.0)


def test_tone_line_reaches_the_prompt():
    """plan_reply 的提示词里必须真有这一行，不能只是个没接上的函数。"""
    tmp = Path(tempfile.mkdtemp())
    state = tmp / "state.json"
    if STATE.exists():
        shutil.copy(STATE, state)
    core = TideCore.from_config(CFG_DIR, state_path=str(state))
    prompt = core.plan_reply("qq:777888")["prompt"]  # privacy-allow
    assert "说话的分寸" in prompt
    assert re.search(r"亲和 \d+", prompt)
