"""PS1 -> canonical -> PC conversion, cross-platform evidence and edge cases."""
import base64
import copy
import os
import subprocess
import sys

import pytest
from conftest import ROOT, fa, load_pc, load_ps1, pcf, ps1_files

from ffix_conv import convert, model, pc_container, pc_schema


def _convert(path, template=None):
    m = model.from_ps1(load_ps1(path))
    tree, rep = convert.to_pc_tree(m, template)
    return m, tree, rep


@pytest.mark.parametrize("path", ps1_files() or [None])
def test_every_ps1_fixture_converts_and_round_trips_semantically(path):
    if path is None:
        pytest.skip("PS1 fixtures not present")
    m, tree, rep = _convert(path)
    assert not rep.errors
    c = convert.blank_container()
    convert.insert(c, 0, 0, tree, convert.preview_for(tree, m, 1.0e9))
    back = model.from_pc(pc_container.Container(c.to_bytes()).slot_tree(0, 0))
    # every mapped field survives exactly
    assert back["state"] == m["state"]
    assert back["event"]["gEventGlobal_b64"] == m["event"]["gEventGlobal_b64"]
    assert back["items"] == m["items"] and back["rare_items"] == m["rare_items"]
    for k in ("escape_no", "summon_flag", "gil", "frog_no", "steal_no", "dragon_no"):
        assert back["party"][k] == m["party"][k]
    assert back["party"]["slot"] == [255 if s == 9 else s for s in m["party"]["slot"]]
    for a, b in zip(m["players"], back["players"]):
        for k in ("name", "category", "level", "exp", "cur", "max", "trance", "web_bone", "elem", "defence",
                  "basis", "info", "status", "equip", "bonus", "bonus_cap", "pa", "sa"):
            assert a[k] == b[k], k
    src_cards = [c for c in m["minigame"]["cards"] if c["id"] != 255]
    dst_cards = [c for c in back["minigame"]["cards"] if c["id"] != 255]
    assert [(c["id"], c["arrow"], c["atk"], c["type"], c["pdef"], c["mdef"]) for c in src_cards] == \
           [(c["id"], c["arrow"], c["atk"], c["type"], c["pdef"], c["mdef"]) for c in dst_cards]
    assert abs(back["playtime_seconds"] - m["playtime_seconds"]) < 1e-6


# ---- cross-platform evidence (real fixtures from different players) -------------
def test_cross_platform_state(steeple_pair):
    ps1, pc = steeple_pair
    field = ("mode", "prevMode", "fldMapNo", "fldLocNo", "btlMapNo", "btlSubMapNo")
    assert {k: ps1["state"][k] for k in field} == {k: pc["state"][k] for k in field}
    # documented initialisation difference before the first world-map visit
    assert (ps1["state"]["wldMapNo"], ps1["state"]["wldLocNo"]) == (9009, 68)
    assert (pc["state"]["wldMapNo"], pc["state"]["wldLocNo"]) == (0, 0)
    assert ps1["event"]["scenario_counter"] == pc["event"]["scenario_counter"] == 1155


def test_gevent_cross_platform(steeple_pair, gulug_pair):
    for (ps1, pc), minimum in ((steeple_pair, 2000), (gulug_pair, 1800)):
        a, b = model.gevent_bytes(ps1), model.gevent_bytes(pc)
        assert len(a) == len(b) == 2048
        assert sum(x == y for x, y in zip(a, b)) >= minimum
    assert gulug_pair[0]["event"]["scenario_counter"] == gulug_pair[1]["event"]["scenario_counter"] == 9950


def test_player_names(steeple_pair):
    ps1, pc = steeple_pair
    assert [p["name"] for p in ps1["players"]] == [p["name"] for p in pc["players"]]


