"""PlayStation memory-card containers and save-block extraction.

Supported inputs (detected by content, not extension):
  raw card      131,072 bytes starting "MC"   (.mcr .mcd .srm .mc .ddf .vm1 ...)
  DexDrive      3,904-byte header "123-456-STD" + raw card   (.gme)
  VGS/Connectix 64-byte header "VgsM" + raw card              (.mem .vgs)
  PSP/Vita VMP  128-byte header "\\0PMV" + raw card            (.vmp; signature not checked)
  PS3 PSV       "\\0VSP" header, single save                   (.psv)
  MCS / PSX     128-byte directory frame + save data          (.mcs .ps1 single save)
  Raw block     the 8,192-byte save block itself
Nothing here modifies input bytes.
"""
import struct
from dataclasses import dataclass

CARD_SIZE = 0x20000
FRAME = 0x80
BLOCK = 0x2000


class CardError(ValueError):
    pass


@dataclass
class SaveEntry:
    block_index: int          # 1..15 for cards; 0 for single-save files
    product_code: str         # e.g. "BASLUS-01251" + game-specific suffix
    filename: str             # full 20-char directory filename
    size: int
    data: bytes               # first block of the save (FF9 uses one 8 KB block)
    directory_ok: bool        # directory-frame XOR checksum valid
    container: str


def _xor(frame):
    x = 0
    for b in frame[:0x7F]:
        x ^= b
    return x


