"""PC container: crypto, layout, schema and lossless round trips."""
import pytest
from conftest import load_pc, pc_files, pcf

from ffix_conv import convert, pc_container, pc_crypto, pc_schema


def test_schema_size_matches_metadata():
    assert pc_schema.SCHEMA_SIZE == pc_schema.DATA_SIZE == 17966
    assert pc_container.CONTAINER_SIZE == 2937152


def test_known_offsets_match_independent_documentation():
    # ffix-save-editor (MIT) documents these offsets inside the decrypted slot (including "SAVE")
    off = lambda *p: pc_schema.OFFSETS[("Data",) + p][1] + 4
    assert off("40000_Common", "gil") == 0x1473
    assert off("40000_Common", "items", 0, "count") == 0x1477
    assert off("40000_Common", "players", 0, "name") == 0x1677 + 0x39
    assert off("40000_Common", "slot", 0) == 0x1F4B
    assert off("30000_MiniGame", "sDraw") == 0x1467
    assert off("95000_Setting", "00001_time") == 0x3832


def test_crypto_round_trip_and_bad_padding():
    for n in (0, 1, 15, 16, 288, 965, 17970):
        p = bytes(range(256)) * (n // 256) + bytes(n % 256)
        c = pc_crypto.encrypt(p)
        assert len(c) == pc_crypto.cipher_size(n)
        assert pc_crypto.decrypt(c) == p
    with pytest.raises(pc_crypto.DecryptError):
        pc_crypto.decrypt(bytes(32))
    with pytest.raises(pc_crypto.DecryptError):
        pc_crypto.decrypt(bytes(15))


@pytest.mark.parametrize("path", pc_files() or [None])
def test_container_round_trip_is_byte_identical(path):
    if path is None:
        pytest.skip("PC fixtures not present")
    raw = open(path, "rb").read()
    c = pc_container.Container(raw)
    occ = c.occupied()
    assert occ
    for slot, save in occ:
        tree = c.slot_tree(slot, save)
        assert pc_schema.encode(tree) == c.slot_plain(slot, save)
        c.put_slot(slot, save, tree, c.preview(slot, save))
        assert c.preview(slot, save).build() == pc_crypto.decrypt(
            raw[pc_container.preview_offset(slot, save):][:pc_crypto.cipher_size(965)])
    c.set_metadata(c.meta)
    assert c.to_bytes() == raw


def test_blank_container_matches_game_empty_sections():
    real = open(pcf("steam_jumprope_a_SavedData_ww.dat"), "rb").read()
    b = convert.blank_container()
    for slot, save in [(0, 1), (5, 5), (9, 14)]:
        po, bo = pc_container.preview_offset(slot, save), pc_container.block_offset(slot, save)
        assert b.raw[po:po + 1024] == real[po:po + 1024]
        assert b.raw[bo:bo + 18432] == real[bo:bo + 18432]
    assert b.occupied() == []


def test_insert_preserves_unrelated_slots_and_refuses_overwrite():
    path = pcf("steam_cd3thread_SavedData_ww.dat")
    raw = open(path, "rb").read()
    c = pc_container.Container(raw)
    tree = c.slot_tree(0, 0)
    with pytest.raises(convert.ConversionError):
        convert.insert(c, 1, 0, tree, c.preview(0, 0))       # occupied
    convert.insert(c, 9, 14, tree, c.preview(0, 0))
    out = c.to_bytes()
    lo, hi = pc_container.block_offset(9, 14), pc_container.block_offset(9, 14) + 18432
    plo, phi = pc_container.preview_offset(9, 14), pc_container.preview_offset(9, 14) + 1024
    changed = [i for i in range(0, len(raw), 16) if out[i:i + 16] != raw[i:i + 16]]
    assert all(lo <= i < hi or plo <= i < phi or i < 320 for i in changed)
    assert pc_container.Container(out).occupied() == c.occupied()
    assert open(path, "rb").read() == raw


@pytest.mark.parametrize("mutate,err", [
    (lambda r: r[:-1], "size"),
    (lambda r: bytes(16) + r[16:], "metadata"),
    (lambda r: pc_crypto.encrypt(b"XXXX" + bytes(284)) + r[304:], "SAVE"),
])
def test_invalid_containers_rejected(mutate, err):
    raw = open(pcf("steam_jumprope_a_SavedData_ww.dat"), "rb").read()
    with pytest.raises(pc_container.ContainerError):
        pc_container.Container(mutate(raw))


def test_wrong_data_size_metadata_rejected():
    raw = bytearray(open(pcf("steam_jumprope_a_SavedData_ww.dat"), "rb").read())
    c = pc_container.Container(bytes(raw))
    meta = c.meta
    meta.data_size = 20000
    enc = pc_crypto.encrypt(meta.build())
    raw[:len(enc)] = enc
    with pytest.raises(pc_container.ContainerError, match="data size"):
        pc_container.Container(bytes(raw))


def test_corrupt_slot_ciphertext_raises():
    raw = bytearray(open(pcf("steam_jumprope_a_SavedData_ww.dat"), "rb").read())
    o = pc_container.block_offset(0, 0) + 17984 - 1
    raw[o] ^= 0xFF
    c = pc_container.Container(bytes(raw))
    with pytest.raises((pc_crypto.DecryptError, pc_container.ContainerError)):
        c.slot_plain(0, 0)


def test_slot_range_checked():
    c = load_pc(pcf("steam_jumprope_a_SavedData_ww.dat"))
    with pytest.raises(pc_container.ContainerError):
        c.slot_plain(10, 0)
    with pytest.raises(pc_container.ContainerError):
        c.slot_plain(0, 15)
