"""Phase 2 audit: mappings checked against the vanilla game's own rules and real PC saves.

Tests needing research/vanilla_extracts/abilities.json (facts extracted locally from the
installed game, not redistributed) skip when it is absent.
"""
import os
import sys

import pytest
from conftest import ROOT, fa, load_pc, load_ps1, pcf

from ffix_conv import convert, model, pc_schema

sys.path.insert(0, os.path.join(ROOT, "tools"))
import audit_abilities  # noqa: E402


@pytest.fixture(scope="module")
def tables():
    if not os.path.exists(audit_abilities.TABLES):
        pytest.skip("vanilla ability tables not extracted (see tools/audit_abilities.py)")
    return audit_abilities.load_tables()


def test_support_abilities_and_ap_follow_vanilla_rules_on_every_record(tables):
    sa_capa, patab = tables
    n = 0
    for plat, name, m in audit_abilities.corpus():
        for i, p in enumerate(m["players"]):
            if p["level"] <= 1 and not any(p["pa"]) and not any(p["sa"]):
                continue
            r = audit_abilities.check_player(p, sa_capa, patab)
            assert r["A_budget"], (plat, name, i, "magic-stone budget; vanilla would unequip all SAs")
            assert r["B_learnable"], (plat, name, i, "SA not in this character's ability table")
            assert r["C_ap_bounds"], (plat, name, i, "AP exceeds the slot requirement")
            n += 1
    assert n > 500


def test_stat_growth_bonus_reproduces_vanilla_formula():
    _, bad = audit_abilities.audit_bonus()
    assert bad == {}, f"inconsistent implied base stats: {bad}"


def test_menu_type_is_five_bits_regression():
    # Regression: early Cinna/Marcus/Blank use presets 17/18/19; a 4-bit read gave 1/2/3
    # (Vivi/Garnet/Steiner presets). Pair: FA 02 vs the user's PC save at the same scenario.
    ps1 = model.from_ps1(load_ps1(fa(2)))
    pc = model.from_pc(load_pc(pcf("user_FF9_CloudSaveFile_ww.sav")).slot_tree(0, 1))
    assert ps1["event"]["scenario_counter"] == pc["event"]["scenario_counter"] == 1190
    assert [p["info"]["menu_type"] for p in ps1["players"][5:8]] == [17, 18, 19]
    assert [p["info"] for p in ps1["players"]] == [p["info"] for p in pc["players"]]


@pytest.mark.parametrize("n,slot", [(1, (0, 0)), (2, (0, 1)), (3, (0, 2)), (6, (0, 12)), (7, (0, 13)),
                                    (8, (1, 0)), (9, (1, 2)), (10, (1, 3)), (11, (1, 5))])
def test_exact_story_pairs_with_user_save(n, slot):
    ps1 = model.from_ps1(load_ps1(fa(n)))
    pc = model.from_pc(load_pc(pcf("user_FF9_CloudSaveFile_ww.sav")).slot_tree(*slot))
    assert ps1["event"]["scenario_counter"] == pc["event"]["scenario_counter"]
    assert ps1["state"]["fldMapNo"] == pc["state"]["fldMapNo"]
    same = sum(a == b for a, b in zip(model.gevent_bytes(ps1), model.gevent_bytes(pc)))
    assert same >= 1900
    # key items: 2 bits per item (obtained, used) in both; obtained bits the PC player has are a
    # subset of the PS1 player's at the same story point
    obtained = lambda r: {i * 4 + k for i, x in enumerate(r) for k in range(4) if x >> (2 * k) & 1}
    assert obtained(pc["rare_items"]) <= obtained(ps1["rare_items"])
    for a, b in zip(ps1["players"][:5], pc["players"][:5]):     # guests (slots 5-8) depend on recruit timing
        assert a["info"]["slot_no"] == b["info"]["slot_no"] and a["info"]["menu_type"] == b["info"]["menu_type"]


def test_defaults_match_what_the_game_writes():
    tree, _ = convert.to_pc_tree(model.from_ps1(load_ps1(fa(1))))
    real = load_pc(pcf("user_FF9_CloudSaveFile_ww.sav")).slot_tree(0, 0)
    d, r = tree["Data"], real["Data"]
    # key bindings equal the user's own save (vanilla defaults); other cfg values are personal options
    for k in ("control_data_keyboard", "control_data_joystick", "control", "control_data"):
        assert d["50000_Setting"]["cfg"][k] == r["50000_Setting"]["cfg"][k]
    for k in convert.EMPTY_MINUS_ONE:
        assert d["80000_Achievement"][k] == r["80000_Achievement"][k]
    for k in ("91000_State", "92000_Event", "93000_MiniGame", "96000_Sound", "97000_World", "99000_Other"):
        assert d[k] == r[k]
    assert d["50000_Setting"]["time"] == r["50000_Setting"]["time"] == -1.0
    assert d["60000_Sound"] == r["60000_Sound"]


def test_template_never_leaks_game_state():
    m = model.from_ps1(load_ps1(fa(41)))
    plain, _ = convert.to_pc_tree(m)
    donor = load_pc(pcf("steam_cd3thread_SavedData_ww.dat")).slot_tree(1, 3)     # level-99 endgame save
    templ, _ = convert.to_pc_tree(m, donor)
    diff = {p[1] for p, t, o in pc_schema.LAYOUT if pc_schema.get(plain, p) != pc_schema.get(templ, p)}
    assert diff <= {"50000_Setting", "70000_World"}


def test_vanilla_load_rules_accept_converted_players(tables):
    """Simulate the vanilla load-time validators on converted output (PLAYER.ValidateSupportAbility,
    ValidateMaxStone precondition, party slot range) for every PS1 fixture."""
    sa_capa, patab = tables
    from conftest import ps1_files
    for f in ps1_files():
        tree, _ = convert.to_pc_tree(model.from_ps1(load_ps1(f)))
        back = model.from_pc(tree)
        for p in back["players"]:
            used = sum(sa_capa[i] for i in range(64) if (p["sa"][i >> 5] >> (i & 31)) & 1)
            assert p["cur"]["capa"] == p["max"]["capa"] - used
        for s in tree["Data"]["40000_Common"]["slot"]:
            assert s == 255 or 0 <= s < 9
