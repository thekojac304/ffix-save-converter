"""PC -> PS1 writer, memory-card writer, and round trips in both directions."""
import copy
import os
import subprocess
import sys

import pytest
from conftest import ROOT, fa, load_pc, load_ps1, pc_files, pcf, ps1_files

from ffix_conv import convert, model, pc_container, ps1_card, ps1_save, ps1_writer

PLAYER_KEYS = ("name", "category", "level", "exp", "cur", "max", "trance", "web_bone", "elem", "defence", "basis",
               "info", "status", "equip", "bonus", "pa", "sa")


def _pc_slots():
    out = []
    for f in pc_files() + [os.path.join(ROOT, "fixtures/pc/originals/user_cloud/user_FF9_CloudSaveFile_ww.sav")]:
        if os.path.exists(f):
            c = pc_container.Container(open(f, "rb").read())
            out += [(f, sl) for sl in c.occupied()]
    return out


def _via_pc(m):
    tree, _ = convert.to_pc_tree(m)
    c = convert.blank_container()
    convert.insert(c, 0, 0, tree, convert.preview_for(tree, m, 1.0))
    return model.from_pc(pc_container.Container(c.to_bytes()).slot_tree(0, 0))


def _reparse_card(card, idx=1):
    _, es = ps1_card.parse_file(card)
    e = [x for x in es if x.block_index == idx][0]
    return ps1_save.PS1Save(e.data, e.product_code, e.filename)


# ---- PS1 writer ----------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ps1_files() or [None])
def test_ps1_canonical_ps1_is_byte_identical(path):
    if path is None:
        pytest.skip("PS1 fixtures not present")
    s = load_ps1(path)
    b, _ = ps1_writer.build_block(model.from_ps1(s))
    assert b == s.block


def test_blank_card_plus_block_reproduces_emulator_card():
    raw = open(fa(1), "rb").read()
    _, es = ps1_card.parse_file(raw)
    out, idx = ps1_card.write_save(ps1_card.blank_card(), es[0].data, es[0].filename)
    assert out == raw and idx == 1


@pytest.mark.parametrize("path", ps1_files() or [None])
def test_ps1_pc_ps1_preserves_gameplay_state(path):
    if path is None:
        pytest.skip("PS1 fixtures not present")
    s = load_ps1(path)
    orig = model.from_ps1(s)
    back_m = _via_pc(orig)
    b, rep = ps1_writer.build_block(back_m)
    back = model.from_ps1(ps1_save.PS1Save(b, s.product_code, s.filename))
    assert ps1_save.PS1Save(b).crc_ok
    assert back["state"] == orig["state"]
    assert back["event"]["gEventGlobal_b64"] == orig["event"]["gEventGlobal_b64"]
    assert back["party"] == orig["party"] and back["items"] == orig["items"]
    assert back["rare_items"] == orig["rare_items"]
    for i, (a, c) in enumerate(zip(orig["players"], back["players"])):
        for k in PLAYER_KEYS:
            assert a[k] == c[k], (i, k)
        # documented: PC stores bonus.cap 0 as "derive it", so guests with cap 0 come back derived
        assert a["bonus_cap"] == c["bonus_cap"] or (a["bonus_cap"] == 0 and c["bonus_cap"] == (a["level"] - 1) * 5)
    key = lambda c: (c["id"], c["arrow"], c["atk"], c["type"], c["pdef"], c["mdef"])
    assert [key(c) for c in orig["minigame"]["cards"] if c["id"] != 255] == \
           [key(c) for c in back["minigame"]["cards"] if c["id"] != 255]      # gaps compacted (documented)
    assert {k: orig["minigame"][k] for k in ("sWin", "sLose", "sDraw")} == \
           {k: back["minigame"][k] for k in ("sWin", "sLose", "sDraw")}
    assert back["preview"]["playtime_frames"] == orig["preview"]["playtime_frames"]
    assert s.block[0x104] == b[0x104]                                      # disc derived from scenario
    assert rep["zero_filled"], "PS1-only regions must be reported when no PS1 base exists"


