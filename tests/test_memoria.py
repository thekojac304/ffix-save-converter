"""Memoria / Moguri saves: sidecar format, slot association, Memoria's load rules, and Memoria -> PS1 safety.

Fixtures: the one public Memoria sidecar (ffix-save-editor examples, MIT) for the binary format, and synthetic
container + sidecar pairs built from vanilla PC saves with memoria.synthesize (what Memoria writes for that state).
Moguri adds no save data (docs/MEMORIA_RESEARCH.md section 7), so a Moguri save is tested as a Memoria save with
vanilla-range values.
"""
import base64
import copy
import hashlib
import os
import shutil
import struct

import pytest

from conftest import fa, pcf
from ffix_conv import memoria, model, pc_container, ps1_card, ps1_save, service

SAMPLE = "ffixsaveeditor_example_SavedData_ww_Memoria_0_0.dat"
VANILLA = "ff9SaveLib_testdata_SavedData_ww.dat"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def memoria_pair(tmp_path, edit=None, time_offset=0.0, name="game"):
    """A game folder with SavedData_ww.dat (vanilla fixture) and a Memoria sidecar for slot 1/1."""
    folder = tmp_path / name
    folder.mkdir()
    cont = folder / "SavedData_ww.dat"
    shutil.copy(pcf(VANILLA), cont)
    m = model.from_pc(pc_container.Container(cont.read_bytes()).slot_tree(0, 0))
    side = memoria.synthesize(m, m["playtime_seconds"] + time_offset)
    if edit:
        edit(side)
    (folder / "SavedData_ww_Memoria_0_0.dat").write_bytes(memoria.dumps(side))
    return cont


def to_ps1(tmp_path, src, out_name, **kw):
    out = tmp_path / out_name
    return service.convert_file(service.ConvertOptions(input=str(src), source="1/1", out=str(out), **kw))


def ps1_model(path):
    _, entries = ps1_card.parse_file(open(path, "rb").read())
    e = entries[0]
    return model.from_ps1(ps1_save.PS1Save(e.data, e.product_code, e.filename))


def vanilla_ps1(tmp_path):
    """Reference: the same container converted with no Memoria data next to it."""
    plain = tmp_path / "plain"
    plain.mkdir()
    shutil.copy(pcf(VANILLA), plain / "SavedData_ww.dat")
    return to_ps1(tmp_path, plain / "SavedData_ww.dat", "vanilla.mcr")


# ---- binary format -------------------------------------------------------------------------------------
def test_sample_sidecar_round_trips_byte_for_byte():
    raw = open(pcf(SAMPLE), "rb").read()
    root, end = memoria.parse(raw)
    assert end == len(raw)
    assert memoria.dumps(root) == raw
    assert memoria.looks_like_sidecar(raw)
    c = root["40000_Common"]
    assert [p["info"]["slot_no"] for p in c["players"]] == list(range(12))
    assert len(base64.b64decode(root["20000_Event"]["gEventGlobal"])) == 2048


def test_trailing_bytes_from_memorias_non_truncating_writer_are_ignored():
    raw = open(pcf(SAMPLE), "rb").read()
    root, end = memoria.parse(raw + b"\x02\x00\x00\x00old tail")
    assert end == len(raw) and memoria.dumps(root) == raw


@pytest.mark.parametrize("bad", [
    b"", b"\x02\x00\x00\x00", b"\x09\x00\x00\x00", b"\x01\x00\x00\x00\x00\x00\x00\x00",   # empty, truncated, tag, array root
    b"\x02\x00\x00\x00\xff\xff\xff\xff",                                              # negative count
    b"\x02\x00\x00\x00\x01\x00\x00\x00\xff\xff\xff\xff\x0f",                          # string length past the end
])
def test_corrupt_sidecars_are_rejected(bad):
    with pytest.raises(memoria.MemoriaFormatError):
        memoria.parse(bad)
    assert not memoria.looks_like_sidecar(bad)


def test_deep_nesting_is_rejected():
    raw = struct.pack("<ii", 2, 1) + b"\x01a" + struct.pack("<ii", 1, 1) * 200 + struct.pack("<ii", 1, 0)
    with pytest.raises(memoria.MemoriaFormatError, match="deeply"):
        memoria.parse(raw)


def test_all_value_tags_round_trip():
    root = {"a": 1, "b": 2.5, "c": memoria.F32(0.5), "d": True, "e": "Ω text", "f": [1, [2]], "g": {}, "h": 2 ** 40}
    back, _ = memoria.parse(memoria.dumps(root))
    assert back == {**root, "h": float(2 ** 40)} and isinstance(back["c"], memoria.F32)


