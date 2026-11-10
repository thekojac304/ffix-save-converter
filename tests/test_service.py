"""The service layer shared by the CLI and the GUI: options, dry runs, destinations, Steam Cloud refusal."""
import hashlib
import os
import shutil

import pytest

from conftest import fa, pcf
from ffix_conv import cli, ps1_card, service


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def test_options_defaults_match_cli():
    """The GUI's ConvertOptions must behave exactly like the CLI with no extra flags."""
    ns = cli.build_parser().parse_args(["convert", "x"])
    opts = service.ConvertOptions(input="x")
    for f in service.ConvertOptions.__dataclass_fields__:
        if f in ("create_dir",):
            continue
        assert getattr(opts, f) == getattr(ns, f), f


def test_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    before = set(os.listdir(tmp_path))
    r = service.convert_file(service.ConvertOptions(input=str(src)), dry_run=True)
    assert r["counts"]["unexpected"] == 0 and r["report_path"] is None
    assert set(os.listdir(tmp_path)) == before
    assert r["report"]["compatibility"]["fully_preserved"]


def test_dry_run_refuses_existing_output(tmp_path):
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    out = tmp_path / "exists.mcr"
    out.write_bytes(b"x")
    with pytest.raises(service.UserError, match="already exists"):
        service.convert_file(service.ConvertOptions(input=str(pcf("ff9SaveLib_testdata_SavedData_ww.dat")),
                                                    source="1/1", out=str(out)), dry_run=True)


def test_create_dir_for_new_output_folder(tmp_path):
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    out = tmp_path / "new folder" / "SavedData_ww.dat"
    r = service.convert_file(service.ConvertOptions(input=str(src), out=str(out), create_dir=True))
    assert os.path.exists(out) and r["counts"]["unexpected"] == 0


@pytest.mark.parametrize("name", ["FF9_CloudSaveFile_ww.sav", os.path.join("Steam", "userdata", "1", "377840", "remote", "x.dat")])
def test_cloud_targets_refused(tmp_path, name):
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    out = tmp_path / name
    for dry in (True, False):
        with pytest.raises(service.UserError, match="Steam Cloud"):
            service.convert_file(service.ConvertOptions(input=str(src), out=str(out), create_dir=True), dry_run=dry)
    assert not os.path.exists(out)


def test_cloud_target_refused_in_place(tmp_path):
    """Even an explicit, forced in-place update of the cloud file is refused, and the file is untouched."""
    cloud = tmp_path / "FF9_CloudSaveFile_ww.sav"
    shutil.copy(pcf("ff9SaveLib_testdata_SavedData_ww.dat"), cloud)
    h = sha(cloud)
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    with pytest.raises(service.UserError, match="Steam Cloud"):
        service.convert_file(service.ConvertOptions(input=str(src), into=str(cloud), in_place=True, force=True,
                                                    dest="5/5"))
    assert sha(cloud) == h


def test_cloud_file_is_still_readable_as_source(tmp_path):
    cloud = tmp_path / "FF9_CloudSaveFile_ww.sav"
    shutil.copy(pcf("ff9SaveLib_testdata_SavedData_ww.dat"), cloud)
    head, rows = service.list_saves(str(cloud))
    assert head["platform"] == "pc" and rows


def test_destination_slots_pc():
    info = service.destination_slots(pcf("ff9SaveLib_testdata_SavedData_ww.dat"))
    assert info["platform"] == "pc" and "1/1" in info["occupied"]


def test_destination_slots_ps1_card(tmp_path):
    card = fa(1)
    info = service.destination_slots(card)
    assert info["platform"] == "ps1"
    used = [b for b, (st, _) in ps1_card.directory(open(card, "rb").read()).items() if st not in ps1_card.FREE_STATES]
    assert sorted(set(info["occupied"]) | set(info["other_blocks"])) == sorted(used)
    assert set(info["free_blocks"]).isdisjoint(used)
    assert info["ff9_files"] and all(1 <= n <= 15 for n in info["ff9_files"])


def test_destination_slots_rejects_single_save_file(tmp_path):
    src = tmp_path / "card.mcr"
    shutil.copy(fa(1), src)
    r = service.convert_file(service.ConvertOptions(input=str(pcf("ff9SaveLib_testdata_SavedData_ww.dat")),
                                                    source="1/1", out=str(tmp_path / "x.mcs"), format="mcs"))
    with pytest.raises(service.UserError, match="raw 128 KB"):
        service.destination_slots(r["out"])


def test_explain_error():
    assert service.explain_error(service.UserError("nope")) == "nope"
    assert "permission denied" in service.explain_error(PermissionError(13, "x", "f.dat"))
    assert service.explain_error(ZeroDivisionError()) is None
