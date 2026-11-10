"""FF9 (PS1) save-block parser.

A FF9 save is one 8,192-byte memory-card block. Only 0x0000-0x13FF is used:
    0x0000-0x00FF  memory-card title frame + icon (standard PS1 header, "SC")
    0x0100-0x017F  menu preview (leader, location, playtime, gil, party preview)
    0x0180-0x01BF  FF9 state (mode, map/location numbers)
    0x01C0-0x09BF  gEventGlobal: 2,048 bytes of persistent event variables
    0x09C0-0x09CF  unknown (first u32 grows monotonically through the story)
    0x09D0-0x0EDF  9 x 144-byte PLAYER records
    0x0EE0-0x0EF1  party: slot[4], escape_no, summon_flag, gil, frog_no, steal_no, dragon_no
    0x0EF2-0x0F1F  unknown (46 bytes)
    0x0F20-0x111F  256 inventory entries (id, count)
    0x1120-0x115F  rare (key) item bitfield, 64 bytes
    0x1160-0x1177  unknown (24 bytes)
    0x1178-0x117D  Tetra Master wins / losses / draws (i16 each)
    0x117E-0x13F3  105 Tetra Master card records x 6 bytes
    0x13F4-0x13FD  unknown (10 bytes)
    0x13FE         CRC-16 (reflected poly 0x8408, init 0xFFFF) over 0x0000-0x13FD
Each mapped field below is tagged with the evidence used to establish it; see
docs/FIELD_MAPPING.md for the full matrix. All raw bytes remain available.
"""
import struct
from dataclasses import dataclass, field

BLOCK_USED = 0x1400
CRC_OFFSET = 0x13FE
GEVENT_OFFSET = 0x1C0
GEVENT_SIZE = 2048
PLAYER_OFFSET = 0x9D0
PLAYER_SIZE = 144
PLAYER_COUNT = 9
PARTY_NONE_PS1 = 9           # PS1 writes 9 for an empty party slot; PC writes 255
ITEM_OFFSET = 0xF20
RARE_OFFSET = 0x1120
CARD_STATS_OFFSET = 0x1178
CARD_OFFSET = 0x117E
CARD_SLOTS = 105
CARD_EMPTY = 0xFF

REGIONS = {
    "BASLUS-01251": ("NTSC-U", "en-US", 1), "BASLUS-01295": ("NTSC-U", "en-US", 2),
    "BASLUS-01296": ("NTSC-U", "en-US", 3), "BASLUS-01297": ("NTSC-U", "en-US", 4),
    "BISLPS-02000": ("NTSC-J", "ja", 1), "BISLPS-02001": ("NTSC-J", "ja", 2),
    "BISLPS-02002": ("NTSC-J", "ja", 3), "BISLPS-02003": ("NTSC-J", "ja", 4),
}
for _lang, _base in (("en-GB", "2965"), ("fr", "2966"), ("de", "2967"), ("it", "2968"), ("es", "2969")):
    for _d in range(4):
        REGIONS[f"BESLES-{_d}{_base}"] = ("PAL", _lang, _d + 1)

_CRC_TABLE = []
for _i in range(256):
    _v = _i
    for _ in range(8):
        _v = (_v >> 1) ^ 0x8408 if _v & 1 else _v >> 1
    _CRC_TABLE.append(_v)


def crc16(data):
    c = 0xFFFF
    for x in data:
        c = (c >> 8) ^ _CRC_TABLE[(c ^ x) & 0xFF]
    return c


# ---- PS1 text (Latin versions) -------------------------------------------
# Table credited to ffix-save-editor (MIT) LegacyTextCodec; verified on fixtures
# (e.g. "Zidane", "Dagger", "??????" for an unnamed Vivi, location strings).
_TEXT = {i: chr(ord("0") + i) for i in range(10)}
_TEXT.update({0x10 + i: chr(ord("A") + i) for i in range(26)})
_TEXT.update({0x30 + i: chr(ord("a") + i) for i in range(26)})
_TEXT.update({0x0A: "+", 0x0B: "-", 0x0C: "*", 0x0D: "=", 0x0E: "%", 0x0F: " ", 0x2A: "(", 0x2B: "!",
              0x2C: "?", 0x2D: "“", 0x2E: ":", 0x2F: ".", 0x4A: ")", 0x4B: ",", 0x4C: "/", 0x4D: "•",
              0x4E: "~", 0x4F: "&", 0x7E: "’", 0x7F: "”", 0x80: "_", 0xAD: "#", 0xAF: ";"})
_ACCENTS = "ÁÀÂÄÉÈÊËÍÌÎÏÓÒÔÖÚÙÛÜáàâäéèêëíìîïóòôöúùûüÇÑçñŒß"
_TEXT.update({0x50 + i: c for i, c in enumerate(_ACCENTS)})


_TEXT_REV = {c: b for b, c in _TEXT.items()}


class TextEncodeError(ValueError):
    pass


