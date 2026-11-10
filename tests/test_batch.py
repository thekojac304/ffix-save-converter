"""Batch conversion (ffix_conv.batch) and the multi-file transaction behind it (safeio.Transaction).

Uses the user's own multi-save RetroArch cards (15 and 13 FF9 saves), multi-slot PC files and the genuine Memoria
sidecar cases; every test works on copies in tmp_path.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT, USER_CARDS, pcf
from ffix_conv import batch, pc_container, ps1_card, ps1_writer, safeio, service, verify

MEMORIA = os.path.join(ROOT, "fixtures", "memoria", "runtime_20261106")
TS = 1_700_000_000.0


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def card(n_saves):
    m = [f for f in glob.glob(os.path.join(USER_CARDS, "*.srm"))
         if len(ps1_card.parse_file(open(f, "rb").read())[1]) == n_saves]
    if not m:
        pytest.skip(f"user card with {n_saves} saves not present")
    return m[0]


@pytest.fixture
def card15(tmp_path):
    return shutil.copy(card(15), tmp_path / "card15.srm")


@pytest.fixture
def card13(tmp_path):
    return shutil.copy(card(13), tmp_path / "card13.srm")


@pytest.fixture
def pc6(tmp_path):
    d = tmp_path / "pc6"
    d.mkdir()
    return shutil.copy(pcf("steam_cd3thread_SavedData_ww.dat"), d / "SavedData_ww.dat")


def memoria_copy(tmp_path, case):
    src = os.path.join(MEMORIA, case)
    if not os.path.isdir(src):
        pytest.skip(f"Memoria runtime fixture {case} not present")
    dst = tmp_path / case
    shutil.copytree(src, dst)
    return str(dst / "SavedData_ww.dat")


def files_in(folder):
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def shuffled_card(src_card, tmp_path):
    """The saves of src_card written into the opposite directory blocks: block 15 holds FILE01, and so on."""
    _, entries = ps1_card.parse_file(open(src_card, "rb").read())
    c = ps1_card.blank_card()
    for e in entries:
        c, _ = ps1_card.write_save(c, e.data[:ps1_card.BLOCK], e.filename, 16 - e.block_index)
    p = tmp_path / "shuffled.mcr"
    p.write_bytes(c)
    return str(p)


# ---- PS1 card -> PC ------------------------------------------------------------------------------
def test_full_card_becomes_one_pc_slot_file01_to_file15(card15, tmp_path):
    before = sha(card15)
    out = str(tmp_path / "new" / "SavedData_ww.dat")
    plan = batch.prepare(batch.BatchOptions(card15, out=out, timestamp=TS))
    assert plan.ok and not plan.needs_approval and plan.destination == "new"
    assert [a.dest_label for a in plan.assignments] == [f"Slot 1, file {n}" for n in range(1, 16)]
    assert [a.source_label for a in plan.assignments] == [f"FILE{n:02d}" for n in range(1, 16)]
    assert not os.path.exists(out)                                      # prepare writes nothing
    r = batch.commit(plan)
    assert r["outputs"][0]["path"] == out and sha(card15) == before
    c = pc_container.Container(open(out, "rb").read())
    assert c.occupied() == [(0, f) for f in range(15)]
    for blk in range(1, 16):                                            # independent re-verification of every save
        v = service.verify_files(card15, out, str(blk), f"1/{blk}")
        assert v["counts"]["unexpected"] == 0
    rep = json.load(open(r["report_path"], encoding="utf-8"))
    assert rep["kind"] == "batch" and len(rep["saves"]) == 15 and rep["outputs"][0]["sha256"] == sha(out)
    # the most-played save is the newest, so the game's Continue opens it
    assert c.meta.latest_slot == 0 and c.meta.latest_save == 14


def test_batch_saves_are_byte_identical_to_single_conversion(card15, pc6, tmp_path):
    """Batch output uses the same engine as the in-game-verified single-save conversion: the save data written for
    each save is byte-for-byte the same (only the menu time stamp and the newest-save marker differ)."""
    out = str(tmp_path / "b" / "SavedData_ww.dat")
    batch.run(batch.BatchOptions(card15, out=out, timestamp=TS))
    c = pc_container.Container(open(out, "rb").read())
    for blk in (1, 7, 15):
        single = service.convert_file(service.ConvertOptions(input=card15, source=str(blk), dest=f"1/{blk}",
                                                             timestamp=TS), dry_run=True)
        one = service.convert_file(service.ConvertOptions(input=card15, source=str(blk), dest=f"1/{blk}", timestamp=TS,
                                                          out=str(tmp_path / f"s{blk}" / "SavedData_ww.dat"),
                                                          create_dir=True))
        s = pc_container.Container(open(one["out"], "rb").read())
        assert s.slot_plain(0, blk - 1) == c.slot_plain(0, blk - 1)
        assert single["counts"]["unexpected"] == 0
    folder = str(tmp_path / "cards")
    r = batch.run(batch.BatchOptions(pc6, select=["2/3"], out=folder))
    _, entries = ps1_card.parse_file(open(r["outputs"][0]["path"], "rb").read())
    one = service.convert_file(service.ConvertOptions(input=pc6, source="2/3", dest="3",
                                                      out=str(tmp_path / "one.mcr")))
    _, single_entries = ps1_card.parse_file(open(one["out"], "rb").read())
    assert entries[0].data == single_entries[0].data and entries[0].filename == single_entries[0].filename


def test_file_numbers_not_directory_blocks(tmp_path):
    src = shuffled_card(card(13), tmp_path)
    plan = batch.prepare(batch.BatchOptions(src, out=str(tmp_path / "o" / "SavedData_ww.dat"), timestamp=TS))
    assert plan.ok
    by_block = {a.id: a for a in plan.assignments}
    assert by_block["15"].source_label == "FILE01" and by_block["15"].dest_label == "Slot 1, file 1"
    assert by_block["3"].source_label == "FILE13" and by_block["3"].dest_label == "Slot 1, file 13"
    head, items = batch.scan(src)
    assert {i["id"]: i["label"] for i in items}["15"] == "FILE01"


def test_selected_saves_only(card15, tmp_path):
    out = str(tmp_path / "sel" / "SavedData_ww.dat")
    r = batch.run(batch.BatchOptions(card15, select=["12", "3", "7"], out=out, timestamp=TS))
    assert [a.id for a in r["plan"].assignments] == ["3", "7", "12"]       # source order
    assert pc_container.Container(open(out, "rb").read()).occupied() == [(0, 2), (0, 6), (0, 11)]


def test_second_card_goes_to_next_empty_slot_and_keeps_existing(card15, card13, tmp_path):
    out = str(tmp_path / "pc" / "SavedData_ww.dat")
    batch.run(batch.BatchOptions(card15, out=out, timestamp=TS))
    first = open(out, "rb").read()
    plan = batch.prepare(batch.BatchOptions(card13, into=out, in_place=True, timestamp=TS))
    assert plan.ok and plan.destination == "in-place" and not plan.replacements
    assert {a.dest_label.split(",")[0] for a in plan.assignments} == {"Slot 2"}
    r = batch.commit(plan)
    backup = r["outputs"][0]["backup"]
    assert backup and open(backup, "rb").read() == first                  # verified backup of the replaced file
    after = open(out, "rb").read()
    for f in range(15):                                                  # slot 1 byte-identical
        o = pc_container.block_offset(0, f)
        assert after[o:o + pc_container.BLOCK_RESERVED] == first[o:o + pc_container.BLOCK_RESERVED]
    assert len(pc_container.Container(after).occupied()) == 28


def test_copy_mode_leaves_existing_file_alone(card13, pc6, tmp_path):
    before = sha(pc6)
    r = batch.run(batch.BatchOptions(card13, into=pc6, timestamp=TS))
    assert r["plan"].destination == "copy" and sha(pc6) == before
    out = r["outputs"][0]["path"]
    assert out != os.path.abspath(pc6) and "with_converted_saves" in out
    c = pc_container.Container(open(out, "rb").read())
    assert len(c.occupied()) == 6 + 13
    assert {a.dest_label.split(",")[0] for a in r["plan"].assignments} == {"Slot 3"}   # slots 1, 2 and 4 are in use


def test_no_empty_slot_shares_a_slot_without_replacing(card13, tmp_path):
    c = pc_container.Container(open(pcf("steam_cd3thread_SavedData_ww.dat"), "rb").read())
    from ffix_conv import convert
    tree = c.slot_tree(0, 0)
    for s in range(10):                                                   # something in file 15 of every slot
        convert.insert(c, s, 14, tree, c.preview(0, 0), overwrite=True, set_latest=False)
    p = tmp_path / "full.dat"
    p.write_bytes(c.to_bytes())
    plan = batch.prepare(batch.BatchOptions(card13, into=str(p), timestamp=TS))   # FILE01-13 fit beside file 15
    assert plan.ok and not plan.replacements and plan.warnings
    assert plan.assignments[0].dest_label == "Slot 3, file 1"


def test_occupied_destination_needs_approval(card13, pc6, tmp_path):
    before = sha(pc6)
    plan = batch.prepare(batch.BatchOptions(card13, into=pc6, in_place=True, pc_slot=2, timestamp=TS))
    assert plan.ok and plan.needs_approval and len(plan.replacements) == 4      # slot 2 holds files 1-4
    with pytest.raises(service.UserError, match="approve"):
        batch.commit(plan)
    assert sha(pc6) == before and files_in(os.path.dirname(pc6)) == ["SavedData_ww.dat"]
    plan = batch.prepare(batch.BatchOptions(card13, into=pc6, in_place=True, pc_slot=2, replace=True, timestamp=TS))
    r = batch.commit(plan)
    assert r["outputs"][0]["backup"] and sha(r["outputs"][0]["backup"]) == before
    c = pc_container.Container(open(pc6, "rb").read())
    orig = pc_container.Container(open(r["outputs"][0]["backup"], "rb").read())
    assert c.slot_plain(0, 0) == orig.slot_plain(0, 0) and c.slot_plain(3, 0) == orig.slot_plain(3, 0)


def test_manual_mapping(card15, tmp_path):
    out = str(tmp_path / "m" / "SavedData_ww.dat")
    plan = batch.prepare(batch.BatchOptions(card15, select=["1", "2"], mapping={"1": "7/9", "2": "10/15"}, out=out,
                                            timestamp=TS))
    assert [a.dest_label for a in plan.assignments] == ["Slot 7, file 9", "Slot 10, file 15"]
    with pytest.raises(service.UserError, match="twice"):
        batch.prepare(batch.BatchOptions(card15, select=["1", "2"], mapping={"1": "1/1", "2": "1/1"}, out=out))
    with pytest.raises(service.UserError, match="no place"):
        batch.prepare(batch.BatchOptions(card15, select=["1", "2"], mapping={"1": "1/1"}, out=out))


def test_damaged_save_blocks_the_batch_until_left_out(card13, tmp_path):
    raw = bytearray(open(card13, "rb").read())
    raw[5 * ps1_card.BLOCK + 0x400] ^= 0xFF                              # break block 5's checksum
    bad = tmp_path / "bad.srm"
    bad.write_bytes(raw)
    out = str(tmp_path / "o" / "SavedData_ww.dat")
    plan = batch.prepare(batch.BatchOptions(str(bad), out=out, timestamp=TS))
    assert not plan.ok and [a.id for a in plan.assignments if a.problem] == ["5"]
    assert plan.assignments[4].problem_kind == "checksum"
    with pytest.raises(service.UserError, match="FILE05"):
        batch.commit(plan)
    assert not os.path.exists(os.path.dirname(out))
    keep = [a.id for a in plan.assignments if not a.problem]
    assert batch.run(batch.BatchOptions(str(bad), select=keep, out=out, timestamp=TS))["outputs"]


# ---- PC -> PS1 -----------------------------------------------------------------------------------
def test_full_pc_export_packs_into_one_card(pc6, tmp_path):
    before = sha(pc6)
    folder = str(tmp_path / "cards")
    r = batch.run(batch.BatchOptions(pc6, out=folder))
    assert files_in(folder) == ["FFIX-PS1-Card-01.mcr", "conversion-manifest.json", "conversion-manifest.txt"]
    assert sha(pc6) == before
    c = os.path.join(folder, "FFIX-PS1-Card-01.mcr")
    _, entries = ps1_card.parse_file(open(c, "rb").read())
    assert [service.ps1_file_number(e.filename) for e in entries] == [1, 2, 3, 4, 5, 6]
    for a in r["plan"].assignments:
        v = service.verify_files(pc6, c, a.id, str(entries[a.file - 1].block_index))
        assert v["counts"]["unexpected"] == 0
    text = open(os.path.join(folder, "conversion-manifest.txt"), encoding="utf-8").read()
    assert "Card 01, FILE06" in text and "Slot 4, file 1" in text


def test_by_slot_layout_one_card_per_slot_keeps_file_numbers(pc6, tmp_path):
    folder = str(tmp_path / "cards")
    r = batch.run(batch.BatchOptions(pc6, out=folder, layout="by-slot"))
    assert [os.path.basename(x["path"]) for x in r["outputs"]] == [f"FFIX-PS1-Card-0{n}.mcr" for n in (1, 2, 3)]
    labels = {a.id: a.dest_label for a in r["plan"].assignments}
    assert labels == {"1/1": "Card 01, FILE01", "2/1": "Card 02, FILE01", "2/2": "Card 02, FILE02",
                      "2/3": "Card 02, FILE03", "2/4": "Card 02, FILE04", "4/1": "Card 03, FILE01"}


def test_one_slot_keeps_its_file_numbers(pc6, tmp_path):
    r = batch.run(batch.BatchOptions(pc6, select=["2/2", "2/4"], out=str(tmp_path / "c")))
    assert [a.dest_label for a in r["plan"].assignments] == ["Card 01, FILE02", "Card 01, FILE04"]


def test_single_save_mcs_files(pc6, tmp_path):
    folder = str(tmp_path / "mcs")
    r = batch.run(batch.BatchOptions(pc6, select=["2/1", "4/1"], out=folder, format="mcs"))
    names = [os.path.basename(x["path"]) for x in r["outputs"]]
    assert names == ["FFIX-PS1-Save-01-FILE01.mcs", "FFIX-PS1-Save-02-FILE02.mcs"]
    for x, a in zip(r["outputs"], r["plan"].assignments):
        assert ps1_card.parse_file(open(x["path"], "rb").read())[0] == "mcs-single"
        assert service.verify_files(pc6, x["path"], a.id)["counts"]["unexpected"] == 0
    with pytest.raises(service.UserError, match="card format"):
        batch.prepare(batch.BatchOptions(pc6, into=str(tmp_path / "x.mcr"), format="mcs"))


def big_pc(tmp_path):
    """A PC file with 28 saves (both user cards: slot 1 files 1-15 and slot 2 files 1-13)."""
    out = str(tmp_path / "big" / "SavedData_ww.dat")
    batch.run(batch.BatchOptions(card(15), out=out, timestamp=TS))
    batch.run(batch.BatchOptions(card(13), into=out, in_place=True, timestamp=TS))
    return out


def test_more_than_fifteen_saves_split_across_cards(tmp_path):
    src = big_pc(tmp_path)
    folder = str(tmp_path / "split")
    r = batch.run(batch.BatchOptions(src, out=folder))
    names = [os.path.basename(x["path"]) for x in r["outputs"]]
    assert names == ["FFIX-PS1-Card-01.mcr", "FFIX-PS1-Card-02.mcr"]
    counts = [len(ps1_card.parse_file(open(x["path"], "rb").read())[1]) for x in r["outputs"]]
    assert counts == [15, 13]
    labels = [a.dest_label for a in r["plan"].assignments]
    assert labels[0] == "Card 01, FILE01" and labels[14] == "Card 01, FILE15" and labels[15] == "Card 02, FILE01"
    man = json.load(open(os.path.join(folder, "conversion-manifest.json"), encoding="utf-8"))
    assert [s["destination"] for s in man["saves"]] == labels and len(man["outputs"]) == 2


def test_existing_card_renumbers_clashing_files_and_keeps_other_blocks(pc6, card13, tmp_path):
    before = open(card13, "rb").read()
    r = batch.run(batch.BatchOptions(pc6, select=["2/1", "2/2"], into=card13))
    out = r["outputs"][0]["path"]
    assert open(card13, "rb").read() == before                           # copy mode: the card is not changed
    after = open(out, "rb").read()
    for b in range(1, 14):
        assert after[b * 0x80:(b + 1) * 0x80] == before[b * 0x80:(b + 1) * 0x80]
        assert after[b * 0x2000:(b + 1) * 0x2000] == before[b * 0x2000:(b + 1) * 0x2000]
    assert [a.file for a in r["plan"].assignments] == [14, 15]
    assert all("already used" in a.note for a in r["plan"].assignments)


def test_existing_card_capacity(pc6, card13, tmp_path):
    plan = batch.prepare(batch.BatchOptions(pc6, select=["2/1", "2/2", "2/3"], into=card13))
    assert not plan.ok and any("room for 2" in p for p in plan.problems)
    plan = batch.prepare(batch.BatchOptions(pc6, select=["2/1", "2/2", "2/3"], into=card13,
                                            mapping={"2/1": "1/1", "2/2": "1/2", "2/3": "1/3"}))
    assert plan.ok and plan.needs_approval and len(plan.replacements) == 3


def test_existing_card_replace_in_place(pc6, card13, tmp_path):
    before = sha(card13)
    o = batch.BatchOptions(pc6, select=["2/1"], into=card13, in_place=True, mapping={"2/1": "1/2"}, replace=True)
    r = batch.run(o)
    assert sha(r["outputs"][0]["backup"]) == before
    info = service.destination_slots(card13)
    assert sorted(info["ff9_files"]) == list(range(1, 14))
    rows = {int(x["id"]): x for x in service.list_saves(card13)[1]}
    assert rows[2]["location"] == r["plan"].assignments[0].summary["location"]


# ---- Memoria ---------------------------------------------------------------------------------------
def test_memoria_sidecars_judged_per_save(tmp_path):
    src = memoria_copy(tmp_path, "sidecar_cases")
    plan = batch.prepare(batch.BatchOptions(src, out=str(tmp_path / "m")))
    st = {a.id: a.memoria for a in plan.assignments}
    assert st == {"1/1": "valid", "1/2": "valid", "1/3": "stale", "1/4": "corrupt", "1/5": "untimed"}
    assert not plan.ok and [a.id for a in plan.assignments if a.problem] == ["1/4"]
    assert plan.assignments[3].problem_kind == "memoria-damaged"
    # leaving the damaged one out, every other save converts with its sidecar applied exactly as single conversion does
    r = batch.run(batch.BatchOptions(src, select=["1/1", "1/2", "1/3", "1/5"], out=str(tmp_path / "m2")))
    cardp = r["outputs"][0]["path"]
    for a in r["plan"].assignments:
        single = service.convert_file(service.ConvertOptions(input=src, source=a.id, dest=str(a.file)), dry_run=True)
        assert single["model"]["event"] == a.model["event"] and single["model"]["players"] == a.model["players"]
        _, entries = ps1_card.parse_file(open(cardp, "rb").read())
        blk = [e.block_index for e in entries if service.ps1_file_number(e.filename) == a.file][0]
        assert service.verify_files(src, cardp, a.id, str(blk))["counts"]["unexpected"] == 0


def test_memoria_lossy_is_explicit(tmp_path):
    src = memoria_copy(tmp_path, "sidecar_cases")
    r = batch.run(batch.BatchOptions(src, out=str(tmp_path / "m"), allow_lossy=True))
    a = [x for x in r["plan"].assignments if x.id == "1/4"][0]
    assert a.report["memoria"]["lossy"]
    man = json.load(open(r["report_path"], encoding="utf-8"))
    assert man["options"]["allow_lossy"] is True


def test_memoria_multi_file_moguri(tmp_path):
    src = memoria_copy(tmp_path, "moguri_style")
    plan = batch.prepare(batch.BatchOptions(src, out=str(tmp_path / "m")))
    with_sidecar = [a for a in plan.assignments if a.memoria == "valid"]
    assert len(with_sidecar) == 2
    for a in with_sidecar:
        assert a.report["memoria"]["taken_from_sidecar"] or a.report["memoria"]["sidecar_status"] == "valid"


def test_ps1_into_memoria_container_refuses_live_sidecar(card13, tmp_path):
    """Memoria applies an untimed (or unreadable) sidecar whatever the save's play time, so it would load over a
    converted save written into that slot; a timed one whose play time differs is ignored by Memoria (a warning)."""
    src = memoria_copy(tmp_path, "sidecar_cases")
    before = sha(src)
    plan = batch.prepare(batch.BatchOptions(card13, select=["1", "2", "3", "4", "5"], into=src, in_place=True,
                                            pc_slot=1, replace=True, timestamp=TS))
    kinds = {a.dest_label: a.problem_kind for a in plan.assignments}
    assert kinds["Slot 1, file 5"] == "memoria-overlay" and kinds["Slot 1, file 4"] == "memoria-overlay"
    assert kinds["Slot 1, file 1"] is None and plan.assignments[0].warnings              # stale for the new save
    assert not plan.ok
    with pytest.raises(service.UserError):
        batch.commit(plan)
    assert sha(src) == before


# ---- transaction safety --------------------------------------------------------------------------
def test_write_failure_rolls_back_every_file(pc6, card13, tmp_path, monkeypatch):
    big = big_pc(tmp_path)
    folder = str(tmp_path / "fail")
    real = safeio._place
    calls = []

    def flaky(tmp, dest, replace):
        calls.append(dest)
        if len(calls) == 2:
            raise OSError("disk full (simulated)")
        return real(tmp, dest, replace)
    monkeypatch.setattr(safeio, "_place", flaky)
    with pytest.raises(safeio.SafetyError, match="put back"):
        batch.run(batch.BatchOptions(big, out=folder))
    assert not os.path.exists(folder)                                     # first card removed, folder removed


def test_in_place_failure_restores_original(card13, pc6, monkeypatch):
    before = sha(pc6)
    real = safeio._place
    calls = []

    def flaky(tmp, dest, replace):
        calls.append(dest)
        real(tmp, dest, replace)
        if len(calls) == 2:                                              # after the save file AND the report moved
            raise OSError("simulated failure")
    monkeypatch.setattr(safeio, "_place", flaky)
    with pytest.raises(safeio.SafetyError, match="put back"):
        batch.run(batch.BatchOptions(card13, into=pc6, in_place=True, timestamp=TS))
    assert sha(pc6) == before
    assert files_in(os.path.dirname(pc6)) == ["SavedData_ww.dat"]           # no report, backup or journal left


def test_crash_leaves_journal_that_recover_undoes(card13, pc6, tmp_path, monkeypatch):
    before = sha(pc6)
    real = safeio._place
    calls = []

    def crash(tmp, dest, replace):
        calls.append(dest)
        real(tmp, dest, replace)
        if len(calls) == 1:
            raise KeyboardInterrupt                                       # the process "dies" after one move
    monkeypatch.setattr(safeio, "_place", crash)
    monkeypatch.setattr(safeio, "_undo", lambda entries, done: ["simulated crash: nothing undone"])
    with pytest.raises(safeio.SafetyError, match="NOT be fully undone"):
        batch.run(batch.BatchOptions(card13, into=pc6, in_place=True, timestamp=TS))
    monkeypatch.undo()
    assert sha(pc6) != before
    folder = os.path.dirname(pc6)
    assert safeio.find_journals(folder)
    plan = batch.prepare(batch.BatchOptions(card13, into=pc6, in_place=True, timestamp=TS))
    assert not plan.ok and any("interrupted" in p for p in plan.problems)
    res = batch.recover(folder)
    assert res and not res[0][1]["problems"] and res[0][1]["restored"]
    assert sha(pc6) == before and not safeio.find_journals(folder)
    left = files_in(folder)
    assert [n for n in left if not n.startswith("SavedData_ww.dat.bak-")] == ["SavedData_ww.dat"]


def test_cancel_before_writing(card15, tmp_path):
    out = str(tmp_path / "c" / "SavedData_ww.dat")
    n = []

    def cancel():
        n.append(1)
        return len(n) > 5
    with pytest.raises(batch.Cancelled):
        batch.prepare(batch.BatchOptions(card15, out=out), cancel=cancel)
    plan = batch.prepare(batch.BatchOptions(card15, out=out, timestamp=TS))
    with pytest.raises(safeio.Cancelled):
        batch.commit(plan, cancel=lambda: True)
    assert not os.path.exists(os.path.dirname(out))


def test_cancel_during_commit_undoes(tmp_path, monkeypatch):
    big = big_pc(tmp_path)
    folder = str(tmp_path / "cx")
    plan = batch.prepare(batch.BatchOptions(big, out=folder))
    real = safeio._place
    moved = []

    def track(tmp, dest, replace):
        moved.append(dest)
        real(tmp, dest, replace)
    monkeypatch.setattr(safeio, "_place", track)
    with pytest.raises(safeio.Cancelled, match="put back"):
        batch.commit(plan, cancel=lambda: len(moved) >= 1)
    assert moved and not os.path.exists(folder)


def test_verification_failure_writes_nothing(card15, tmp_path, monkeypatch):
    real = verify.compare

    def bad(a, b):
        f = real(a, b)
        f.append({"field": "simulated", "status": "unexpected", "source": 1, "converted": 2, "note": ""})
        return f
    monkeypatch.setattr(verify, "compare", bad)
    out = str(tmp_path / "v" / "SavedData_ww.dat")
    plan = batch.prepare(batch.BatchOptions(card15, out=out, timestamp=TS))
    assert not plan.ok and all(a.problem_kind == "verify" for a in plan.assignments)
    with pytest.raises(service.UserError):
        batch.commit(plan)
    assert not os.path.exists(os.path.dirname(out))


def test_destination_changed_after_review(card13, pc6):
    plan = batch.prepare(batch.BatchOptions(card13, into=pc6, in_place=True, timestamp=TS))
    raw = bytearray(open(pc6, "rb").read())
    raw[-1] ^= 1
    open(pc6, "wb").write(raw)
    changed = sha(pc6)
    with pytest.raises(safeio.SafetyError, match="changed since"):
        batch.commit(plan)
    assert sha(pc6) == changed


def test_new_output_must_not_exist(card15, tmp_path):
    out = tmp_path / "exists" / "SavedData_ww.dat"
    out.parent.mkdir()
    out.write_bytes(b"x")
    plan = batch.prepare(batch.BatchOptions(card15, out=str(out)))
    assert not plan.ok and any("already exists" in p for p in plan.problems)


def test_never_writes_source_or_cloud(card15, pc6, tmp_path):
    with pytest.raises(safeio.SafetyError):
        batch.prepare(batch.BatchOptions(pc6, into=pc6, in_place=True))
    cloud = tmp_path / "Steam" / "userdata" / "123" / "377840" / "remote"
    with pytest.raises(service.UserError, match="Steam Cloud"):
        batch.prepare(batch.BatchOptions(card15, out=str(cloud / "SavedData_ww.dat")))


def test_transaction_unit(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "sub" / "b.bin"
    a.write_bytes(b"old")
    tx = safeio.Transaction()
    tx.add(a, b"new-a", replace=True, expected_sha256=hashlib.sha256(b"old").hexdigest())
    tx.add(b, lambda backups: f"backup={os.path.basename(backups[str(a)])}".encode(), create_dir=True)
    res = tx.commit()
    assert a.read_bytes() == b"new-a" and b.read_bytes().startswith(b"backup=a.bin.bak-")
    assert open(res[0]["backup"], "rb").read() == b"old" and not safeio.find_journals(tmp_path)
    tx = safeio.Transaction()
    tx.add(a, b"x")                                                      # exists, replace not allowed
    with pytest.raises(safeio.SafetyError, match="already exists"):
        tx.commit()
    tx = safeio.Transaction()
    tx.add(a, b"1", replace=True)
    tx.add(a, b"2", replace=True)
    with pytest.raises(safeio.SafetyError, match="twice"):
        tx.commit()


# ---- CLI ---------------------------------------------------------------------------------------------
def run_cli(*args):
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}
    return subprocess.run([sys.executable, "-m", "ffix_conv", *map(str, args)], capture_output=True, text=True,
                          env=env, cwd=ROOT)


def test_cli_batch_matches_service(pc6, tmp_path):
    p = run_cli("batch", pc6, "--json", "--dry-run")
    assert p.returncode == 0, p.stderr
    j = json.loads(p.stdout[:p.stdout.rindex("}") + 1])
    plan = batch.prepare(batch.BatchOptions(pc6))
    assert [s["destination"] for s in j["saves"]] == [a.dest_label for a in plan.assignments]
    folder = tmp_path / "cli_cards"
    p = run_cli("batch", pc6, "--select", "2/1", "4/1", "--out", folder)
    assert p.returncode == 0, p.stderr
    assert files_in(folder) == ["FFIX-PS1-Card-01.mcr", "conversion-manifest.json", "conversion-manifest.txt"]


def test_cli_batch_refusals(card13, pc6, tmp_path):
    p = run_cli("batch", card13, "--into", pc6, "--in-place")
    assert p.returncode == 2 and "--force" in p.stderr
    p = run_cli("batch", card13, "--into", pc6, "--in-place", "--force", "--slot", "2")
    assert p.returncode == 2 and "approve" in p.stderr
    p = run_cli("batch", pc6, "--select", "9/9")
    assert p.returncode == 2 and "no save 9/9" in p.stderr


def test_cli_recover(tmp_path):
    p = run_cli("recover", tmp_path)
    assert p.returncode == 0 and "no interrupted" in p.stdout