@pytest.mark.parametrize("f,slot", _pc_slots() or [(None, None)])
def test_pc_ps1_pc_preserves_common_fields(f, slot):
    if f is None:
        pytest.skip("PC fixtures not present")
    m = model.from_pc(pc_container.Container(open(f, "rb").read()).slot_tree(*slot))
    b, rep = ps1_writer.build_block(m)
    card, idx = ps1_writer.place_on_card(b, 3)
    s = _reparse_card(card, idx)
    assert s.crc_ok and s.region[0] == "NTSC-U"
    back = model.from_ps1(s)
    st = dict(m["state"])
    if (st["wldMapNo"], st["wldLocNo"]) == (0, 0):                       # documented PS1 initial value
        st["wldMapNo"], st["wldLocNo"] = ps1_writer.PS1_INITIAL_WORLD
    assert back["state"] == st
    assert model.gevent_bytes(back) == model.gevent_bytes(m)
    assert back["party"]["slot"] == [9 if x == 255 else x for x in m["party"]["slot"]]
    assert {k: v for k, v in back["party"].items() if k != "slot"} == {k: v for k, v in m["party"].items() if k != "slot"}
    assert back["items"] == m["items"] and back["rare_items"] == m["rare_items"]
    for a, c in zip(m["players"], back["players"]):
        for k in PLAYER_KEYS:
            assert a[k] == c[k], k
    # and on to PC again: the PC slot equals the original except documented PC-only data
    tree2, _ = convert.to_pc_tree(back)
    again = model.from_pc(tree2)
    for k in ("items", "rare_items", "party"):
        assert again[k] == m[k]
    assert abs(again["playtime_seconds"] - m["playtime_seconds"]) <= 1 / 60


def test_pc_only_fields_are_reported():
    m = model.from_pc(load_pc(pcf("ff9SaveLib_testdata_SavedData_ww.dat")).slot_tree(0, 0))
    b, rep = ps1_writer.build_block(m)
    assert any("PS1-only" in g or "title" in g for g in rep["generated"])
    assert rep["zero_filled"]


# ---- card handling ----------------------------------------------------------------------------------
def test_insert_preserves_unrelated_blocks_and_refuses_overwrite():
    base = open(fa(10), "rb").read()
    m = model.from_pc(load_pc(pcf("ff9SaveLib_testdata_SavedData_ww.dat")).slot_tree(0, 0))
    b, _ = ps1_writer.build_block(m, file_no=2)
    out, idx = ps1_writer.place_on_card(b, 2, card=base)
    assert idx == 2
    assert out[0x2000:0x4000] == base[0x2000:0x4000]                          # block 1 untouched
    assert out[0x80:0x100] == base[0x80:0x100]                                # its directory frame untouched
    changed = [i for i in range(len(base)) if out[i] != base[i]]
    assert all(0x100 <= i < 0x180 or 0x4000 <= i < 0x6000 for i in changed)
    with pytest.raises(ps1_writer.PS1WriteError, match="occupied"):
        ps1_writer.place_on_card(b, 3, card=out, block_index=1)
    with pytest.raises(ps1_writer.PS1WriteError, match="already exists"):
        ps1_writer.place_on_card(b, 2, card=out)
    replaced, _ = ps1_card.write_save(out, b, ps1_writer.card_filename(1), 1, replace=True)
    assert replaced[0x4000:0x6000] == out[0x4000:0x6000]


