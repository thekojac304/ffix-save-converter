"""PS1 memory-card detection, extraction and FF9 block parsing."""
import struct

import pytest
from conftest import fa, load_ps1, ps1_files

from ffix_conv import ps1_card, ps1_save


def test_corpus_present_and_complete():
    files = ps1_files()
    if not files:
        pytest.skip("PS1 fixtures not present")
    assert len(files) == 54


@pytest.mark.parametrize("path", ps1_files() or [None])
def test_every_fixture_parses_with_valid_crc(path):
    if path is None:
        pytest.skip("PS1 fixtures not present")
    raw = open(path, "rb").read()
    kind, entries = ps1_card.parse_file(raw)
    assert kind == "raw-card" and len(entries) == 1
    e = entries[0]
    assert e.directory_ok and e.block_index == 1
    s = ps1_save.PS1Save(e.data, e.product_code, e.filename)
    assert s.region == ("NTSC-U", "en-US", 1)
    assert s.crc_ok
    assert s.block[ps1_save.BLOCK_USED:] == bytes(len(s.block) - ps1_save.BLOCK_USED)  # unused tail is zero
    p = s.preview()
    assert p["gil"] == s.party()["gil"]                                               # preview agrees with party
    party_levels = sorted(s.players()[i].fields()["level"] for i in s.party()["slot"] if i != 9)
    assert sorted(x["level"] for x in p["party"] if x) == party_levels
    assert open(path, "rb").read() == raw                                             # input untouched


def test_scenario_counter_is_monotonic_through_corpus():
    files = ps1_files()
    if not files:
        pytest.skip("PS1 fixtures not present")
    sc = [load_ps1(f).scenario_counter for f in files]
    assert sc == sorted(sc), "FantasyAnime saves are chronological; scenario counter must not decrease"
    assert sc[0] == 1155 and sc[-1] == 11770


def test_text_decoding():
    s = load_ps1(fa(1))
    names = [p.name for p in s.players()]
    assert names[:4] == ["Zidane", "??????", "Dagger", "Steiner"]
    assert s.preview()["location"] == "Alexandria/Steeple"


def test_player_info_bits_and_layout():
    s = load_ps1(fa(41))
    z, v, f = (s.players()[i].fields() for i in (0, 1, 4))
    assert (z["info"]["slot_no"], z["info"]["serial_no"]) == (0, 0)
    assert (v["info"]["slot_no"], v["info"]["serial_no"], v["info"]["menu_type"]) == (1, 2, 1)
    assert (f["info"]["slot_no"], f["info"]["serial_no"], f["info"]["menu_type"]) == (4, 12, 4)
    assert z["level"] == 41 and z["cur"]["hp"] <= z["max"]["hp"]


def test_cards_and_empty_marker():
    s = load_ps1(fa(1))
    cards = s.cards()
    assert len(cards) == ps1_save.CARD_SLOTS
    assert cards[0]["id"] == 0 and cards[1]["id"] == 1
    assert all(c["id"] == 0xFF for c in cards[100:])


# ---- container wrappers (SYNTHETIC: built from a real block for self-consistency only) ----
def _card_with(blocks):
    card = bytearray(ps1_card.CARD_SIZE)
    card[0:2] = b"MC"
    card[0x7F] = 0x0E
    for i in range(1, 16):
        fr = bytearray(0x80)
        if i <= len(blocks):
            struct.pack_into("<IIH", fr, 0, 0x51, 0x2000, 0xFFFF)
            fr[0x0A:0x1E] = b"BASLUS-0125100000-%02d" % (i - 1)
            card[i * 0x2000:(i + 1) * 0x2000] = blocks[i - 1]
        else:
            struct.pack_into("<IIH", fr, 0, 0xA0, 0, 0xFFFF)
        x = 0
        for b in fr[:0x7F]:
            x ^= b
        fr[0x7F] = x
        card[i * 0x80:(i + 1) * 0x80] = fr
    return bytes(card)


@pytest.fixture
def real_block():
    return load_ps1(fa(1)).block


def test_multiple_occupied_slots(real_block):
    other = load_ps1(fa(54)).block
    _, entries = ps1_card.parse_file(_card_with([real_block, other, real_block]))
    assert [e.block_index for e in entries] == [1, 2, 3]
    assert ps1_save.PS1Save(entries[1].data).scenario_counter == 11770


def test_wrappers_detected(real_block):
    card = _card_with([real_block])
    gme = b"123-456-STD" + bytes(3904 - 11) + card
    vgs = b"VgsM" + bytes(60) + card
    vmp = b"\x00PMV" + bytes(0x7C) + card
    fr = card[0x80:0x100]
    mcs = fr + real_block
    psv = bytearray(0x84 + 0x2000)
    psv[0:4] = b"\x00VSP"
    struct.pack_into("<I", psv, 0x40, 0x2000)
    psv[0x64:0x78] = b"BASLUS-0125100000-00"
    psv[0x84:] = real_block
    for raw, kind in [(gme, "dexdrive-gme"), (vgs, "vgs"), (vmp, "psp-vmp"), (mcs, "mcs-single"),
                      (bytes(psv), "ps3-psv"), (real_block, "raw-block")]:
        k, entries = ps1_card.parse_file(raw)
        assert k == kind
        assert entries[0].data[:ps1_save.BLOCK_USED] == real_block[:ps1_save.BLOCK_USED]


# ---- malformed input ------------------------------------------------------------
def test_corrupt_card_header(real_block):
    card = bytearray(_card_with([real_block]))
    card[0:2] = b"XX"
    with pytest.raises(ps1_card.CardError):
        ps1_card.parse_file(bytes(card))


def test_truncated_inputs(real_block):
    card = _card_with([real_block])
    for n in (0, 10, 0x2000 - 1, len(card) - 1):
        with pytest.raises((ps1_card.CardError, ValueError)):
            k, e = ps1_card.parse_file(card[:n])
            ps1_save.PS1Save(e[0].data)
    with pytest.raises(ValueError):
        ps1_save.PS1Save(real_block[:0x1000])


def test_invalid_directory_entry_is_flagged(real_block):
    card = bytearray(_card_with([real_block]))
    card[0x80 + 0x20] ^= 0xFF     # corrupt directory frame without fixing its XOR
    _, entries = ps1_card.parse_file(bytes(card))
    assert entries[0].directory_ok is False


def test_empty_card_has_no_saves(real_block):
    _, entries = ps1_card.parse_file(_card_with([]))
    assert entries == []


def test_crc_mismatch_detected(real_block):
    b = bytearray(real_block)
    b[0x1C0 + 100] ^= 1
    assert not ps1_save.PS1Save(bytes(b)).crc_ok


def test_non_ff9_block_rejected():
    with pytest.raises(ValueError):
        ps1_save.PS1Save(bytes(0x2000))