def parse_raw_card(card, container="raw"):
    if len(card) != CARD_SIZE:
        raise CardError(f"card image must be {CARD_SIZE} bytes, got {len(card)}")
    if card[:2] != b"MC":
        raise CardError("missing 'MC' card header")
    entries = []
    for i in range(1, 16):
        fr = card[i * FRAME:(i + 1) * FRAME]
        state = struct.unpack_from("<I", fr, 0)[0]
        if state != 0x51:      # 0x51 = in use, first block of a file
            continue
        size = struct.unpack_from("<I", fr, 4)[0]
        name = fr[0x0A:0x1E].split(b"\x00")[0].decode("ascii", errors="replace")
        nblocks = max(1, size // BLOCK)
        data = bytearray(card[i * BLOCK:(i + 1) * BLOCK])
        # follow the link chain for multi-block files (FF9 saves are single-block)
        nxt, cur, guard = struct.unpack_from("<H", fr, 8)[0], i, 0
        while nxt != 0xFFFF and len(data) < nblocks * BLOCK and guard < 15:
            blk = nxt + 1
            if not 1 <= blk <= 15:
                break
            data += card[blk * BLOCK:(blk + 1) * BLOCK]
            nxt = struct.unpack_from("<H", card, blk * FRAME + 8)[0]
            guard += 1
        entries.append(SaveEntry(i, name[:12], name, size, bytes(data), _xor(fr) == fr[0x7F], container))
    return entries


def parse_file(raw):
    """Return (container_name, [SaveEntry]) for any supported input."""
    n = len(raw)
    if n == CARD_SIZE and raw[:2] == b"MC":
        return "raw-card", parse_raw_card(raw, "raw-card")
    if raw[:11] == b"123-456-STD" and n == 3904 + CARD_SIZE:
        return "dexdrive-gme", parse_raw_card(raw[3904:], "dexdrive-gme")
    if raw[:4] == b"VgsM" and n == 64 + CARD_SIZE:
        return "vgs", parse_raw_card(raw[64:], "vgs")
    if raw[:4] == b"\x00PMV" and n == 0x80 + CARD_SIZE:
        return "psp-vmp", parse_raw_card(raw[0x80:], "psp-vmp")
    if raw[:4] == b"\x00VSP":
        # PS3 virtual save: 0x84-byte header, then the PS1 save data (title frame first)
        if n < 0x84 + BLOCK:
            raise CardError("PSV file too small")
        size = struct.unpack_from("<I", raw, 0x40)[0]
        name = raw[0x64:0x78].split(b"\x00")[0].decode("ascii", errors="replace")
        data = raw[0x84:0x84 + BLOCK]
        return "ps3-psv", [SaveEntry(0, name[:12], name, size, data, True, "ps3-psv")]
    if n in (FRAME + BLOCK, FRAME + BLOCK * 2) and raw[0] == 0x51:
        fr = raw[:FRAME]
        name = fr[0x0A:0x1E].split(b"\x00")[0].decode("ascii", errors="replace")
        return "mcs-single", [SaveEntry(0, name[:12], name, struct.unpack_from("<I", fr, 4)[0],
                                        raw[FRAME:FRAME + BLOCK], _xor(fr) == fr[0x7F], "mcs-single")]
    if n == BLOCK and raw[:2] == b"SC":
        return "raw-block", [SaveEntry(0, "", "", BLOCK, raw, True, "raw-block")]
    raise CardError(f"unrecognised PS1 save container ({n} bytes, header {raw[:4]!r})")


# ---- writing ---------------------------------------------------------------------------
FREE_STATES = (0xA0, 0xA1, 0xA2, 0xA3)   # free, or deleted first/middle/last block


def directory(card):
    """{block 1..15: (state, filename)} read straight from a raw card's directory frames."""
    if len(card) != CARD_SIZE or card[:2] != b"MC":
        raise CardError("not a raw 128 KB memory card image")
    return {i: (struct.unpack_from("<I", card, i * FRAME)[0],
                bytes(card[i * FRAME + 0x0A:i * FRAME + 0x1E]).split(b"\x00")[0].decode("ascii", "replace"))
            for i in range(1, 16)}


def _frame(state, size, link, name=b""):
    fr = bytearray(FRAME)
    struct.pack_into("<IIH", fr, 0, state, size, link)
    fr[0x0A:0x0A + len(name)] = name
    fr[0x7F] = _xor(fr)
    return bytes(fr)


def blank_card():
    """A freshly formatted 128 KB card, laid out exactly like the emulator-written fixtures."""
    card = bytearray(CARD_SIZE)
    hdr = bytearray(FRAME)
    hdr[0:2] = b"MC"
    hdr[0x7F] = _xor(hdr)
    card[0:FRAME] = hdr
    for i in range(1, 16):
        card[i * FRAME:(i + 1) * FRAME] = _frame(0xA0, 0, 0xFFFF)
    for i in range(16, 36):
        card[i * FRAME:(i + 1) * FRAME] = _frame(0xFFFFFFFF, 0, 0xFFFF)
    card[63 * FRAME:64 * FRAME] = hdr
    return bytes(card)


def write_save(card, block, filename, block_index=None, replace=False):
    """Return a new card image with a one-block save written; other blocks are untouched.

    block_index None picks the first free block. An occupied block is only replaced when
    replace=True and it is a single-block save; multi-block files are never touched.
    """
    if len(card) != CARD_SIZE or card[:2] != b"MC":
        raise CardError("target is not a raw 128 KB memory card image")
    if len(block) != BLOCK:
        raise CardError("save block must be 8192 bytes")
    name = filename.encode("ascii")
    if not 1 <= len(name) <= 20:
        raise CardError("directory filename must be 1-20 ASCII characters")
    card = bytearray(card)
    states = {i: struct.unpack_from("<I", card, i * FRAME)[0] for i in range(1, 16)}
    names = {i: bytes(card[i * FRAME + 0x0A:i * FRAME + 0x1E]).split(b"\x00")[0] for i in range(1, 16)}
    for i, n in names.items():
        if n == name and states[i] not in FREE_STATES and i != block_index:
            raise CardError(f"a save named {filename!r} already exists in block {i}")
    if block_index is None:
        free = [i for i in range(1, 16) if states[i] in FREE_STATES]
        if not free:
            raise CardError("memory card is full")
        block_index = free[0]
    if not 1 <= block_index <= 15:
        raise CardError("block index must be 1-15")
    st = states[block_index]
    if st not in FREE_STATES:
        size = struct.unpack_from("<I", card, block_index * FRAME + 4)[0]
        link = struct.unpack_from("<H", card, block_index * FRAME + 8)[0]
        if not replace:
            raise CardError(f"block {block_index} is occupied by {names[block_index].decode('ascii', 'replace')!r}")
        if st != 0x51 or size > BLOCK or link != 0xFFFF:
            raise CardError(f"block {block_index} belongs to a multi-block file; refusing to replace it")
    card[block_index * FRAME:(block_index + 1) * FRAME] = _frame(0x51, BLOCK, 0xFFFF, name)
    card[block_index * BLOCK:(block_index + 1) * BLOCK] = block
    return bytes(card), block_index


def single_save_file(block, filename):
    """Export one save as a .mcs-style file (directory frame + block)."""
    return _frame(0x51, BLOCK, 0xFFFF, filename.encode("ascii")) + bytes(block)
