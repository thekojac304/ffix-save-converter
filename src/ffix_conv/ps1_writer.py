"""Canonical model -> FF9 PS1 save block (8,192 bytes) and memory-card placement.

Mapped fields are written from the canonical model with the inverse of every transform
in model.FIELD_MAP. PS1-only bytes (header/icon, unknown regions, per-player padding)
come from, in order of preference:
  1. the model's own source block, when the model was read from a PS1 save (lossless round trip);
  2. an explicit base block the user supplies (reported as such);
  3. documented generated values (title, icon, constants) and zeros for unknown regions.
Values that cannot be represented raise PS1WriteError rather than being truncated.
"""
import base64
import struct
import unicodedata

from . import ps1_card, ps1_save
from .ps1_save import (BLOCK_USED, CARD_OFFSET, CARD_SLOTS, CARD_STATS_OFFSET, CRC_OFFSET, GEVENT_OFFSET,
                       ITEM_OFFSET, PARTY_NONE_PS1, PLAYER_OFFSET, PLAYER_SIZE, RARE_OFFSET)

PC_PARTY_NONE = 255
PRODUCT_NTSC_U = "BASLUS-01251"
PRODUCT = {"NTSC-U": PRODUCT_NTSC_U, "PAL": "BESLES-02965"}   # FF9 writes the disc-1 code on every disc
HEADER_CONST = bytes([0x05, 0x00, 0x03, 0x00])        # 0x100-0x103, identical in all 54 fixtures
# Disc from the scenario counter. Boundaries are the closest observed saves on each side
# (disc masks of real PS1 saves: last Disc 1 save 3880, "Start of DISC 2" 3900, last Disc 2
# save 6960, "Start of DISC 3" 6990, last Disc 3 save 10980, "Start of DISC 4" 10995).
# Values inside a gap are ambiguous and need an explicit disc.
DISC_RANGES = [(0, 3880, 1), (3900, 6960, 2), (6990, 10980, 3), (10995, 0xFFFF, 4)]
# Preview portrait id by character slot, observed in the fixtures' preview records
# (slot 3 Steiner -> 4, slot 4 Freya -> 7, slot 7 Amarant -> 8). Slot 8 unobserved.
PORTRAIT_BY_SLOT = {0: 0, 1: 1, 2: 2, 3: 4, 4: 7, 5: 5, 6: 6, 7: 8}
# Load-screen portrait by character model (serial_no), as the PS1 game itself writes it (82 PS1 saves). Records 5-7
# are shared, so the record number alone gave Eiko's portrait to Marcus; Garnet's short-hair model has its own.
# Cinna, Blank and Beatrix never appear in a party preview in the corpus and keep PORTRAIT_BY_SLOT.
PORTRAIT_BY_SERIAL = {0: 0, 1: 0, 2: 1, 3: 2, 4: 2, 5: 3, 7: 4, 8: 4, 9: 5, 10: 6, 11: 6, 12: 7, 13: 8, 15: 9}
PS1_INITIAL_WORLD = (9009, 68)                         # wldMapNo/wldLocNo before the first world-map visit
FPS = {"NTSC-U": 60, "PAL": 50}


class PS1WriteError(ValueError):
    pass


def disc_for_scenario(sc):
    for lo, hi, disc in DISC_RANGES:
        if lo <= sc <= hi:
            return disc
    raise PS1WriteError(f"scenario counter {sc} lies between observed disc boundaries; pass an explicit disc")


def _fullwidth(s):
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in s)


