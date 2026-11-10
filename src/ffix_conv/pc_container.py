"""SavedData_ww.dat container used by the vanilla 2016 PC release.

Layout (Memoria SharedDataBytesStorage.MetaData; sizes in bytes):
    0x000000  metadata, AES(288 plaintext) -> 304, reserved 320
    0x000140  150 previews (slot*15 + save), AES(965) -> 976, reserved 1024 each
    0x025940  autosave block, AES(17970) -> 17984, reserved 18432
    0x025940 + 18432*(1 + slot*15 + save)   save blocks
    total 2,937,152
Unused bytes inside each reserved area are whatever the game left there; they
are preserved untouched on rewrite. Slots/saves are 0-based here (the game UI
shows them 1-based).
"""
import struct
from dataclasses import dataclass, field

from . import pc_crypto, pc_schema

META_RESERVED = 320
META_PLAIN = 288
PREVIEW_RESERVED = 1024
PREVIEW_PLAIN = 965
BLOCK_RESERVED = 18432
SLOT_COUNT = 10
SAVE_COUNT = 15
TOTAL_SAVES = SLOT_COUNT * SAVE_COUNT
BASE_BLOCK = META_RESERVED + TOTAL_SAVES * PREVIEW_RESERVED
CONTAINER_SIZE = BASE_BLOCK + BLOCK_RESERVED * (1 + TOTAL_SAVES)
AUTOSAVE = "auto"


class ContainerError(ValueError):
    pass


def block_offset(slot, save):
    if slot == AUTOSAVE:
        return BASE_BLOCK
    _check(slot, save)
    return BASE_BLOCK + BLOCK_RESERVED * (1 + slot * SAVE_COUNT + save)


def preview_offset(slot, save):
    _check(slot, save)
    return META_RESERVED + PREVIEW_RESERVED * (slot * SAVE_COUNT + save)


def _check(slot, save):
    if not (0 <= slot < SLOT_COUNT and 0 <= save < SAVE_COUNT):
        raise ContainerError(f"slot/save out of range: {slot}/{save}")


@dataclass
class Metadata:
    save_version: float
    data_size: int
    latest_slot: int
    latest_save: int
    latest_timestamp: float
    game_finished: int
    language: int
    auto_login: int
    achievement_status: int
    screen_rotation: int
    reserved: bytes = field(repr=False, default=b"")

    FMT = "<4sfiiidiibBB"

    @classmethod
    def parse(cls, plain):
        if len(plain) != META_PLAIN or plain[:4] != b"SAVE":
            raise ContainerError("metadata header is not 'SAVE' (wrong key, modded encryption or corrupt file)")
        v = struct.unpack_from(cls.FMT, plain)
        return cls(*v[1:], reserved=plain[struct.calcsize(cls.FMT):])

    def build(self):
        head = struct.pack(self.FMT, b"SAVE", self.save_version, self.data_size, self.latest_slot,
                           self.latest_save, self.latest_timestamp, self.game_finished, self.language,
                           self.auto_login, self.achievement_status, self.screen_rotation)
        return head + self.reserved


@dataclass
class Preview:
    has_data: bool
    gil: int
    play_seconds: int
    win_type: int
    location: str
    party: list            # [(serial_id, level, name) or None] * 4
    timestamp: float
    reserved: bytes = field(repr=False, default=bytes(256))

    @classmethod
    def parse(cls, plain):
        if plain[:4] == b"NONE":
            return None
        if plain[:4] != b"PREV" or len(plain) != PREVIEW_PLAIN:
            raise ContainerError(f"preview header {plain[:4]!r} unexpected")
        o = 4
        has_data, gil, dur, win = struct.unpack_from("<?qQQ", plain, o); o += 25
        loc = pc_schema.string_value(plain[o:o + 128]); o += 128
        party = []
        for _ in range(4):
            sid, lvl = struct.unpack_from("<ii", plain, o); o += 8
            name = pc_schema.string_value(plain[o:o + 128]); o += 128
            party.append(None if (sid, lvl) == (-1, -1) else (sid, lvl, name))
        ts, = struct.unpack_from("<d", plain, o); o += 8
        return cls(has_data, gil, dur, win, loc, party, ts, plain[o:o + 256])

    def build(self):
        b = bytearray(b"PREV")
        b += struct.pack("<?qQQ", self.has_data, self.gil, self.play_seconds, self.win_type)
        b += pc_schema.string_bytes(self.location, 128)
        for m in self.party:
            sid, lvl, name = m if m else (-1, -1, "")
            b += struct.pack("<ii", sid, lvl) + pc_schema.string_bytes(name, 128)
        b += struct.pack("<d", self.timestamp) + self.reserved
        assert len(b) == PREVIEW_PLAIN
        return bytes(b)


class Container:
    """In-memory view of a SavedData_ww.dat. Never writes to disk by itself."""

    def __init__(self, raw):
        if len(raw) != CONTAINER_SIZE:
            raise ContainerError(f"size {len(raw)} is not the vanilla container size {CONTAINER_SIZE}")
        self.raw = bytearray(raw)
        try:
            plain = pc_crypto.decrypt(bytes(raw[:pc_crypto.cipher_size(META_PLAIN)]))
        except pc_crypto.DecryptError as e:
            raise ContainerError(f"metadata did not decrypt: {e}") from e
        self.meta = Metadata.parse(plain)
        if self.meta.data_size != pc_schema.DATA_SIZE:
            raise ContainerError(f"unsupported slot data size {self.meta.data_size} "
                                 f"(vanilla is {pc_schema.DATA_SIZE}); modded or newer format")

    # ---- low level -------------------------------------------------------
    def _read_section(self, off, plain_size):
        n = pc_crypto.cipher_size(plain_size)
        return pc_crypto.decrypt(bytes(self.raw[off:off + n]))

    def _write_section(self, off, plain, reserved):
        c = pc_crypto.encrypt(plain)
        if len(c) > reserved:
            raise ContainerError("encrypted section exceeds reserved size")
        self.raw[off:off + len(c)] = c

    # ---- previews / slots ------------------------------------------------
    def preview(self, slot, save):
        return Preview.parse(self._read_section(preview_offset(slot, save), PREVIEW_PLAIN))

    def slot_plain(self, slot, save):
        """Return decrypted payload (without 'SAVE') or None if the block is empty ('NONE')."""
        plain = self._read_section(block_offset(slot, save), pc_schema.SLOT_PLAIN_SIZE)
        if plain[:4] == b"NONE":
            return None
        if plain[:4] != b"SAVE" or len(plain) != pc_schema.SLOT_PLAIN_SIZE:
            raise ContainerError(f"slot {slot}/{save}: bad header {plain[:4]!r} or size {len(plain)}")
        return plain[4:]

    def slot_tree(self, slot, save):
        p = self.slot_plain(slot, save)
        return None if p is None else pc_schema.decode(p)

    def occupied(self):
        out = []
        for slot in range(SLOT_COUNT):
            for save in range(SAVE_COUNT):
                if self.slot_plain(slot, save) is not None:
                    out.append((slot, save))
        return out

    def put_slot(self, slot, save, tree, preview):
        self._write_section(block_offset(slot, save), b"SAVE" + pc_schema.encode(tree), BLOCK_RESERVED)
        self._write_section(preview_offset(slot, save), preview.build(), PREVIEW_RESERVED)

    def set_metadata(self, meta):
        self.meta = meta
        self._write_section(0, meta.build(), META_RESERVED)

    def to_bytes(self):
        return bytes(self.raw)