def test_opening_a_sidecar_directly_explains_what_to_open(tmp_path):
    p = tmp_path / "SavedData_ww_Memoria_0_0.dat"
    shutil.copy(pcf(SAMPLE), p)
    with pytest.raises(service.UserError, match="SavedData_ww.dat from the same folder"):
        service.list_saves(str(p))


# ---- association and Memoria's load rules -----------------------------------------------------------------------------
def test_sidecar_names_and_indices(tmp_path):
    cont = memoria_pair(tmp_path)
    (cont.parent / "SavedData_ww_Memoria_Autosave.dat").write_bytes(b"")
    (cont.parent / "SavedData_ww_Memoria_9_14.dat").write_bytes(b"")
    (cont.parent / "Other_Memoria_0_0.dat").write_bytes(b"")
    found = memoria.sidecars_beside(str(cont))
    assert set(found) == {(0, 0), (9, 14), "autosave"}
    assert memoria.sidecar_path(str(cont), 2, 5).endswith("SavedData_ww_Memoria_2_5.dat")


@pytest.mark.parametrize("offset,status", [(0.0, "valid"), (0.9, "valid"), (1.5, "stale"), (-30, "stale")])
def test_staleness_follows_memorias_one_second_rule(tmp_path, offset, status):
    cont = memoria_pair(tmp_path, time_offset=offset)
    t = model.from_pc(pc_container.Container(cont.read_bytes()).slot_tree(0, 0))["playtime_seconds"]
    assert memoria.slot_sidecar(str(cont), 0, 0, t)["status"] == status


def test_listing_shows_memoria_status(tmp_path):
    cont = memoria_pair(tmp_path)
    head, rows = service.list_saves(str(cont))
    assert head["memoria_sidecars"] == 1 and "Memoria sidecar" in head["format"]
    assert rows[0]["memoria"] == "valid"


# ---- Memoria / Moguri -> PS1 ---------------------------------------------------------------------------------------------
def test_redundant_sidecar_gives_the_vanilla_result(tmp_path):
    """A Moguri (visual-only) or unmodded Memoria save: the sidecar agrees with the container, so the PS1 save is
    byte-identical to converting the container alone, and the report says the sidecar was considered."""
    ref = vanilla_ps1(tmp_path)
    cont = memoria_pair(tmp_path)
    r = to_ps1(tmp_path, cont, "moguri.mcr")
    assert open(r["out"], "rb").read() == open(ref["out"], "rb").read()
    mem = r["report"]["memoria"]
    assert mem["sidecar_status"] == "valid" and not mem["blocking"] and not mem["taken_from_sidecar"]
    assert any("Cinna" in x or "Quina" in x for x in mem["dropped_memoria_only"])     # inactive pair member
    assert "Memoria/Moguri->PS1 beta" in r["report"]["conversion_status"]
    assert service.verify_files(str(cont), r["out"], "1/1")["counts"]["unexpected"] == 0


def test_stale_sidecar_is_ignored_and_reported(tmp_path):
    ref = vanilla_ps1(tmp_path)

    def mod(side):
        side["40000_Common"]["gil"] = 1234567
        side["40000_Common"]["players"][0]["equip"][0] = 300           # would block if applied
    cont = memoria_pair(tmp_path, mod, time_offset=60)
    r = to_ps1(tmp_path, cont, "stale.mcr")
    assert open(r["out"], "rb").read() == open(ref["out"], "rb").read()
    assert r["report"]["memoria"]["sidecar_status"] == "stale"
    assert any("ignored, exactly as Memoria does" in w for w in r["report"]["compatibility"]["warnings"])


def test_valid_sidecar_overrides_the_container(tmp_path):
    def mod(side):
        c = side["40000_Common"]
        c["gil"] = 1234567
        c["players"][0]["level"] = 50
        c["players"][0]["equip"][4] = 200
        owned = {x["id"] for x in c["items"]}
        c["items"].append({"id": next(i for i in range(1, 250) if i not in owned), "count": 3})
        side["30000_MiniGame"]["sWin"] = 77
    cont = memoria_pair(tmp_path, mod)
    r = to_ps1(tmp_path, cont, "override.mcr")
    out = ps1_model(r["out"])
    assert out["party"]["gil"] == 1234567 and out["players"][0]["level"] == 50
    assert out["players"][0]["equip"][4] == 200 and out["minigame"]["sWin"] == 77
    applied = " ".join(r["report"]["memoria"]["taken_from_sidecar"])
    assert "gil" in applied and "inventory" in applied and "Zidane" in applied
    assert service.verify_files(str(cont), r["out"], "1/1")["counts"]["unexpected"] == 0


