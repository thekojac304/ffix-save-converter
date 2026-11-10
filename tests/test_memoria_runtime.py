"""Regression tests on genuine files from the 2026-11-06 Memoria runtime test (Memoria 2025-07-13, your own Disc 2
playthrough, PS1 card block 13 -> PC -> Memoria native save -> PS1 -> PS1 native save). Expected values are the ones
read from the game screens during that test (reports/RUNTIME_RESULTS.md). The files are personal and git-ignored;
these tests skip when they are absent.
"""
import base64
import os
import shutil

import pytest

from conftest import ROOT
from ffix_conv import memoria, model, pc_container, ps1_card, ps1_save, ps1_writer, service

RT = os.path.join(ROOT, "fixtures", "memoria", "runtime_20261106")
USER_CARD = os.path.join(ROOT, "fixtures", "ps1", "originals", "user_retroarch", "user_Final_Fantasy_IX.srm")


def rt(*parts):
    p = os.path.join(RT, *parts)
    if not os.path.exists(p):
        pytest.skip("Memoria runtime fixtures not present")
    return p


def ps1_block(path, block):
    _, es = ps1_card.parse_file(open(path, "rb").read())
    e = [x for x in es if x.block_index == block][0]
    return e, model.from_ps1(ps1_save.PS1Save(e.data, e.product_code, e.filename))


def convert(tmp_path, src, source, name="out.mcr", **kw):
    return service.convert_file(service.ConvertOptions(input=str(src), source=source, out=str(tmp_path / name), **kw))


@pytest.mark.parametrize("name", ["native_save/SavedData_ww_Memoria_0_1.dat",
                                  "autosave/SavedData_ww_Memoria_Autosave.dat",
                                  "moguri_style/SavedData_ww_Memoria_0_5.dat"])
def test_genuine_sidecars_round_trip_byte_for_byte(name):
    raw = open(rt(name), "rb").read()
    root, end = memoria.parse(raw)
    assert end == len(raw) and memoria.dumps(root) == raw


def test_genuine_native_save_converts_with_the_party_memoria_shows(tmp_path):
    """In-game (Memoria and DuckStation): Dagger 222/222 12/60, Steiner 177/406, Marcus 146/277, 40,491 gil."""
    src = rt("native_save", "SavedData_ww.dat")
    r = convert(tmp_path, src, "1/2")
    m = r["model"]
    assert m["party"]["slot"][:3] == [2, 3, 6] and m["party"]["gil"] == 40491
    hp = {m["players"][i]["name"]: (m["players"][i]["cur"]["hp"], m["players"][i]["max"]["hp"]) for i in (2, 3, 6)}
    assert hp == {"Dagger": (222, 222), "Steiner": (177, 406), "Marcus": (146, 277)}
    assert not r["report"]["memoria"]["blocking"]
    assert service.verify_files(str(src), r["out"], "1/2")["counts"]["unexpected"] == 0


def test_memorias_own_container_loses_marcus_and_the_sidecar_restores_him(tmp_path):
    """Memoria flags Quina/Eiko/Amarant on every vanilla-save load, so its container drops Marcus from the party."""
    alone = tmp_path / "alone"
    alone.mkdir()
    shutil.copy(rt("native_save", "SavedData_ww.dat"), alone / "SavedData_ww.dat")
    r = convert(tmp_path, alone / "SavedData_ww.dat", "1/2")
    assert r["model"]["party"]["slot"] == [2, 3, 255, 255] and r["model"]["players"][6]["name"] == "Eiko"
    full = convert(tmp_path, rt("native_save", "SavedData_ww.dat"), "1/2", name="with_sidecar.mcr")
    m, applied = full["model"], full["report"]["memoria"]["taken_from_sidecar"]
    assert m["party"]["slot"] == [2, 3, 6, 255] and m["players"][6]["name"] == "Marcus"
    assert m["players"][7]["name"] == "Blank" and any("record 6 holds Marcus" in x for x in applied)


def test_genuine_autosave_pair(tmp_path):
    d = rt("autosave")
    c = pc_container.Container(open(os.path.join(d, "SavedData_ww.dat"), "rb").read())
    tree = c.slot_tree(pc_container.AUTOSAVE, 0)
    root, _ = memoria.parse(open(os.path.join(d, "SavedData_ww_Memoria_Autosave.dat"), "rb").read())
    m, rec = memoria.reconcile(tree, {"status": "valid", "path": "auto", "root": root,
                                      "time": root["95000_Setting"]["00001_time"]})
    assert not rec.blocking and m["party"]["slot"] == [2, 3, 6, 255]