def title_bytes(file_no, seconds):
    hh, mm = divmod(int(seconds) // 60, 60)
    hh = min(hh, 99)
    t = _fullwidth(f"FF9/FILE{file_no:02d}/{hh:02d}:{mm:02d}").encode("shift_jis")
    return t


def generated_header(file_no, seconds):
    """Title frame + a neutral 16x16 icon drawn for this project (not game artwork)."""
    h = bytearray(0x100)
    h[0:2] = b"SC"
    h[2] = 0x11            # icon: 1 frame (as in all fixtures)
    h[3] = 1               # blocks used
    t = title_bytes(file_no, seconds)
    h[4:4 + len(t)] = t
    h[0x25] = 0x5E         # constant byte after the 32-byte title in all fixtures
    clut = [0x0000, 0x7FFF, 0x5294, 0x4210, 0x7C00, 0x001F] + [0] * 10
    for i, c in enumerate(clut):
        struct.pack_into("<H", h, 0x60 + 2 * i, c)
    rows = ["0000000000000000", "0111111111111110", "0122222222222210", "0120002000200210",
            "0122020202022210", "0122202020222210", "0122220202222210", "0122202020222210",
            "0122020202022210", "0120002000200210", "0122222222222210", "0124444444444210",
            "0122222222222210", "0111111111111110", "0000000000000000", "0000000000000000"]
    for y, row in enumerate(rows):
        for x in range(0, 16, 2):
            h[0x80 + y * 8 + x // 2] = int(row[x], 16) | (int(row[x + 1], 16) << 4)
    return bytes(h)


def _b(model_b64):
    return base64.b64decode(model_b64)


def build_block(m, *, base_block=None, file_no=None, region="NTSC-U", disc=None):
    """Return (block bytes, report dict). file_no (1-15, the in-game FILEnn) defaults to the source
    save's own number when the model came from a PS1 card, else 1."""
    if file_no is None:
        name = (m.get("platform_extra") or {}).get("ps1_filename") or ""
        file_no = int(name[-2:]) + 1 if name[-3:-2] == "-" and name[-2:].isdigit() else 1
    rep = {"written": [], "transformed": [], "generated": [], "zero_filled": [], "dropped": [], "warnings": []}
    if region not in FPS:
        raise PS1WriteError(f"unsupported target region {region!r} (NTSC-U or PAL)")
    src = m.get("source", {}).get("platform")
    own = (m.get("platform_extra") or {}).get("ps1_block_b64")
    if own:
        base = bytearray(_b(own))
        rep["generated"].append("PS1-only bytes restored from the model's own source PS1 block")
    elif base_block is not None:
        base = bytearray(base_block[:BLOCK_USED])
        rep["warnings"].append("PS1-only bytes (header/icon, unknown regions, player padding) copied from the "
                               "supplied base block; use a save from the same playthrough")
    else:
        base = None
    b = bytearray(base + bytes(ps1_card.BLOCK - len(base))) if base is not None else bytearray(ps1_card.BLOCK)
    secs = float(m["playtime_seconds"])
    frames = round(secs * FPS[region])
    if not 0 <= frames <= 0xFFFFFFFF:
        raise PS1WriteError("playtime does not fit the PS1 frame counter")

    # ---- header / constants -------------------------------------------------------------
    if base is None:
        b[0:0x100] = generated_header(file_no, secs)
        b[0x100:0x104] = HEADER_CONST
        b[0x178] = 1
        rep["generated"].append("memory-card title 'FF9/FILEnn/hh:mm', project-drawn icon, 0x100-0x103 constant, "
                                "save counter 0x178=1")
        rep["zero_filled"] += ["0x0174-0x0177, 0x0179-0x017F", "0x0182-0x019F", "0x01AC-0x01BF", "0x09C0-0x09CF",
                               "0x0EF2-0x0F1F", "0x1160-0x1177", "0x13F4-0x13FD", "players[] +0x22-0x23, +0x48-0x57"]
    sc = m["event"]["scenario_counter"]
    if base is None or disc is not None:
        d = disc if disc is not None else disc_for_scenario(sc)
        if d not in (1, 2, 3, 4):
            raise PS1WriteError(f"disc must be 1-4, got {d}")
        b[0x104] = 1 << (d - 1)
        rep["transformed"].append(f"disc {d} (mask 0x{1 << (d - 1):02x}) from scenario {sc}" if disc is None
                                  else f"disc {d} as requested")

    # ---- state ---------------------------------------------------------------------------
    st = dict(m["state"])
    if src == "pc" and (st["wldMapNo"], st["wldLocNo"]) == (0, 0):
        st["wldMapNo"], st["wldLocNo"] = PS1_INITIAL_WORLD
        rep["transformed"].append("wldMapNo/wldLocNo 0/0 (PC, before first world-map visit) -> PS1 initial 9009/68")
    try:
        b[0x180], b[0x181] = st["mode"], st["prevMode"]
        struct.pack_into("<hhhb", b, 0x1A0, st["fldMapNo"], st["fldLocNo"], st["btlMapNo"], st["btlSubMapNo"])
        b[0x1A7] = 0xFF if st["btlSubMapNo"] < 0 else 0x00
        struct.pack_into("<hh", b, 0x1A8, st["wldMapNo"], st["wldLocNo"])
    except (struct.error, ValueError) as e:
        raise PS1WriteError(f"state value out of PS1 range: {e}") from e
    rep["written"].append("state")

    # ---- event variables -----------------------------------------------------------------
    g = _b(m["event"]["gEventGlobal_b64"])
    if len(g) != 2048:
        raise PS1WriteError("gEventGlobal must be 2048 bytes")
    b[GEVENT_OFFSET:GEVENT_OFFSET + 2048] = g
    rep["written"].append(f"gEventGlobal (scenario {sc})")
    if src == "pc" and m["event"].get("gStepCount"):
        rep["dropped"].append(f"gStepCount={m['event']['gStepCount']} (no confirmed PS1 location)")

    # ---- players ---------------------------------------------------------------------------
    for i, p in enumerate(m["players"]):
        o = PLAYER_OFFSET + PLAYER_SIZE * i
        old = bytes(b[o:o + PLAYER_SIZE])
        f = dict(p)
        if src == "pc" and not f.get("bonus_cap"):
            # PC stores 0 to mean "derive it"; write what the PC game would use. Vanilla PC rule when 94000_Common.player_bonus is 0 (JsonParser.ParseToFF9StateSystem)
            cap = (p["level"] - 1) * 5
            if p["info"]["serial_no"] in (10, 11):
                lv = p["level"]
                cap += next((t for t in (10, 20, 30, 40, 50, 60, 70, 80, 90) if lv <= t), 99)
            if cap:
                rep["transformed"].append(f"player {i}: bonus.cap 0 -> {cap} (vanilla PC load rule)")
            f["bonus_cap"] = cap
        try:
            rec = ps1_save.encode_player(f, p["name"], base=old)
        except (ps1_save.TextEncodeError, ValueError, struct.error) as e:
            raise PS1WriteError(f"player {i} ({p['name']!r}): {e}") from e
        if ps1_save.decode_text(old[:10])[0] == p["name"]:
            rec = old[:10] + rec[10:]        # keep the game's original name padding bytes
        b[o:o + PLAYER_SIZE] = rec
    rep["written"].append("9 PLAYER records")

    # ---- party / inventory -------------------------------------------------------------------
    pty = m["party"]
    slots = []
    for s in pty["slot"]:
        if s == PC_PARTY_NONE or s == PARTY_NONE_PS1:
            slots.append(PARTY_NONE_PS1)
        elif 0 <= s < 9:
            slots.append(s)
        else:
            raise PS1WriteError(f"party slot value {s} out of range")
    b[0xEE0:0xEE4] = bytes(slots)
    try:
        struct.pack_into("<HHIhhh", b, 0xEE4, pty["escape_no"], pty["summon_flag"], pty["gil"], pty["frog_no"],
                         pty["steal_no"], pty["dragon_no"])
    except struct.error as e:
        raise PS1WriteError(f"party counter out of PS1 range: {e}") from e
    for k, it in enumerate(m["items"]):
        b[ITEM_OFFSET + 2 * k], b[ITEM_OFFSET + 2 * k + 1] = it["id"], it["count"]
    b[RARE_OFFSET:RARE_OFFSET + 64] = bytes(m["rare_items"])
    rep["written"].append("party slots (255 -> 9), counters, gil, items, key items")

    # ---- Tetra Master ----------------------------------------------------------------------------
    mg = m["minigame"]
    struct.pack_into("<hhh", b, CARD_STATS_OFFSET, mg["sWin"], mg["sLose"], mg["sDraw"])
    if src == "ps1" and len(mg["cards"]) == CARD_SLOTS:
        records = list(mg["cards"])          # PS1 keeps gaps between cards: keep positions
    else:
        records = [c for c in mg["cards"] if c["id"] != 255]
        if len(records) > CARD_SLOTS:
            raise PS1WriteError(f"{len(records)} cards exceed the {CARD_SLOTS} PS1 card records")
        records += [{"id": 0xFF, "arrow": 0, "atk": 0, "type": 0, "pdef": 0, "mdef": 0}] * (CARD_SLOTS - len(records))
    cards = [c for c in records if c["id"] != 255]
    for k, c in enumerate(records):
        o = CARD_OFFSET + 6 * k
        if c["id"] != 0xFF and c["type"] > 3:
            raise PS1WriteError(f"card {c} has an invalid attack type")
        try:
            b[o:o + 6] = bytes([c["id"], c["arrow"], c["atk"], c["type"], c["pdef"], c["mdef"]])
        except ValueError as e:
            raise PS1WriteError(f"card {k} value out of byte range: {c}") from e
        if src == "pc" and c["id"] != 0xFF and (c.get("side", 0) != 0 or c.get("cpoint", 10) != 10):
            rep["warnings"].append(f"card {k}: PC side/cpoint {c.get('side')}/{c.get('cpoint')} not representable")
    rep["written"].append(f"{len(cards)} Tetra Master cards")

    # ---- preview (cosmetic; regenerated unless it already matches) ----------------------------------
    _write_preview(b, m, slots, frames, base is not None, rep)

    # memory-card title shows file number and playtime; refresh it when either differs
    t = title_bytes(file_no, secs)
    if bytes(b[4:4 + len(t)]) != t:
        b[4:0x24] = bytes(0x20)
        b[4:4 + len(t)] = t
        if base is not None:
            rep["transformed"].append("memory-card title text refreshed (file number / playtime)")
    struct.pack_into("<H", b, CRC_OFFSET, ps1_save.crc16(bytes(b[:CRC_OFFSET])))
    return bytes(b), rep


def _write_preview(b, m, slots, frames, has_base, rep):
    members = [s for s in slots if s != PARTY_NONE_PS1]
    if not members:
        raise PS1WriteError("party is empty")
    players = m["players"]
    if has_base:
        cur = ps1_save.PS1Save(bytes(b))
        pv = cur.preview()
        same = (pv["playtime_frames"] == frames and pv["gil"] == (m["party"]["gil"] & 0xFFFFFF)
                and sorted(x["level"] for x in pv["party"] if x) == sorted(players[s]["level"] for s in members))
        if same:
            return
    lead = players[members[0]]
    b[0x105] = min(lead["level"], 255)
    b[0x106:0x110] = ps1_save.encode_text(lead["name"], 10)
    loc = (m.get("preview") or {}).get("location") or ""
    loc = unicodedata.normalize("NFKC", loc).replace("’", "'")
    if len(loc) > 28:
        rep["warnings"].append(f"preview location {loc!r} shortened to 28 characters (load-screen text only)")
    try:
        b[0x110:0x12C] = ps1_save.encode_text(loc[:28], 28)
    except ps1_save.TextEncodeError:
        b[0x110:0x12C] = bytes([0xFF]) * 28
        rep["warnings"].append(f"preview location {loc!r} not encodable; left blank")
    struct.pack_into("<I", b, 0x12C, frames)
    struct.pack_into("<I", b, 0x130, m["party"]["gil"])
    for k in range(4):
        o = 0x134 + 16 * k
        # empty record as the game writes it (all 78 empty records in the PS1 corpus): present 0,
        # portrait 0xFF, name 0xFF x10, level 0. Portrait 0 would show Zidane (seen in DuckStation).
        b[o:o + 16] = bytes([0x00]) + bytes([0xFF]) * 11 + bytes(4)
        if k < len(members):
            p = players[members[k]]
            b[o] = 1
            b[o + 1] = PORTRAIT_BY_SERIAL.get(p["info"]["serial_no"],
                                              PORTRAIT_BY_SLOT.get(p["info"]["slot_no"], p["info"]["slot_no"]))
            b[o + 2:o + 12] = ps1_save.encode_text(p["name"], 10)
            b[o + 12] = min(p["level"], 255)
    rep["generated"].append("menu preview (leader = first party member, portrait ids by character model)")


def card_filename(file_no, product=PRODUCT_NTSC_U):
    if not 1 <= file_no <= 15:
        raise PS1WriteError("PS1 file number must be 1-15")
    return f"{product}00000-{file_no - 1:02d}"


def place_on_card(block, file_no, card=None, block_index=None, replace=False):
    """Write block into card (or a new blank card). Returns (card bytes, block index)."""
    if card is None:
        card = ps1_card.blank_card()
    try:
        return ps1_card.write_save(card, block, card_filename(file_no), block_index, replace)
    except ps1_card.CardError as e:
        raise PS1WriteError(str(e)) from e