def test_untimed_sidecar_is_applied_like_memoria(tmp_path):
    def mod(side):
        del side["95000_Setting"]["00001_time"]
        side["40000_Common"]["gil"] = 4242
    r = to_ps1(tmp_path, memoria_pair(tmp_path, mod), "untimed.mcr")
    assert ps1_model(r["out"])["party"]["gil"] == 4242
    assert r["report"]["memoria"]["sidecar_status"] == "untimed"


def test_legacy_ability_counters_are_cleared(tmp_path):
    def mod(side):
        g = bytearray(base64.b64decode(side["20000_Event"]["gEventGlobal"]))
        g[1100 + 5] = 9
        side["20000_Event"]["gEventGlobal"] = base64.b64encode(bytes(g)).decode()
    r = to_ps1(tmp_path, memoria_pair(tmp_path, mod), "legacy.mcr")
    assert model.gevent_bytes(ps1_model(r["out"]))[1105] == 0
    assert any("1101-1291" in x for x in r["report"]["memoria"]["taken_from_sidecar"])


def _equip(side):
    side["40000_Common"]["players"][0]["equip"][0] = 300


def _item(side):
    side["40000_Common"]["items"].append({"id": 400, "count": 1})


def _script(side):
    side["20000_Event"]["gScriptVector"] = [{"id": 1, "entries": [3, 4]}]


def _hp(side):
    p = side["40000_Common"]["players"][0]
    p["maxHpLimit"] = 99999
    p["max"]["hp"] = p["cur"]["hp"] = p["basis"]["max_hp"] = 15000


def _sa(side):
    side["40000_Common"]["players"][1]["sa_extended"].append(70)


def _card(side):
    side["30000_MiniGame"]["MiniGameCard"].append({"id": 120, "side": 0, "atk": 1, "type": 0, "pdef": 1, "mdef": 1,
                                                   "cpoint": 10, "arrow": 1})


def _ap(side):
    """Memoria's container keeps AP wrapped to a byte, so a value 256 higher is consistent with it."""
    side["40000_Common"]["players"][0]["pa_extended"][0]["cur"] += 256


LOSSY_CASES = {"mod equipment": (_equip, "item id 300"), "mod item": (_item, "mod item stack"),
               "script storage": (_script, "script vector"), "raised HP limit": (_hp, "HP 15000"),
               "mod support ability": (_sa, "support abilities [70]"), "mod card": (_card, "Tetra Master card"),
               "AP above 255": (_ap, "AP in one ability is above")}


@pytest.mark.parametrize("case", sorted(LOSSY_CASES))
def test_unrepresentable_values_block_by_default_and_need_lossy(tmp_path, case):
    edit, text = LOSSY_CASES[case]
    cont = memoria_pair(tmp_path, edit)
    with pytest.raises(service.UserError) as e:
        to_ps1(tmp_path, cont, "refused.mcr")
    assert text in str(e.value) and "lossy" in str(e.value)
    assert not (tmp_path / "refused.mcr").exists()
    r = to_ps1(tmp_path, cont, "lossy.mcr", allow_lossy=True)
    assert any(text in x for x in r["report"]["memoria"]["lossy"])
    assert any(x.startswith("LOSSY") for x in r["report"]["compatibility"]["unsupported_or_lossy"])
    assert service.verify_files(str(cont), r["out"], "1/1")["counts"]["unexpected"] == 0
    out = ps1_model(r["out"])
    if case == "mod equipment":
        assert out["players"][0]["equip"][0] == 255
    if case == "raised HP limit":
        assert out["players"][0]["max"]["hp"] == 9999


def _custom_in_party(side):
    c = side["40000_Common"]
    extra = copy.deepcopy(c["players"][0])
    extra["name"], extra["info"]["slot_no"] = "Kuja", 12
    c["players"].append(extra)
    c["slot"][1] = 12


def _modded_abilities(side):
    side["40000_Common"]["players"][0]["pa_extended"][3]["id"] = 700


def _event_size(side):
    side["20000_Event"]["gEventGlobal"] = base64.b64encode(bytes(4096)).decode()


@pytest.mark.parametrize("edit,text", [(_custom_in_party, "is in the party"), (_modded_abilities, "modded ability list"),
                                       (_event_size, "not 2,048 bytes")])
