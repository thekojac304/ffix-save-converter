"""Release hardening: safe writes, path aliasing, strict encoding, CLI behaviour, verify."""
import copy
import hashlib
import json
import os
import stat
import subprocess
import sys

import pytest
from conftest import ROOT, fa, load_pc, load_ps1, pcf

import ffix_conv  # noqa: E402
from ffix_conv import cli, convert, model, pc_container, pc_schema, ps1_card, safeio, verify

USER_CARD = os.path.join(ROOT, "fixtures/ps1/originals/user_retroarch/user_Final_Fantasy_IX.srm")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def run(*args):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    return subprocess.run([sys.executable, "-P", "-m", "ffix_conv", *map(str, args)], env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def ok(data):
    pass


# ---- safeio ------------------------------------------------------------------------------------
def test_write_output_refuses_existing_and_cleans_temp(tmp_path):
    d = tmp_path / "out.bin"
    d.write_bytes(b"original")
    with pytest.raises(safeio.SafetyError, match="refusing to overwrite"):
        safeio.write_output(str(d), b"new", ok)
    assert d.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["out.bin"]


def test_force_makes_verified_backup(tmp_path):
    d = tmp_path / "out.bin"
    d.write_bytes(b"original")
    res = safeio.write_output(str(d), b"new", ok, force=True)
    assert d.read_bytes() == b"new"
    assert open(res["backup"], "rb").read() == b"original"


def test_detects_destination_changed_since_read(tmp_path):
    d = tmp_path / "out.bin"
    d.write_bytes(b"changed by someone else")
    with pytest.raises(safeio.SafetyError, match="changed since it was read"):
        safeio.write_output(str(d), b"new", ok, force=True, expected_sha256=safeio.sha256(b"what we read"))
    assert d.read_bytes() == b"changed by someone else"


def test_read_only_destination_not_touched(tmp_path):
    d = tmp_path / "out.bin"
    d.write_bytes(b"original")
    os.chmod(d, stat.S_IREAD)
    try:
        with pytest.raises(safeio.SafetyError, match="read-only|permission"):
            safeio.write_output(str(d), b"new", ok, force=True)
        assert d.read_bytes() == b"original"
    finally:
        os.chmod(d, stat.S_IREAD | stat.S_IWRITE)


def test_validation_failure_writes_nothing(tmp_path):
    def bad(_):
        raise safeio.SafetyError("invalid")
    with pytest.raises(safeio.SafetyError):
        safeio.write_output(str(tmp_path / "x.bin"), b"data", bad)
    assert list(tmp_path.iterdir()) == []


def test_missing_folder_and_missing_source(tmp_path):
    with pytest.raises(safeio.SafetyError, match="folder does not exist"):
        safeio.write_output(str(tmp_path / "nope" / "x.bin"), b"d", ok)
    with pytest.raises(safeio.SafetyError, match="not found"):
        safeio.read_source(str(tmp_path / "missing.mcr"))
    with pytest.raises(safeio.SafetyError, match="folder"):
        safeio.read_source(str(tmp_path))


def test_aliases_are_detected(tmp_path):
    src = tmp_path / "a.mcr"
    src.write_bytes(b"x")
    assert safeio.same_file(str(src), str(tmp_path / "." / "a.mcr"))
    assert safeio.same_file(str(src), str(tmp_path / "A.MCR")) == (os.path.normcase("A") == os.path.normcase("a"))
    link = tmp_path / "hard.mcr"
    os.link(src, link)
    assert safeio.same_file(str(src), str(link))                     # hard link
    with pytest.raises(safeio.SafetyError, match="same file"):
        safeio.check_distinct(str(link), str(src))
    try:
        sym = tmp_path / "sym.mcr"
        os.symlink(src, sym)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this system")
    assert safeio.same_file(str(src), str(sym))


# ---- strict encoding / no silent truncation --------------------------------------------------------
def test_oversized_strings_are_rejected_not_truncated():
    with pytest.raises(ValueError):
        pc_schema.string_bytes("x" * 200, 128)
    tree = load_pc(pcf("steam_jumprope_a_SavedData_ww.dat")).slot_tree(0, 0)
    tree["Data"]["40000_Common"]["players"][0]["name"] = b"y" * 129
    with pytest.raises(ValueError, match="do not fit"):
        pc_schema.encode(tree)


def test_undecodable_ps1_name_blocks_conversion():
    m = model.from_ps1(load_ps1(fa(1)))
    m["players"][0]["name"] = "Zid\\xc3ne"
    m["players"][0]["name_fully_decoded"] = False
    with pytest.raises(convert.ConversionError, match="PS1 text table"):
        convert.to_pc_tree(copy.deepcopy(m))
    _, rep = convert.to_pc_tree(m, strict=False)
    assert any("PS1 text table" in w for w in rep.warnings)


# ---- CLI ---------------------------------------------------------------------------------------------
def test_version_and_help():
    r = run("--version")
    assert r.returncode == 0 and f"ffix-convert {ffix_conv.__version__}" in r.stdout
    assert run("--help").returncode == 0 and run("verify", "--help").returncode == 0


def test_inspect_json_lists_every_save():
    if not os.path.exists(USER_CARD):
        pytest.skip("user card not present")
    r = run("inspect", USER_CARD, "--json")
    data = json.loads(r.stdout)
    assert data["platform"] == "ps1" and len(data["saves"]) == 13
    assert data["saves"][-1]["location"] == "Bentini Heights" and data["saves"][-1]["disc"] == 2


@pytest.mark.parametrize("args,needle", [
    (("inspect", "missing.mcr"), "not found"),
    (("convert", "missing.mcr"), "not found"),
    (("inspect", "."), "folder"),
])
def test_clean_errors_exit_2(args, needle):
    r = run(*args)
    assert r.returncode == 2 and needle in r.stderr and "Traceback" not in r.stderr


def test_corrupt_and_unknown_inputs(tmp_path):
    junk = tmp_path / "junk.bin"
    junk.write_bytes(os.urandom(5000))
    r = run("inspect", junk)
    assert r.returncode == 2 and "not a recognised" in r.stderr
    pcbad = tmp_path / "bad.dat"
    pcbad.write_bytes(bytes(pc_container.CONTAINER_SIZE))
    r = run("inspect", pcbad)
    assert r.returncode == 2 and "PC save" in r.stderr and "Traceback" not in r.stderr
    raw = bytearray(open(fa(1), "rb").read())
    raw[0x2000 + 0x500] ^= 0xFF                                  # break the block CRC
    bad = tmp_path / "crc.mcr"
    bad.write_bytes(bytes(raw))
    r = run("convert", bad, "--out", tmp_path / "o.dat")
    assert r.returncode == 2 and "CRC" in r.stderr and not (tmp_path / "o.dat").exists()


def test_default_output_names_never_clobber(tmp_path):
    src = tmp_path / "card.mcr"
    src.write_bytes(open(fa(41), "rb").read())
    before = sha(src)
    assert run("convert", src).returncode == 0
    assert run("convert", src).returncode == 0
    assert (tmp_path / "card_converted_pc" / "SavedData_ww.dat").exists()
    assert (tmp_path / "card_converted_pc-2" / "SavedData_ww.dat").exists()
    pc = tmp_path / "card_converted_pc" / "SavedData_ww.dat"
    assert run("convert", pc).returncode == 0
    assert (tmp_path / "card_converted_pc" / "SavedData_ww_converted_ps1.mcr").exists()
    assert sha(src) == before


def test_in_place_requires_force_and_backs_up(tmp_path):
    card = tmp_path / "mine.mcr"
    card.write_bytes(open(fa(10), "rb").read())
    before = card.read_bytes()
    r = run("convert", pcf("ff9SaveLib_testdata_SavedData_ww.dat"), "--source", "1/1", "--into", card, "--in-place",
            "--dest", "2")
    assert r.returncode == 2 and "--force" in r.stderr and card.read_bytes() == before
    r = run("convert", pcf("ff9SaveLib_testdata_SavedData_ww.dat"), "--source", "1/1", "--into", card, "--in-place",
            "--force", "--dest", "2")
    assert r.returncode == 0, r.stderr
    backups = [p for p in tmp_path.iterdir() if ".bak-" in p.name]
    assert len(backups) == 1 and backups[0].read_bytes() == before
    after = card.read_bytes()
    assert after[0x80:0x100] == before[0x80:0x100] and after[0x2000:0x4000] == before[0x2000:0x4000]   # block 1 untouched
    assert len(ps1_card.parse_file(after)[1]) == 2


def test_in_place_pc_preserves_other_slots(tmp_path):
    dat = tmp_path / "SavedData_ww.dat"
    dat.write_bytes(open(pcf("steam_cd3thread_SavedData_ww.dat"), "rb").read())
    before = pc_container.Container(dat.read_bytes())
    r = run("convert", fa(41), "--into", dat, "--in-place", "--force", "--dest", "5/7")
    assert r.returncode == 0, r.stderr
    after = pc_container.Container(dat.read_bytes())
    assert after.occupied() == sorted(before.occupied() + [(4, 6)])
    for sl in before.occupied():
        assert after.slot_plain(*sl) == before.slot_plain(*sl)


def test_out_cannot_alias_input(tmp_path):
    src = tmp_path / "card.mcr"
    src.write_bytes(open(fa(1), "rb").read())
    link = tmp_path / "alias.mcr"
    os.link(src, link)
    r = run("convert", src, "--out", link, "--force")
    assert r.returncode == 2 and "same file" in r.stderr
    assert src.read_bytes() == open(fa(1), "rb").read()


def test_verify_detects_tampering(tmp_path):
    out = tmp_path / "SavedData_ww.dat"
    assert run("convert", fa(20), "--out", out).returncode == 0
    r = run("verify", fa(20), out)
    assert r.returncode == 0 and "0 unexpected" in r.stdout
    c = pc_container.Container(out.read_bytes())
    tree = c.slot_tree(0, 0)
    tree["Data"]["40000_Common"]["gil"] += 1
    c.put_slot(0, 0, tree, c.preview(0, 0))
    bad = tmp_path / "tampered.dat"
    bad.write_bytes(c.to_bytes())
    r = run("verify", fa(20), bad)
    assert r.returncode == 1 and "party.gil" in r.stdout


@pytest.mark.parametrize("n", [1, 15, 32, 49, 54])
def test_cli_round_trips_verify_clean(tmp_path, n):
    pc = tmp_path / "SavedData_ww.dat"
    ps1 = tmp_path / "back.mcr"
    assert run("convert", fa(n), "--out", pc).returncode == 0
    assert run("convert", pc, "--out", ps1).returncode == 0
    r = run("verify", fa(n), ps1)                                   # PS1 -> PC -> PS1
    assert r.returncode == 0, r.stdout
    pc2 = tmp_path / "again.dat"
    assert run("convert", ps1, "--out", pc2).returncode == 0
    r = run("verify", pc, pc2)                                      # PC -> PS1 -> PC
    assert r.returncode == 0, r.stdout


def test_compat_report_levels(tmp_path):
    out = tmp_path / "x.mcr"
    rep = tmp_path / "r.json"
    assert run("convert", pcf("ff9SaveLib_testdata_SavedData_ww.dat"), "--source", "1/1", "--out", out,
               "--report", rep).returncode == 0
    data = json.loads(rep.read_text())
    assert set(verify.SEVERITIES) <= set(data["compatibility"])
    assert data["compatibility"]["unsupported_or_lossy"] and data["verification"]["counts"]["unexpected"] == 0
    assert data["input"]["sha256"] == sha(pcf("ff9SaveLib_testdata_SavedData_ww.dat"))


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-only")
def test_junction_alias_is_detected(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    src = real / "card.mcr"
    src.write_bytes(open(fa(1), "rb").read())
    junction = tmp_path / "jn"
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(real)], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"could not create junction: {r.stdout} {r.stderr}")
    alias = junction / "card.mcr"
    assert safeio.same_file(str(src), str(alias))
    out = run("convert", src, "--out", alias, "--force")
    assert out.returncode == 2 and "same file" in out.stderr
    assert src.read_bytes() == open(fa(1), "rb").read()