def test_player_core(steeple_pair, gulug_pair):
    ps1, pc = steeple_pair
    for a, b in zip(ps1["players"], pc["players"]):
        for k in ("category", "level", "exp", "elem", "defence", "basis", "equip", "status", "trance"):
            assert a[k] == b[k], k
        assert a["max"] == b["max"]
        assert (a["cur"]["hp"], a["cur"]["mp"], a["cur"]["capa"]) == (b["cur"]["hp"], b["cur"]["mp"], b["cur"]["capa"])
    ps1, pc = gulug_pair
    assert [p["web_bone"] for p in ps1["players"][:8]] == [p["web_bone"] for p in pc["players"][:8]]
    assert (ps1["state"]["wldMapNo"], ps1["state"]["wldLocNo"]) == (pc["state"]["wldMapNo"], pc["state"]["wldLocNo"])


def test_player_info_bits(steeple_pair):
    ps1, pc = steeple_pair
    for a, b in zip(ps1["players"], pc["players"]):
        assert a["info"] == b["info"]


def test_party_slots(steeple_pair):
    ps1, pc = steeple_pair
    assert ps1["party"]["slot"] == [1, 9, 9, 9]
    assert pc["party"]["slot"] == [1, 255, 255, 255]
    tree, _ = convert.to_pc_tree(ps1)
    assert tree["Data"]["40000_Common"]["slot"] == [1, 255, 255, 255]


def test_items(steeple_pair):
    ps1, pc = steeple_pair
    ids = lambda m: [x["id"] for x in m["items"] if x["count"]]
    assert ids(ps1)[:6] == ids(pc)[:6]


def test_rare_items(gulug_pair):
    ps1, pc = gulug_pair
    common = sum(bin(a & b).count("1") for a, b in zip(ps1["rare_items"], pc["rare_items"]))
    assert common >= 0.6 * sum(bin(b).count("1") for b in pc["rare_items"])


def test_party_counters():
    s = load_ps1(fa(41))
    assert s.party()["gil"] == s.preview()["gil"]


def test_cards():
    m, tree, rep = _convert(fa(1))
    cards = tree["Data"]["30000_MiniGame"]["MiniGameCard"]
    assert len(cards) == 100
    n = sum(1 for c in m["minigame"]["cards"] if c["id"] != 255)
    assert all(c["cpoint"] == 10 and c["side"] == 0 for c in cards[:n])
    assert all(c == convert.PC_EMPTY_CARD for c in cards[n:])


def test_playtime():
    m = model.from_ps1(load_ps1(fa(1)))
    assert m["playtime_seconds"] == load_ps1(fa(1)).preview()["playtime_frames"] / 60


def test_preview():
    m, tree, _ = _convert(fa(41))
    pv = convert.preview_for(tree, m, 123.0)
    assert pv.location == "Esto Gaza/Terrace"
    assert pc_container.Preview.parse(pv.build()) == pv


def test_defaults():
    m, tree, rep = _convert(fa(10))
    d = tree["Data"]
    assert d["20000_Event"]["gStepCount"] == 0
    assert d["50000_Setting"]["time"] == -1.0 and d["60000_Sound"]["auto_save_bgm_id"] == -1
    assert not any(d["99000_Other"])
    for k in ("abilities", "passiveAbilities", "QuadmistWinList"):      # game's "empty" marker
        assert set(d["80000_Achievement"][k]) == {-1}
    assert any("timerControl" in x for x in rep.defaulted)
    tmpl = load_pc(pcf("ff9SaveLib_testdata_SavedData_ww.dat")).slot_tree(0, 0)
    _, t2, rep2 = _convert(fa(10), template=tmpl)
    assert t2["Data"]["50000_Setting"]["cfg"] == tmpl["Data"]["50000_Setting"]["cfg"]
    assert t2["Data"]["40000_Common"] == tree["Data"]["40000_Common"]      # template never leaks game state


def test_conversion_is_deterministic():
    m = model.from_ps1(load_ps1(fa(20)))
    outs = []
    for _ in range(2):
        tree, _ = convert.to_pc_tree(copy.deepcopy(m))
        c = convert.blank_container()
        convert.insert(c, 2, 3, tree, convert.preview_for(tree, m, 42.0))
        outs.append(c.to_bytes())
    assert outs[0] == outs[1]


