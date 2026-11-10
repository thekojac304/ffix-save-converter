import glob
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ffix_conv import model, pc_container, ps1_card, ps1_save  # noqa: E402

PS1_GLOB = os.path.join(ROOT, "fixtures/ps1/extracted/fantasyanime/*/*.mcr")
PC_DIR = os.path.join(ROOT, "fixtures/pc/originals")


def ps1_files():
    return sorted(glob.glob(PS1_GLOB))


USER_CARDS = os.path.join(ROOT, "fixtures/ps1/originals/user_retroarch")


def ps1_card_saves():
    """(card path, block index) for every FF9 save on the user's own multi-save cards."""
    out = []
    for f in sorted(glob.glob(os.path.join(USER_CARDS, "*.srm"))):
        _, entries = ps1_card.parse_file(open(f, "rb").read())
        out += [(f, e.block_index) for e in entries]
    return out


def load_ps1_block(path, block):
    _, entries = ps1_card.parse_file(open(path, "rb").read())
    e = [x for x in entries if x.block_index == block][0]
    return ps1_save.PS1Save(e.data, e.product_code, e.filename)


def pc_files():
    return sorted(glob.glob(os.path.join(PC_DIR, "*/*SavedData_ww.dat")))


def fa(n):
    """Path of FantasyAnime save number n (third-party fixture, not redistributed)."""
    m = glob.glob(os.path.join(ROOT, f"fixtures/ps1/extracted/fantasyanime/ff9save{n:02d}_*/*.mcr"))
    if not m:
        pytest.skip("FantasyAnime fixtures not present (run tools/acquire.py + tools/safe_extract.py)")
    return m[0]


def pcf(name):
    m = glob.glob(os.path.join(PC_DIR, "*", name))
    if not m:
        pytest.skip(f"PC fixture {name} not present")
    return m[0]


def load_ps1(path):
    _, entries = ps1_card.parse_file(open(path, "rb").read())
    e = entries[0]
    return ps1_save.PS1Save(e.data, e.product_code, e.filename)


def load_pc(path):
    return pc_container.Container(open(path, "rb").read())


@pytest.fixture
def steeple_pair():
    """Cross-platform checkpoint: scenario 1155, Alexandria/Steeple."""
    return model.from_ps1(load_ps1(fa(1))), model.from_pc(load_pc(pcf("steam_jumprope_b_SavedData_ww.dat")).slot_tree(0, 0))


@pytest.fixture
def gulug_pair():
    """Cross-platform checkpoint: scenario 9950 (Gulug)."""
    return model.from_ps1(load_ps1(fa(41))), model.from_pc(load_pc(pcf("ff9SaveLib_testdata_SavedData_ww.dat")).slot_tree(0, 0))