def encode_text(text, length):
    """PS1 text, 0xFF-terminated and 0xFF-padded (the game's own padding); errors on unknown characters."""
    out = []
    for ch in text:
        if ch not in _TEXT_REV:
            raise TextEncodeError(f"character {ch!r} in {text!r} has no PS1 (Latin) encoding")
        out.append(_TEXT_REV[ch])
    if len(out) > length:
        raise TextEncodeError(f"{text!r} is longer than {length} PS1 characters")
    return bytes(out) + bytes([0xFF]) * (length - len(out))


def decode_text(raw):
    """Returns (text, fully_decoded)."""
    out, ok = [], True
    for b in raw:
        if b == 0xFF:
            break
        c = _TEXT.get(b)
        if c is None:
            ok = False
            out.append(f"\\x{b:02x}")
        else:
            out.append(c)
    return "".join(out), ok


@dataclass
class PS1Player:
    raw: bytes
    name_raw: bytes = field(init=False)
    name: str = field(init=False)
    name_decoded: bool = field(init=False)

    def __post_init__(self):
        r = self.raw
        self.name_raw = r[0x00:0x0A]
        self.name, self.name_decoded = decode_text(self.name_raw)

    def u8(self, o): return self.raw[o]
    def i8(self, o): return struct.unpack_from("<b", self.raw, o)[0]
    def u16(self, o): return struct.unpack_from("<H", self.raw, o)[0]
    def i16(self, o): return struct.unpack_from("<h", self.raw, o)[0]
    def u32(self, o): return struct.unpack_from("<I", self.raw, o)[0]

    def fields(self):
        """Field values in PC JSON naming. Offsets relative to the 144-byte record."""
        return decode_player(self.raw)

    def unmapped(self):
        """Bytes not carried by any mapped field (offset -> raw hex)."""
        r = self.raw
        return {"0x22-0x23": r[0x22:0x24].hex(), "info.bits17-31": (struct.unpack_from("<I", r, 0x34)[0] >> 17),
                "0x48-0x57": r[0x48:0x58].hex()}


# ---- PLAYER record codec (shared by reader and writer) -------------------------------
# (path, offset, struct format). "info" is a packed u32 at +0x34, handled separately.
_STAT = [("hp", 0, "<H"), ("mp", 2, "<h"), ("at", 4, "<h"), ("at_coef", 6, "<b"), ("capa", 7, "<B")]
PLAYER_LAYOUT = (
    [(("category",), 0x0A, "<B"), (("level",), 0x0B, "<B"), (("exp",), 0x0C, "<I")]
    + [(("cur", k), 0x10 + o, f) for k, o, f in _STAT] + [(("max", k), 0x18 + o, f) for k, o, f in _STAT]
    + [(("trance",), 0x20, "<B"), (("web_bone",), 0x21, "<B")]
    + [(("elem", k), 0x24 + i, "<B") for i, k in enumerate(("dex", "str", "mgc", "wpr"))]
    + [(("defence", k), 0x28 + i, "<B") for i, k in enumerate(("p_def", "p_ev", "m_def", "m_ev"))]
    + [(("basis", "max_hp"), 0x2C, "<h"), (("basis", "max_mp"), 0x2E, "<h")]
    + [(("basis", k), 0x30 + i, "<B") for i, k in enumerate(("dex", "str", "mgc", "wpr"))]
    + [(("status",), 0x38, "<B")] + [(("equip", i), 0x39 + i, "<B") for i in range(5)]
    + [(("bonus", k), 0x3E + 2 * i, "<H") for i, k in enumerate(("dex", "str", "mgc", "wpr"))]
    + [(("bonus_cap",), 0x46, "<H")]
    + [(("pa", i), 0x58 + i, "<B") for i in range(48)] + [(("sa", i), 0x88 + 4 * i, "<I") for i in range(2)]
)
# info u32 at +0x34: bits 0-3 slot_no, 4-8 serial_no, 9 row, 10 win_pose, 11 party, 12-16 menu_type.
# Verified on all 54 PS1 fixtures against PC values (Blank serial 16, Beatrix 18, early
# Cinna/Marcus/Blank menu_type 17/18/19); bits 17-31 are zero in every fixture.
INFO_BITS = [("slot_no", 0, 4), ("serial_no", 4, 5), ("row", 9, 1), ("win_pose", 10, 1), ("party", 11, 1),
             ("menu_type", 12, 5)]


def decode_player(raw):
    out = {"equip": [0] * 5, "pa": [0] * 48, "sa": [0] * 2}
    for path, off, fmt in PLAYER_LAYOUT:
        node = out
        for k in path[:-1]:
            node = node.setdefault(k, {})
        node[path[-1]] = struct.unpack_from(fmt, raw, off)[0]
    u = struct.unpack_from("<I", raw, 0x34)[0]
    out["info"] = {k: (u >> sh) & ((1 << n) - 1) for k, sh, n in INFO_BITS}
    return out