# ---- negative / edge cases -------------------------------------------------------------
def test_strict_crc_and_region_errors():
    m = model.from_ps1(load_ps1(fa(1)))
    bad = copy.deepcopy(m)
    bad["source"]["crc_ok"] = False
    with pytest.raises(convert.ConversionError, match="CRC"):
        convert.to_pc_tree(bad)
    _, rep = convert.to_pc_tree(bad, strict=False)
    assert any("CRC" in w for w in rep.warnings)
    jp = copy.deepcopy(m)
    jp["source"]["region"] = "NTSC-J"
    with pytest.raises(convert.ConversionError, match="region"):
        convert.to_pc_tree(jp)


def test_too_many_cards_rejected():
    m = model.from_ps1(load_ps1(fa(1)))
    m["minigame"]["cards"] = [{"id": i % 100, "arrow": 0, "atk": 0, "type": 0, "pdef": 0, "mdef": 0} for i in range(105)]
    with pytest.raises(convert.ConversionError, match="at most 100"):
        convert.to_pc_tree(m)


def test_invalid_party_and_card_values_rejected():
    m = model.from_ps1(load_ps1(fa(1)))
    m1 = copy.deepcopy(m)
    m1["party"]["slot"] = [0, 12, 9, 9]
    with pytest.raises(convert.ConversionError, match="party"):
        convert.to_pc_tree(m1)
    m2 = copy.deepcopy(m)
    m2["minigame"]["cards"][0]["type"] = 7
    with pytest.raises(convert.ConversionError, match="card"):
        convert.to_pc_tree(m2)


def test_bad_gevent_length_rejected():
    m = model.from_ps1(load_ps1(fa(1)))
    m["event"]["gEventGlobal_b64"] = base64.b64encode(bytes(100)).decode()
    with pytest.raises(convert.ConversionError, match="2048"):
        convert.to_pc_tree(m)


def test_out_of_range_values_fail_safely():
    m = model.from_ps1(load_ps1(fa(1)))
    m["party"]["gil"] = 2 ** 33
    with pytest.raises(Exception):
        convert.to_pc_tree(m)


def test_unusual_inventory_and_ability_combinations():
    m = model.from_ps1(load_ps1(fa(54)))
    m["items"] = [{"id": i, "count": 99} for i in range(256)]
    for p in m["players"]:
        p["pa"] = [255] * 48
        p["sa"] = [0xFFFFFFFF, 0xFFFFFFFF]
    tree, _ = convert.to_pc_tree(m)
    back = model.from_pc(pc_schema.decode(pc_schema.encode(tree)))
    assert back["items"] == m["items"] and back["players"][3]["sa"] == [0xFFFFFFFF] * 2


def test_cli_refuses_to_overwrite_and_converts(tmp_path):
    src = fa(32)
    out = tmp_path / "SavedData_ww.dat"
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    cmd = [sys.executable, "-P", "-m", "ffix_conv", "convert", src, "--out", str(out), "--slot", "2", "--file", "3",
           "--timestamp", "1", "--report", str(tmp_path / "r.json")]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    c = pc_container.Container(out.read_bytes())
    assert c.occupied() == [(1, 2)] and (c.meta.latest_slot, c.meta.latest_save) == (1, 2)
    r2 = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert r2.returncode != 0 and "refusing to overwrite" in r2.stderr
    into = tmp_path / "into.dat"
    base = pcf("steam_cd3thread_SavedData_ww.dat")
    r3 = subprocess.run([sys.executable, "-P", "-m", "ffix_conv", "convert", src, "--out", str(into), "--into", base,
                         "--slot", "2", "--file", "1"], env=env, capture_output=True, text=True)
    assert r3.returncode != 0 and "occupied" in r3.stderr