def test_unsafe_states_are_refused_even_with_lossy(tmp_path, edit, text):
    cont = memoria_pair(tmp_path, edit)
    for lossy in (False, True):
        with pytest.raises(service.UserError, match=text):
            to_ps1(tmp_path, cont, f"x{lossy}.mcr", allow_lossy=lossy)


def test_corrupt_sidecar_blocks_unless_lossy_ignores_it(tmp_path):
    cont = memoria_pair(tmp_path)
    (cont.parent / "SavedData_ww_Memoria_0_0.dat").write_bytes(b"\x02\x00\x00\x00\x05\x00")
    with pytest.raises(service.UserError, match="corrupt"):
        to_ps1(tmp_path, cont, "c.mcr")
    r = to_ps1(tmp_path, cont, "c2.mcr", allow_lossy=True)
    assert open(r["out"], "rb").read() == open(vanilla_ps1(tmp_path)["out"], "rb").read()


def test_sources_are_never_modified(tmp_path):
    cont = memoria_pair(tmp_path)
    side = cont.parent / "SavedData_ww_Memoria_0_0.dat"
    h1, h2 = sha(cont), sha(side)
    to_ps1(tmp_path, cont, "a.mcr")
    assert sha(cont) == h1 and sha(side) == h2


# ---- PS1 -> Memoria / Moguri: never let an old sidecar overlay the converted save ------------------------------------------
def test_matching_sidecar_at_destination_refuses_the_write(tmp_path):
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    game = tmp_path / "game"
    game.mkdir()
    dest = game / "SavedData_ww.dat"
    shutil.copy(pcf(VANILLA), dest)
    probe = service.convert_file(service.ConvertOptions(input=str(src), into=str(dest), dest="5/5",
                                                         out=str(tmp_path / "probe.dat")), dry_run=True)
    t = probe["model"]["playtime_seconds"]
    side = memoria.synthesize(model.from_pc(pc_container.Container(dest.read_bytes()).slot_tree(0, 0)), t)
    (game / "SavedData_ww_Memoria_4_4.dat").write_bytes(memoria.dumps(side))
    h = sha(dest)
    with pytest.raises(service.UserError, match="would be loaded over the converted save"):
        service.convert_file(service.ConvertOptions(input=str(src), into=str(dest), dest="5/5", in_place=True, force=True))
    assert sha(dest) == h


def test_stale_sidecar_at_destination_is_a_warning(tmp_path):
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    game = tmp_path / "game"
    game.mkdir()
    dest = game / "SavedData_ww.dat"
    shutil.copy(pcf(VANILLA), dest)
    side = memoria.synthesize(model.from_pc(pc_container.Container(dest.read_bytes()).slot_tree(0, 0)), 99999.0)
    (game / "SavedData_ww_Memoria_4_4.dat").write_bytes(memoria.dumps(side))
    r = service.convert_file(service.ConvertOptions(input=str(src), into=str(dest), dest="5/5", in_place=True, force=True))
    assert any("old Memoria sidecar" in w for w in r["report"]["compatibility"]["warnings"])
    assert r["backup"] and os.path.exists(r["backup"])


def test_ps1_to_pc_output_loads_without_sidecar_under_memoria_rules(tmp_path):
    """PS1 -> Memoria: Memoria reads vanilla containers unchanged; with no sidecar it loads the container alone."""
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    r = service.convert_file(service.ConvertOptions(input=str(src), out=str(tmp_path / "pc" / "SavedData_ww.dat"),
                                                    create_dir=True))
    assert memoria.sidecars_beside(r["out"]) == {}
    t = model.from_pc(pc_container.Container(open(r["out"], "rb").read()).slot_tree(0, 0))["playtime_seconds"]
    assert memoria.slot_sidecar(r["out"], 0, 0, t)["status"] == "none"


def test_reconciling_a_faithful_sidecar_is_the_identity_on_every_vanilla_slot():
    """Every PC fixture slot: the sidecar Memoria would write for that state changes nothing and blocks nothing."""
    from conftest import pc_files
    n = 0
    for f in pc_files():
        c = pc_container.Container(open(f, "rb").read())
        for s, fi in c.occupied():
            tree = c.slot_tree(s, fi)
            m0 = model.from_pc(tree)
            side = {"status": "valid", "path": "x", "root": memoria.synthesize(m0), "time": m0["playtime_seconds"]}
            m, rec = memoria.reconcile(tree, side)
            assert not rec.blocking and not rec.applied and not rec.lossy, (f, s, fi, rec.as_dict())
            assert m == m0
            n += 1
    if not n:
        pytest.skip("no PC fixtures")