def test_full_card_and_multiblock_protection():
    m = model.from_ps1(load_ps1(fa(1)))
    b, _ = ps1_writer.build_block(m)
    card = ps1_card.blank_card()
    for n in range(1, 16):
        card, _ = ps1_writer.place_on_card(b, n, card=card)
    assert len(ps1_card.parse_file(card)[1]) == 15
    with pytest.raises(ps1_card.CardError, match="full"):
        ps1_card.write_save(card, b, "BASLUS-0125100000-99")
    multi = bytearray(ps1_card.blank_card())
    multi[0x80:0x100] = ps1_card._frame(0x51, 0x4000, 1, b"OTHERGAME")
    with pytest.raises(ps1_card.CardError, match="multi-block"):
        ps1_card.write_save(bytes(multi), b, "BASLUS-0125100000-00", 1, replace=True)


# ---- values that cannot be represented ----------------------------------------------------------------
def test_unrepresentable_values_are_rejected_not_truncated():
    m = model.from_pc(load_pc(pcf("ff9SaveLib_testdata_SavedData_ww.dat")).slot_tree(0, 0))
    for mutate, msg in [
        (lambda x: x["players"][0].__setitem__("name", "ジタン"), "no PS1"),
        (lambda x: x["players"][0].__setitem__("name", "Zidane-Tribal"), "longer"),
        (lambda x: x["players"][0]["info"].__setitem__("menu_type", 40), "5-bit"),
        (lambda x: x["party"].__setitem__("slot", [0, 11, 255, 255]), "party"),
        (lambda x: x["party"].__setitem__("frog_no", 70000), "range"),
        (lambda x: x["minigame"]["cards"][0].__setitem__("type", 9), "attack type"),
    ]:
        mm = copy.deepcopy(m)
        mutate(mm)
        with pytest.raises(ps1_writer.PS1WriteError, match=msg):
            ps1_writer.build_block(mm)


def test_disc_derivation_and_ambiguity():
    assert [ps1_writer.disc_for_scenario(x) for x in (1155, 4160, 7100, 11770)] == [1, 2, 3, 4]
    with pytest.raises(ps1_writer.PS1WriteError, match="explicit disc"):
        ps1_writer.disc_for_scenario(3890)
    m = model.from_pc(load_pc(pcf("ff9SaveLib_testdata_SavedData_ww.dat")).slot_tree(0, 0))
    b, _ = ps1_writer.build_block(m, disc=3)
    assert b[0x104] == 4


def test_pal_uses_50hz_frames_and_title():
    m = model.from_pc(load_pc(pcf("steam_jumprope_b_SavedData_ww.dat")).slot_tree(0, 0))
    b, _ = ps1_writer.build_block(m, region="PAL", file_no=7)
    s = ps1_save.PS1Save(b)
    assert s.preview()["playtime_frames"] == round(m["playtime_seconds"] * 50)
    assert ps1_writer.title_bytes(7, m["playtime_seconds"]) == b[4:4 + 32]


def test_cli_both_directions(tmp_path):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    run = lambda *a: subprocess.run([sys.executable, "-P", "-m", "ffix_conv", *a], env=env, capture_output=True, text=True)
    pc_src = pcf("ff9SaveLib_testdata_SavedData_ww.dat")
    r = run("convert", pc_src, "--out", str(tmp_path / "x.mcr"))
    assert r.returncode != 0 and "--pc-slot" in r.stderr                       # several slots: must choose
    r = run("convert", "--from", "pc", "--to", "ps1", pc_src, "--pc-slot", "1/4", "--ps1-file", "4",
            "--out", str(tmp_path / "oeil.mcr"), "--report", str(tmp_path / "r.json"))
    assert r.returncode == 0, r.stderr
    s = _reparse_card((tmp_path / "oeil.mcr").read_bytes(), 1)
    assert s.crc_ok and s.filename.endswith("-03") and s.scenario_counter == 9750
    r = run("convert", "--from", "pc", "--to", "ps1", pc_src, "--pc-slot", "1/1", "--into", str(tmp_path / "oeil.mcr"),
            "--out", str(tmp_path / "two.mcr"), "--ps1-file", "5")
    assert r.returncode == 0, r.stderr
    _, es = ps1_card.parse_file((tmp_path / "two.mcr").read_bytes())
    assert [e.block_index for e in es] == [1, 2]
    r = run("convert", "--from", "pc", "--to", "ps1", pc_src, "--pc-slot", "1/1", "--format", "mcs",
            "--out", str(tmp_path / "one.mcs"))
    assert r.returncode == 0 and ps1_card.parse_file((tmp_path / "one.mcs").read_bytes())[0] == "mcs-single"
    r = run("convert", str(tmp_path / "oeil.mcr"), "--out", str(tmp_path / "back.dat"), "--slot", "3", "--file", "2")
    assert r.returncode == 0, r.stderr
    assert pc_container.Container((tmp_path / "back.dat").read_bytes()).occupied() == [(2, 1)]