def encode_player(f, name, base=None):
    """Build a 144-byte PLAYER record. base supplies bytes no field covers (zero if None)."""
    r = bytearray(base if base is not None else bytes(PLAYER_SIZE))
    r[0:0x0A] = encode_text(name, 10)
    for path, off, fmt in PLAYER_LAYOUT:
        node = f
        for k in path:
            node = node[k]
        struct.pack_into(fmt, r, off, node)
    u = struct.unpack_from("<I", r, 0x34)[0] & ~((1 << 17) - 1)
    for k, sh, n in INFO_BITS:
        v = f["info"][k]
        if not 0 <= v < (1 << n):
            raise ValueError(f"info.{k}={v} does not fit the PS1 {n}-bit field")
        u |= v << sh
    struct.pack_into("<I", r, 0x34, u)
    return bytes(r)


@dataclass
class PS1Save:
    block: bytes
    product_code: str = ""
    filename: str = ""

    def __post_init__(self):
        if len(self.block) < BLOCK_USED:
            raise ValueError(f"FF9 save block truncated ({len(self.block)} bytes)")
        if self.block[:2] != b"SC":
            raise ValueError("not a PS1 save block (missing 'SC' title-frame magic)")

    # -- integrity -----------------------------------------------------------
    @property
    def crc_stored(self): return struct.unpack_from("<H", self.block, CRC_OFFSET)[0]
    @property
    def crc_computed(self): return crc16(self.block[:CRC_OFFSET])
    @property
    def crc_ok(self): return self.crc_stored == self.crc_computed

    @property
    def region(self):
        return REGIONS.get(self.product_code[:12], ("unknown", "unknown", None))

    def _u16(self, o): return struct.unpack_from("<H", self.block, o)[0]
    def _i16(self, o): return struct.unpack_from("<h", self.block, o)[0]
    def _u32(self, o): return struct.unpack_from("<I", self.block, o)[0]

    # -- preview --------------------------------------------------------------
    def preview(self):
        b = self.block
        party = []
        for k in range(4):
            o = 0x134 + 16 * k
            if b[o] == 0:
                party.append(None)
                continue
            party.append({"serial_no": b[o + 1], "name": decode_text(b[o + 2:o + 12])[0],
                          "level": b[o + 12]})   # u8; bytes o+13..o+15 are uninitialised
        return {"leader_level": b[0x105], "leader_name": decode_text(b[0x106:0x110])[0],
                "location": decode_text(b[0x110:0x12C])[0], "playtime_frames": self._u32(0x12C),
                "gil": self._u32(0x130) & 0xFFFFFF, "party": party}

    # -- state ------------------------------------------------------------------
    def state(self):
        b = self.block
        return {"mode": b[0x180], "prevMode": b[0x181], "fldMapNo": self._i16(0x1A0), "fldLocNo": self._i16(0x1A2),
                "btlMapNo": self._i16(0x1A4), "btlSubMapNo": struct.unpack_from("<b", b, 0x1A6)[0],
                "wldMapNo": self._i16(0x1A8), "wldLocNo": self._i16(0x1AA)}

    @property
    def gevent(self): return self.block[GEVENT_OFFSET:GEVENT_OFFSET + GEVENT_SIZE]
    @property
    def scenario_counter(self): return self._u16(GEVENT_OFFSET)

    def players(self):
        return [PS1Player(self.block[PLAYER_OFFSET + PLAYER_SIZE * i: PLAYER_OFFSET + PLAYER_SIZE * (i + 1)])
                for i in range(PLAYER_COUNT)]

    def party(self):
        b = self.block
        return {"slot": list(b[0xEE0:0xEE4]), "escape_no": self._u16(0xEE4), "summon_flag": self._u16(0xEE6),
                "gil": self._u32(0xEE8), "frog_no": self._i16(0xEEC), "steal_no": self._i16(0xEEE),
                "dragon_no": self._i16(0xEF0)}

    def items(self):
        b = self.block
        return [(b[ITEM_OFFSET + 2 * i], b[ITEM_OFFSET + 2 * i + 1]) for i in range(256)]

    def rare_items(self): return list(self.block[RARE_OFFSET:RARE_OFFSET + 64])

    def card_stats(self):
        w, l, d = struct.unpack_from("<hhh", self.block, CARD_STATS_OFFSET)
        return {"sWin": w, "sLose": l, "sDraw": d}

    def cards(self):
        """105 records (id, arrow, atk, type, pdef, mdef); id 0xFF = empty."""
        out = []
        for i in range(CARD_SLOTS):
            o = CARD_OFFSET + 6 * i
            cid, arrow, atk, typ, pdef, mdef = self.block[o:o + 6]
            out.append({"id": cid, "arrow": arrow, "atk": atk, "type": typ, "pdef": pdef, "mdef": mdef})
        return out

    def unknown_regions(self):
        b = self.block
        return {"0x0100-0x0104": b[0x100:0x105].hex(), "0x0174-0x017F": b[0x174:0x180].hex(),
                "0x0182-0x019F": b[0x182:0x1A0].hex(), "0x01A7": b[0x1A7], "0x01AC-0x01BF": b[0x1AC:0x1C0].hex(),
                "0x09C0-0x09CF": b[0x9C0:0x9D0].hex(), "0x0EF2-0x0F1F": b[0xEF2:0xF20].hex(),
                "0x1160-0x1177": b[0x1160:0x1178].hex(), "0x13F4-0x13FD": b[0x13F4:0x13FE].hex()}