# observed in Memoria: gil, Dagger HP, Marcus HP (None = the slot does not load: "Data corrupted.")
OBSERVED = {"1/1": ("valid", 1234567, 111, 146), "1/3": ("stale", 40169, 222, 178),
            "1/4": ("corrupt", None, None, None), "1/5": ("untimed", 7777, 222, 146)}


@pytest.mark.parametrize("slot", sorted(OBSERVED))
def test_sidecar_cases_match_what_memoria_did(tmp_path, slot):
    status, gil, dagger, marcus = OBSERVED[slot]
    src = rt("sidecar_cases", "SavedData_ww.dat")
    head, rows = service.list_saves(src)
    assert {r["id"]: r for r in rows}[slot]["memoria"] == status
    if gil is None:
        with pytest.raises(service.UserError, match="corrupt"):
            convert(tmp_path, src, slot)
        return
    m = convert(tmp_path, src, slot)["model"]
    assert (m["party"]["gil"], m["players"][2]["cur"]["hp"], m["players"][6]["cur"]["hp"]) == (gil, dagger, marcus)


def test_moguri_style_save_is_a_plain_memoria_save(tmp_path):
    """Saved with Memoria's `MoguriFiles` mod folder active: same sidecar structure and the same converted state."""
    src = rt("moguri_style", "SavedData_ww.dat")
    a, _ = memoria.parse(open(rt("moguri_style", "SavedData_ww_Memoria_0_5.dat"), "rb").read())
    b, _ = memoria.parse(open(rt("moguri_style", "SavedData_ww_Memoria_0_1.dat"), "rb").read())

    def shape(x):
        if isinstance(x, dict):
            return {k: shape(v) for k, v in x.items()}
        return [shape(x[0])] if isinstance(x, list) and x else type(x).__name__
    assert shape(a) == shape(b)
    m6 = convert(tmp_path, src, "1/6")["model"]
    m2 = convert(tmp_path, src, "1/2", name="b.mcr")["model"]
    for i in range(9):
        p6 = {k: v for k, v in m6["players"][i].items() if k != "web_bone"}
        p2 = {k: v for k, v in m2["players"][i].items() if k != "web_bone"}
        assert p6 == p2
    assert m6["party"] == m2["party"] and m6["items"] == m2["items"] and m6["minigame"] == m2["minigame"]


def test_vanilla_state_survives_ps1_memoria_ps1(tmp_path):
    """Original PS1 block 13 vs. the PS1 save made from the genuine Memoria save: only the Memoria session's play
    (one battle: gil, EXP, AP, HP, two items, battle bookkeeping, play time) and documented normalizations differ."""
    if not os.path.exists(USER_CARD):
        pytest.skip("personal PS1 card not present")
    _, a = ps1_block(USER_CARD, 13)
    r = convert(tmp_path, rt("native_save", "SavedData_ww.dat"), "1/2")
    _, b = ps1_block(r["out"], 1)
    assert a["event"]["scenario_counter"] == b["event"]["scenario_counter"] == 4390
    assert a["rare_items"] == b["rare_items"] and a["minigame"] == b["minigame"]
    assert a["party"]["slot"] == b["party"]["slot"] and b["party"]["gil"] - a["party"]["gil"] == 322
    ga, gb = model.gevent_bytes(a), model.gevent_bytes(b)
    assert [i for i in range(2048) if ga[i] != gb[i]] == [64, 65, 66, 67, 68, 69, 70, 72]
    allowed = {"exp", "cur", "pa", "web_bone", "bonus_cap", "info"}
    for i in range(9):
        pa, pb = a["players"][i], b["players"][i]
        assert {k for k in pa if pa[k] != pb[k]} <= allowed, pa["name"]
        assert pa["level"] == pb["level"] and pa["equip"] == pb["equip"] and pa["sa"] == pb["sa"]


def test_ps1_preview_portraits_follow_the_character(tmp_path):
    """The PS1 game drew Marcus's portrait (id 9) when it saved; the converter now writes the same."""
    game, _ = ps1_block(rt("ps1_after", "duckstation_after_ps1_save.mcd"), 2)
    r = convert(tmp_path, rt("native_save", "SavedData_ww.dat"), "1/2")
    ours, _ = ps1_block(r["out"], 1)
    portraits = lambda d: [d[0x134 + 16 * k + 1] for k in range(4) if d[0x134 + 16 * k] == 1]
    assert portraits(ours.data) == portraits(game.data) == [ps1_writer.PORTRAIT_BY_SERIAL[4], 4, 9]