# ---- the user's own multi-save PS1 cards ---------------------------------------------------------
from conftest import ps1_card_saves, load_ps1_block, USER_CARDS  # noqa: E402


@pytest.mark.parametrize("path,block", ps1_card_saves() or [(None, None)])
def test_user_card_saves_round_trip(path, block):
    if path is None:
        pytest.skip("user PS1 cards not present")
    s = load_ps1_block(path, block)
    assert s.crc_ok
    m = model.from_ps1(s)
    b, _ = ps1_writer.build_block(m)
    assert b == s.block                                                    # PS1 -> canonical -> PS1
    back = model.from_ps1(ps1_save.PS1Save(ps1_writer.build_block(_via_pc(m))[0]))
    for k in ("state", "party", "items", "rare_items"):
        assert back[k] == m[k], k                                          # PS1 -> PC -> PS1
    assert back["event"]["gEventGlobal_b64"] == m["event"]["gEventGlobal_b64"]
    if s.block[0x104] in (1, 2, 4, 8):
        assert 1 << (ps1_writer.disc_for_scenario(m["event"]["scenario_counter"]) - 1) == s.block[0x104]


def test_rewriting_every_save_on_a_user_card_in_place_is_byte_identical():
    import glob as _g
    files = sorted(_g.glob(os.path.join(USER_CARDS, "*.srm")))
    if not files:
        pytest.skip("user PS1 cards not present")
    for f in files:
        raw = open(f, "rb").read()
        card = raw
        for e in ps1_card.parse_file(raw)[1]:
            m = model.from_ps1(ps1_save.PS1Save(e.data, e.product_code, e.filename))
            block, _ = ps1_writer.build_block(m)
            card, _ = ps1_card.write_save(card, block, e.filename, e.block_index, replace=True)
        assert card == raw


def test_steal_and_dragon_counters_regression():
    # User's own PS1 run: 3 steals in the opening (as in every PC fixture), dragons only after
    # the world map opens. Confirms 0xEEE = steal_no, 0xEF0 = dragon_no.
    saves = [load_ps1_block(f, b) for f, b in ps1_card_saves()]
    if not saves:
        pytest.skip("user PS1 cards not present")
    steeple = [s for s in saves if s.scenario_counter == 1155][0]
    assert (steeple.party()["steal_no"], steeple.party()["dragon_no"]) == (3, 0)
    steals = [s.party()["steal_no"] for s in sorted(saves, key=lambda s: (s.scenario_counter, s.block[0x178]))]
    assert steals == sorted(steals) and steals[-1] > 25


def test_empty_preview_records_match_the_game_regression():
    # Regression from the DuckStation run: empty party preview records were written as zeros,
    # which the PS1 load screen shows as Zidane portraits (portrait id 0).
    m = model.from_pc(load_pc(pcf("user_FF9_CloudSaveFile_ww.sav")).slot_tree(1, 0))   # Zidane alone
    b, _ = ps1_writer.build_block(m)
    records = [b[0x134 + 16 * k:0x134 + 16 * (k + 1)] for k in range(4)]
    assert records[0][0] == 1 and records[0][1] == 0
    for r in records[1:]:
        assert r[:13] == bytes([0x00]) + bytes([0xFF]) * 11 + bytes([0x00])
