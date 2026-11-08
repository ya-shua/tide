"""谁算「同一个人」：称呼卡上的人合成一个，别人按 QQ 号各算各的。"""
from __future__ import annotations

import importlib.util
import types
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mood_main", _HERE / "plugins" / "mood" / "main.py")
mood = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mood)

A, B, C = "1234567890", "9876543210", "777888"  # privacy-allow


def cfg_of(cards):
    return types.SimpleNamespace(admins=cards, owner_qq=A, owner_ids=[A])


CARDS = [types.SimpleNamespace(name="管理员A", ids=[A, B])]


def test_two_accounts_are_one_person():
    ctx = types.SimpleNamespace(cfg=cfg_of(CARDS))
    assert mood.person_for(ctx, f"private:{A}", A) == ""
    assert mood.person_for(ctx, f"private:{B}", B) == ""
    # 群里用哪个号说话，也还是同一个人
    assert mood.person_for(ctx, "group:123456", B) == ""  # privacy-allow


def test_other_people_are_their_own_person():
    ctx = types.SimpleNamespace(cfg=cfg_of(CARDS))
    assert mood.person_for(ctx, f"private:{C}", C) == f"qq:{C}"
    assert mood.person_for(ctx, "group:123456", C) == f"qq:{C}"  # privacy-allow


def test_same_group_different_people_are_not_one():
    ctx = types.SimpleNamespace(cfg=cfg_of(CARDS))
    one = mood.person_for(ctx, "group:123456", C)  # privacy-allow
    two = mood.person_for(ctx, "group:123456", "120000")  # privacy-allow
    assert one != two


def test_no_card_configured_still_keys_by_qq():
    ctx = types.SimpleNamespace(cfg=types.SimpleNamespace(admins=[], owner_qq=A, owner_ids=[A]))
    assert mood.person_for(ctx, f"private:{C}", C) == f"qq:{C}"
