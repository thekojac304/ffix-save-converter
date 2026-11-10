"""Memoria / Moguri saves: the per-slot sidecar files Memoria writes next to SavedData_ww.dat.

Memoria (github.com/Albeoris/Memoria, MIT) still writes the vanilla encrypted container, with its richer runtime
state projected onto the vanilla fields (and silently narrowed: item ids wrap to a byte, mod items are dropped). It
also writes `SavedData_ww_Memoria_{slot}_{file}.dat` (0-based indices) beside it. On load Memoria applies the
container, then overrides it with the sidecar, unless the sidecar's playtime differs from the container's by more than
one second: then the sidecar is stale and ignored. A missing sidecar means the container alone is loaded; a corrupt
one makes the slot unloadable. Moguri is a visual mod running on Memoria and adds no save data, so a Moguri save is
a Memoria save. Sources and line references: docs/MEMORIA_RESEARCH.md.

This module reads and writes the sidecar format (SimpleJSON binary), finds the sidecar that belongs to a container
slot, and reconciles container + sidecar into the canonical model exactly as Memoria would load it, refusing values
the original PlayStation game cannot hold unless lossy conversion was explicitly requested.
"""
import base64
import copy
import os
import re
import struct

from . import model

TAG_ARRAY, TAG_CLASS, TAG_STRING, TAG_INT, TAG_DOUBLE, TAG_BOOL, TAG_FLOAT = range(1, 8)
MAX_DEPTH = 64
STALE_SECONDS = 1.0                      # JsonParser.cs: |sidecar time - container time| > 1.0 -> ignored
LEGACY_ABILITY_USAGE = range(1101, 1292)  # older Memoria kept ability-use counters in gEventGlobal[1100 + id]
VANILLA_LIMITS = {"maxHpLimit": 9999, "maxMpLimit": 999, "maxDamageLimit": 9999, "maxMpDamageLimit": 999}
CHARACTER_NAMES = ["Zidane", "Vivi", "Garnet", "Steiner", "Freya", "Quina", "Eiko", "Amarant",
                   "Cinna", "Marcus", "Blank", "Beatrix"]
PAIR_OWNER_SERIALS = {5: {9}, 6: {10, 11}, 7: {13}}   # vanilla serial_no of Quina / Eiko / Amarant (else Tantalus)
CARD_KEYS = ("id", "side", "atk", "type", "pdef", "mdef", "cpoint", "arrow")
PS1_CARD_RECORDS = 105
# Ability ids of each vanilla ability set (menu_type), in the order Memoria writes `pa_extended` (= the PS1 pa[]
# order). Read from sidecars written by Memoria 2025-07-13 (runtime test) and by the 2024 build of the public
# ffix-save-editor sample; identical in both. Cinna, Marcus and Blank learn no abilities (all 0).
VANILLA_ABILITY_IDS = {
    0: (101, 102, 103, 104, 105, 106, 107, 108, 192, 193, 194, 195, 196, 198, 201, 202, 203, 204, 205, 206, 207,
        208, 210, 211, 212, 214, 215, 217, 218, 227, 228, 230, 231, 232, 233, 235, 236, 238, 240, 241, 242, 244,
        245, 248, 249, 250, 253, 254),
    1: (25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 192, 193,
        194, 195, 196, 200, 216, 217, 222, 223, 224, 226, 227, 232, 235, 236, 240, 241, 243, 245, 246, 248, 249, 250),
    2: (49, 51, 53, 55, 58, 60, 62, 64, 1, 2, 3, 5, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 192, 193, 194, 195,
        196, 200, 216, 219, 222, 225, 226, 227, 232, 235, 236, 240, 241, 243, 245, 248, 249, 250, 251, 252),
    3: (141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 192, 193, 194, 195, 196, 197, 198, 201, 202,
        203, 204, 205, 206, 207, 208, 210, 211, 212, 217, 219, 227, 228, 229, 231, 232, 233, 235, 236, 240, 241,
        242, 244, 245, 248, 249, 250),
    4: (117, 118, 119, 120, 121, 122, 123, 124, 192, 193, 194, 195, 196, 197, 198, 199, 201, 202, 203, 204, 205,
        206, 207, 208, 209, 210, 211, 212, 213, 217, 218, 219, 227, 228, 229, 231, 232, 234, 235, 236, 240, 241,
        242, 244, 245, 248, 249, 250),
    5: (77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 192, 193,
        194, 195, 196, 199, 216, 217, 218, 226, 227, 228, 232, 235, 236, 237, 240, 241, 243, 245, 247, 248, 249, 250),
    6: (68, 66, 72, 74, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 20, 21, 22, 23, 24, 192, 193, 194, 195,
        196, 199, 200, 216, 222, 225, 226, 227, 232, 235, 236, 239, 240, 241, 243, 245, 248, 249, 250, 251),
    7: (125, 126, 127, 128, 129, 130, 131, 132, 192, 193, 194, 195, 196, 197, 198, 201, 203, 204, 205, 206, 207,
        208, 210, 211, 212, 216, 217, 218, 220, 221, 227, 228, 229, 231, 232, 233, 235, 236, 238, 240, 241, 242,
        244, 245, 246, 248, 249, 250),
    8: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    10: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    11: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    12: (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    14: (149, 150, 151, 152, 2, 5, 6, 10, 14, 16, 19, 24, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
}


class MemoriaFormatError(ValueError):
    pass


class F32(float):
    """A number stored with the float32 tag (kept so that files round-trip byte for byte)."""


# ---- SimpleJSON binary format -------------------------------------------------------------------
def parse(data):
    """Return (root, end). Bytes after `end` are ignored: Memoria's writer does not truncate old files.

    Class -> dict (key order kept), Array -> list, string -> str, int32 -> int, double -> float,
    float32 -> F32, bool -> bool."""
    pos = 0

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise MemoriaFormatError("Memoria sidecar is truncated or corrupt")
        b = data[pos:pos + n]
        pos += n
        return b

    def i32():
        return struct.unpack("<i", take(4))[0]

    def string():
        n = shift = 0
        while True:
            b = take(1)[0]
            n |= (b & 0x7F) << shift
            shift += 7
            if b < 0x80:
                break
            if shift > 35:
                raise MemoriaFormatError("Memoria sidecar has a bad string length")
        try:
            return take(n).decode("utf-8")
        except UnicodeDecodeError:
            raise MemoriaFormatError("Memoria sidecar has a string that is not UTF-8")

    def node(depth):
        if depth > MAX_DEPTH:
            raise MemoriaFormatError("Memoria sidecar is nested too deeply")
        tag = i32()
        if tag in (TAG_ARRAY, TAG_CLASS):
            count = i32()
            if count < 0 or count > len(data):
                raise MemoriaFormatError("Memoria sidecar has a bad element count")
            if tag == TAG_ARRAY:
                return [node(depth + 1) for _ in range(count)]
            out = {}
            for _ in range(count):
                k = string()
                out[k] = node(depth + 1)
            return out
        if tag == TAG_STRING:
            return string()
        if tag == TAG_INT:
            return i32()
        if tag == TAG_DOUBLE:
            return struct.unpack("<d", take(8))[0]
        if tag == TAG_BOOL:
            return bool(take(1)[0])
        if tag == TAG_FLOAT:
            return F32(struct.unpack("<f", take(4))[0])
        raise MemoriaFormatError(f"Memoria sidecar has an unknown tag {tag}")

    root = node(0)
    if not isinstance(root, dict):
        raise MemoriaFormatError("Memoria sidecar root is not an object")
    return root, pos


def dumps(root):
    """Serialize a tree from parse() (or built by hand) in Memoria's format."""
    out = bytearray()

    def string(s):
        b = s.encode("utf-8")
        n = len(b)
        while True:
            if n < 0x80:
                out.append(n)
                break
            out.append((n & 0x7F) | 0x80)
            n >>= 7
        out.extend(b)

    def node(v):
        if isinstance(v, dict):
            out.extend(struct.pack("<ii", TAG_CLASS, len(v)))
            for k, x in v.items():
                string(k)
                node(x)
        elif isinstance(v, list):
            out.extend(struct.pack("<ii", TAG_ARRAY, len(v)))
            for x in v:
                node(x)
        elif isinstance(v, bool):
            out.extend(struct.pack("<iB", TAG_BOOL, v))
        elif isinstance(v, int):
            if -2 ** 31 <= v < 2 ** 31:
                out.extend(struct.pack("<ii", TAG_INT, v))
            else:
                out.extend(struct.pack("<id", TAG_DOUBLE, float(v)))
        elif isinstance(v, F32):
            out.extend(struct.pack("<if", TAG_FLOAT, v))
        elif isinstance(v, float):
            out.extend(struct.pack("<id", TAG_DOUBLE, v))
        elif isinstance(v, str):
            out.extend(struct.pack("<i", TAG_STRING))
            string(v)
        else:
            raise TypeError(f"cannot store {type(v).__name__} in a Memoria sidecar")

    node(root)
    return bytes(out)


def looks_like_sidecar(data):
    try:
        root, _ = parse(data)
    except MemoriaFormatError:
        return False
    return isinstance(root.get("40000_Common"), dict) and isinstance(root["40000_Common"].get("players"), list)


def _num(v):
    """Numbers by value, whatever tag (Memoria writes ints as int32, large values as double)."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else v
    if isinstance(v, str):
        try:
            f = float(v)
        except ValueError:
            return None
        return int(f) if f.is_integer() else f
    return None


def _truthy(v):
    return v is True or (isinstance(v, str) and v.strip().lower() == "true") or (isinstance(v, int) and v == 1)


# ---- finding the sidecar of a slot -------------------------------------------------------------------
SIDECAR_NAME = re.compile(r"^(?P<stem>.+)_Memoria_(?:(?P<slot>\d+)_(?P<file>\d+)|Autosave)\.dat$", re.IGNORECASE)


def sidecar_path(container_path, slot, file):
    """The sidecar Memoria uses for container slot/file (both 0-based)."""
    return f"{os.path.splitext(container_path)[0]}_Memoria_{slot}_{file}.dat"


def sidecars_beside(container_path):
    """{(slot, file): path} of every sidecar next to this container (0-based), plus "autosave" if present."""
    folder = os.path.dirname(os.path.abspath(container_path))
    stem = os.path.splitext(os.path.basename(container_path))[0].lower()
    found = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return found
    for n in names:
        m = SIDECAR_NAME.match(n)
        if m and m.group("stem").lower() == stem:
            key = (int(m.group("slot")), int(m.group("file"))) if m.group("slot") is not None else "autosave"
            found[key] = os.path.join(folder, n)
    return found


def slot_sidecar(container_path, slot, file, container_time):
    """The state of the sidecar for one container slot, judged the way Memoria judges it on load.

    status: "none" (no file: Memoria loads the container alone), "valid" (Memoria applies it), "untimed" (no time
    key: Memoria applies it unconditionally), "stale" (playtime differs by more than 1 s: Memoria ignores it),
    "corrupt" (Memoria cannot load the slot at all)."""
    path = sidecar_path(container_path, slot, file)
    if not os.path.isfile(path):
        return {"status": "none", "path": path}
    with open(path, "rb") as f:
        raw = f.read()
    try:
        root, end = parse(raw)
        if not looks_like_sidecar(raw[:end]):
            raise MemoriaFormatError("the file is not a Memoria save sidecar")
    except MemoriaFormatError as e:
        return {"status": "corrupt", "path": path, "error": str(e)}
    t = _num((root.get("95000_Setting") or {}).get("00001_time"))
    info = {"path": path, "root": root, "time": t, "trailing_bytes": len(raw) - end}
    if t is None:
        return {"status": "untimed", **info}
    if abs(t - container_time) > STALE_SECONDS:
        return {"status": "stale", **info}
    return {"status": "valid", **info}


def overlay_risk(container_path, slot, file, new_time):
    """For a PC write: would Memoria lay an existing sidecar over the slot we are about to write?

    Returns None (no sidecar), ("stale", path) (Memoria will ignore it) or ("applies", path) (it would override the
    converted save: the write must not proceed while it is there)."""
    s = slot_sidecar(container_path, slot, file, new_time)
    if s["status"] == "none":
        return None
    if s["status"] == "stale":
        return "stale", s["path"]
    return "applies", s["path"]


# ---- reconciling container + sidecar into the canonical model ------------------------------------------
PAIRS = {5: (5, 8), 6: (6, 9), 7: (7, 10)}   # shared PS1 record: (Quina/Eiko/Amarant, Cinna/Marcus/Blank)
# Story positions (scenario counter) at which each shared record changes hands, as observed in 118 vanilla PS1/PC
# saves: (last position seen with Cinna/Marcus/Blank, first position seen with Quina/Eiko/Amarant).
PAIR_SWITCH = {5: (3700, 3700), 6: (6270, 6310), 7: (6795, 6890)}


def _never_played(p):
    return _num((p or {}).get("level")) == 1 and not _num((p or {}).get("exp"))


def pair_occupants(players_by_id, party_ids, container_players=None, scenario=None):
    """Which character holds each shared record (5, 6, 7), and which one Memoria wrote into its own container.

    Memoria's rule (SelectOldSaveSlot) trusts the `sub_replaced` flag of Quina/Eiko/Amarant. But Memoria sets that
    flag on all three whenever it loads a vanilla-format save (JsonParser: the 94000_Common bonus loop calls
    GetPlayerFromOldSave(i, false)), so after loading e.g. an early Disc 2 vanilla save it names Eiko as owner of the
    record that Marcus really uses, and its container drops Marcus from the party. The sidecar keeps every character,
    so the occupant is decided from evidence: a member in the party; else the story position, outside the window
    in which the record changes hands; else a played member over a never-played placeholder (level 1, no EXP); else
    Memoria's flag. Returns {slot: (occupant, container_character)}, where the
    container character is read from the container record's serial_no (Memoria's flag rule if not given)."""
    out = {}
    for slot, (q, t) in PAIRS.items():
        pq, pt = players_by_id.get(q), players_by_id.get(t)
        flag = q if _truthy(((pq or {}).get("info") or {}).get("sub_replaced")) else t
        if pq is None or pt is None:
            choice = q if pq is not None else t
        else:
            in_party = [c for c in (q, t) if c in party_ids]
            last_t, first_q = PAIR_SWITCH[slot]
            if len(in_party) == 1:
                choice = in_party[0]
            elif scenario is not None and scenario < first_q:
                choice = t
            elif scenario is not None and scenario > last_t:
                choice = q
            elif _never_played(players_by_id[flag]) and not _never_played(players_by_id[t if flag == q else q]):
                choice = t if flag == q else q
            else:
                choice = flag
        held = flag
        if container_players is not None:
            held = q if container_players[slot]["info"]["serial_no"] in PAIR_OWNER_SERIALS[slot] else t
        out[slot] = (choice, held)
    return out


def old_slot_of(occupants, cid):
    """The 9-record (PS1/vanilla) index of CharacterId cid, or None (custom character, or the unused pair member)."""
    if 0 <= cid <= 4:
        return cid
    if cid == 11:
        return 8
    for slot, (q, t) in PAIRS.items():
        if cid in (q, t):
            return slot if occupants[slot][0] == cid else None
    return None


class Reconciliation:
    def __init__(self, status, path):
        self.status, self.path = status, path
        self.blocking, self.lossy, self.applied, self.dropped, self.notes = [], [], [], [], []

    def as_dict(self):
        return {"sidecar_status": self.status, "sidecar": self.path, "blocking": self.blocking, "lossy": self.lossy,
                "taken_from_sidecar": self.applied, "dropped_memoria_only": self.dropped, "notes": self.notes}


def reconcile(tree, side, *, allow_lossy=False):
    """Build the canonical model of a container slot the way Memoria would load it.

    side is slot_sidecar() output (or None). Returns (model, Reconciliation). Anything the PS1 game cannot hold is a
    blocking finding; findings that have a well-defined lossy fix are applied only with allow_lossy=True."""
    m = model.from_pc(tree)
    side = side or {"status": "none", "path": None}
    rec = Reconciliation(side["status"], side.get("path"))

    def problem(msg, fix=None):
        if fix is not None and allow_lossy:
            fix()
            rec.lossy.append(msg)
        else:
            rec.blocking.append(msg if fix is None else msg + " (allowed only with lossy conversion)")

    g = bytearray(model.gevent_bytes(m))
    if side["status"] == "none":
        if any(g[i] for i in LEGACY_ABILITY_USAGE):
            rec.notes.append("gEventGlobal bytes 1101-1291 are not zero (ability-use counters from an older Memoria "
                             "build?); they are copied as they are")
        return m, rec
    if side["status"] == "corrupt":
        def ignore():
            rec.notes.append("the corrupt sidecar was ignored; the container alone was converted")
        problem(f"the Memoria sidecar {os.path.basename(side['path'])} is corrupt ({side['error']}), so Memoria itself "
                "cannot load this slot", ignore)
        return m, rec
    if side["status"] == "stale":
        rec.notes.append(f"Memoria sidecar ignored, exactly as Memoria does: its playtime ({side['time']:.1f} s) differs "
                         f"from the save's ({m['playtime_seconds']:.1f} s) by more than {STALE_SECONDS:g} s, so it "
                         "belongs to an older save in this slot")
        _clear_legacy(g, m, rec)
        return m, rec
    if side["status"] == "untimed":
        rec.notes.append("the Memoria sidecar has no playtime; Memoria applies such a sidecar without checking it")
    root = side["root"]

    # -- event state
    ev = root.get("20000_Event") or {}
    if ev.get("gEventGlobal") is not None:
        try:
            sg = base64.b64decode(ev["gEventGlobal"], validate=True)
        except (ValueError, TypeError):
            sg = None
        if sg is None or len(sg) != len(g):
            rec.blocking.append("the sidecar's story state (gEventGlobal) is not 2,048 bytes; a mod changed its size")
        elif sg != bytes(g):
            g[:] = sg
            rec.applied.append("story state (gEventGlobal) differs from the container; Memoria loads the sidecar's")
    for key, what in (("gScriptVector", "vector"), ("gScriptDictionary", "dictionary")):
        entries = ev.get(key) or []
        if entries:
            problem(f"a mod keeps story state in Memoria's script {what} storage ({len(entries)} entries); the PS1 game "
                    "has no such storage, so that mod's progress would be lost",
                    lambda: None)
    if ev.get("gAbilityUsage"):
        rec.dropped.append(f"ability-use counters ({len(ev['gAbilityUsage'])} abilities; read only by Memoria features)")
    _set_event(m, g)
    _clear_legacy(g, m, rec)

    # -- characters
    common = root.get("40000_Common") or {}
    by_id = {}
    for p in common.get("players") or []:
        cid = _num(((p or {}).get("info") or {}).get("slot_no"))
        if isinstance(cid, int):
            by_id[cid] = p
    party_ids = [_num(x) for x in common.get("slot") or []]
    occupants = pair_occupants(by_id, party_ids, m["players"], m["event"]["scenario_counter"])
    for slot, (choice, held) in occupants.items():
        if choice != held:
            rec.applied.append(f"PS1 record {slot} holds {CHARACTER_NAMES[choice]}, who is in use; the container had "
                               f"an unused {CHARACTER_NAMES[held]} record there (Memoria marks Quina, Eiko and Amarant as "
                               "present whenever it loads a vanilla save, and then writes their records instead)")
    for cid, p in sorted(by_id.items()):
        label = CHARACTER_NAMES[cid] if 0 <= cid < len(CHARACTER_NAMES) else f"character {cid}"
        old = old_slot_of(occupants, cid)
        if cid >= 12:
            if cid in party_ids:
                rec.blocking.append(f"a mod-added character ({p.get('name') or label}, id {cid}) is in the party; the PS1 "
                                    "game has no such character")
            else:
                problem(f"a mod-added character ({p.get('name') or label}, id {cid}) would be dropped", lambda: None)
            continue
        if old is None:
            rec.dropped.append(f"{label}'s record (not in use: the PS1 keeps one record for this pair, as vanilla does)")
            continue
        swapped = old in occupants and occupants[old][0] != occupants[old][1]
        _apply_player(m["players"][old], p, label, rec, problem, container_is_other=swapped)

    # -- party and counters
    if party_ids:
        slots = []
        for cid in party_ids[:4]:
            if cid is None or cid == 255:
                slots.append(255)
                continue
            old = old_slot_of(occupants, cid)
            if old is None:
                rec.blocking.append(f"party member id {cid} has no PS1 equivalent")
                slots.append(255)
            else:
                slots.append(old)
        if slots != list(m["party"]["slot"]):
            rec.applied.append(f"party {m['party']['slot']} -> {slots}")
            m["party"]["slot"] = slots
    for k in ("escape_no", "summon_flag", "gil", "frog_no", "steal_no", "dragon_no"):
        v = _num(common.get(k))
        if isinstance(v, int) and v != m["party"][k]:
            rec.applied.append(f"{k} {m['party'][k]} -> {v}")
            m["party"][k] = v
    if m["party"]["gil"] > 9_999_999:
        def clamp_gil():
            m["party"]["gil"] = 9_999_999
        problem(f"gil {m['party']['gil']:,} is above the game's 9,999,999 limit", clamp_gil)
    extra = [k for k in ("humanoid_no", "beast_no", "devil_no", "undead_no", "stone_no", "soul_no", "flight_no")
             if _num(common.get(k))]
    if extra or common.get("kills_per_model") or _num(common.get("battle_no")):
        rec.dropped.append("Memoria battle statistics (kill counts per category and per enemy, battle count)")

    _apply_items(m, common, rec, problem)
    _apply_rare(m, common, rec, problem)
    _apply_cards(m, root.get("30000_MiniGame") or {}, rec, problem)
    return m, rec


def _set_event(m, g):
    m["event"]["gEventGlobal_b64"] = base64.b64encode(bytes(g)).decode("ascii")
    m["event"]["scenario_counter"] = struct.unpack_from("<H", g)[0]


def _clear_legacy(g, m, rec):
    if any(g[i] for i in LEGACY_ABILITY_USAGE):
        for i in LEGACY_ABILITY_USAGE:
            g[i] = 0
        _set_event(m, g)
        rec.applied.append("cleared gEventGlobal bytes 1101-1291 (ability-use counters an older Memoria build kept there; "
                           "they are zero in every vanilla save)")


def _apply_player(q, p, label, rec, problem, container_is_other=False):
    """Apply a sidecar character over its PS1 record. container_is_other: Memoria's container put the other
    member of a shared pair into this record, so the container cannot cross-check this character's abilities."""
    changes = []

    def setv(path, value):
        d = q
        for k in path[:-1]:
            d = d[k]
        if d[path[-1]] != value:
            changes.append(".".join(path))
            d[path[-1]] = value

    name = p.get("name")
    if isinstance(name, str) and name != q["name"]:
        changes.append("name")
        q["name"] = name
    for k in ("category", "level", "exp", "trance"):
        v = _num(p.get(k))
        if isinstance(v, int):
            setv((k,), v)
    for grp, keys in (("cur", ("hp", "mp", "at", "at_coef", "capa")), ("max", ("hp", "mp", "at", "at_coef", "capa")),
                      ("elem", ("dex", "str", "mgc", "wpr")),
                      ("defence", ("p_def", "p_ev", "m_def", "m_ev")),
                      ("basis", ("max_hp", "max_mp", "dex", "str", "mgc", "wpr")), ("bonus", ("dex", "str", "mgc", "wpr"))):
        src = p.get(grp) or {}
        for k in keys:
            v = _num(src.get(k))
            if isinstance(v, int):
                setv((grp, k), v)
    cap = _num((p.get("bonus") or {}).get("cap"))
    if isinstance(cap, int) and cap != q.get("bonus_cap"):
        changes.append("bonus.cap")
        q["bonus_cap"] = cap
    info = p.get("info") or {}
    for k in ("serial_no", "row", "win_pose", "party", "menu_type"):
        v = _num(info.get(k))
        if isinstance(v, int):
            setv(("info", k), v)
    status = _num(p.get("status"))
    if isinstance(status, int):
        if status >> 8:
            rec.dropped.append(f"{label}: Memoria-only status bits {status >> 8:#x} (only permanent statuses exist on PS1)")
        setv(("status",), status & 0xFF)

    # limits raised by a mod or setting
    for k, vanilla in VANILLA_LIMITS.items():
        v = _num(p.get(k))
        if isinstance(v, int) and v != vanilla:
            rec.notes.append(f"{label}: {k} is {v} (vanilla {vanilla}): a gameplay mod or Memoria setting raised it")
    for grp in ("cur", "max"):
        if q[grp]["hp"] > 9999:
            problem(f"{label}: {grp} HP {q[grp]['hp']} is above the PS1 limit 9999",
                    lambda grp=grp: q[grp].__setitem__("hp", 9999))
        if q[grp]["mp"] > 999:
            problem(f"{label}: {grp} MP {q[grp]['mp']} is above the PS1 limit 999",
                    lambda grp=grp: q[grp].__setitem__("mp", 999))
        if q[grp]["capa"] > 99:
            problem(f"{label}: {grp} magic stones {q[grp]['capa']} is above the game's limit 99",
                    lambda grp=grp: q[grp].__setitem__("capa", 99))
    if q["basis"]["max_hp"] > 9999:
        problem(f"{label}: base max HP {q['basis']['max_hp']} is above 9999", lambda: q["basis"].__setitem__("max_hp", 9999))
    if q["basis"]["max_mp"] > 999:
        problem(f"{label}: base max MP {q['basis']['max_mp']} is above 999", lambda: q["basis"].__setitem__("max_mp", 999))
    if q["info"]["serial_no"] >= 32 or q["info"]["menu_type"] >= 32:
        rec.blocking.append(f"{label}: a non-vanilla character model or ability set (serial {q['info']['serial_no']}, "
                            f"preset {q['info']['menu_type']}) from a mod")

    # equipment: the container holds ids wrapped to a byte, so the sidecar decides
    equip = [_num(x) for x in (p.get("equip") or [])]
    if len(equip) == 5 and all(isinstance(x, int) for x in equip):
        for i, item in enumerate(equip):
            if item >= 256 or item < 0:
                problem(f"{label}: equipped mod item id {item} does not exist on PS1 (the container shows "
                        f"item {item & 0xFF} instead, which is wrong); lossy conversion unequips it",
                        lambda i=i: q["equip"].__setitem__(i, 255))
            elif item != q["equip"][i]:
                changes.append(f"equip[{i}]")
                q["equip"][i] = item

    # abilities
    sa_ids = [_num(x) for x in (p.get("sa_extended") or [])]
    if p.get("sa_extended") is not None:
        bad = [x for x in sa_ids if not isinstance(x, int) or not 0 <= x < 64]
        if bad:
            problem(f"{label}: mod support abilities {bad} do not exist on PS1", lambda: None)
        bits = 0
        for x in sa_ids:
            if isinstance(x, int) and 0 <= x < 64:
                bits |= 1 << x
        new_sa = [bits & 0xFFFFFFFF, bits >> 32]
        if new_sa != list(q["sa"]):
            changes.append("support abilities")
            q["sa"] = new_sa
    pa = p.get("pa_extended")
    if pa is not None:
        ids = [_num((x or {}).get("id")) for x in pa]
        ap = [_num((x or {}).get("cur")) for x in pa]
        vanilla_ids = VANILLA_ABILITY_IDS.get(q["info"]["menu_type"])
        if any(not isinstance(i, int) or i >= 256 or i < 0 for i in ids) or len(pa) > len(q["pa"]):
            rec.blocking.append(f"{label}: a modded ability list ({len(pa)} abilities, ids up to "
                                f"{max((i for i in ids if isinstance(i, int)), default=0)}); the PS1 game cannot hold it")
        elif vanilla_ids is not None and tuple(ids) != vanilla_ids[:len(ids)]:
            rec.blocking.append(f"{label}: the ability list differs from the vanilla list of ability set "
                                f"{q['info']['menu_type']} (a mod changed it); the PS1 game cannot hold it")
        elif vanilla_ids is None and not container_is_other and                 any(not isinstance(a, int) or (a & 0xFF) != q["pa"][j] for j, a in enumerate(ap)):
            rec.blocking.append(f"{label}: ability set {q['info']['menu_type']} is not a known vanilla set and its AP "
                                "does not match the container, so the abilities cannot be identified safely")
        elif any(not isinstance(a, int) or a < 0 for a in ap):
            rec.blocking.append(f"{label}: unreadable ability AP in the sidecar")
        else:
            for j, a in enumerate(ap):
                if a > 255:
                    problem(f"{label}: {a} AP in one ability is above the PS1 limit 255",
                            lambda j=j: q["pa"].__setitem__(j, 255))
                elif a != q["pa"][j]:
                    changes.append(f"pa[{j}]")
                    q["pa"][j] = a
    if changes:
        rec.applied.append(f"{label}: " + ", ".join(changes))


def _apply_items(m, common, rec, problem):
    items = common.get("items")
    if items is None:
        return
    owned = [(_num(x.get("id")), _num(x.get("count"))) for x in items if isinstance(x, dict)]
    owned = [(i, c) for i, c in owned if isinstance(i, int) and isinstance(c, int) and c > 0]
    mods = [(i, c) for i, c in owned if not 0 <= i < 255]
    keep = [(i, c) for i, c in owned if 0 <= i < 255]
    if mods:
        problem(f"{len(mods)} mod item stack(s) (ids {sorted({i for i, _ in mods})[:8]}) do not exist on PS1", lambda: None)
    if len(keep) > 256:
        problem(f"{len(keep)} item stacks exceed the 256 the PS1 holds", lambda: keep.__delitem__(slice(256, None)))
    big = [(i, c) for i, c in keep if c > 255]
    if big:
        problem(f"item counts above 255 ({big[:4]})", lambda: keep.__setitem__(slice(None), [(i, min(c, 255)) for i, c in keep]))
    if any(c > 99 for _, c in keep):
        rec.notes.append("some item counts are above the game's usual 99 per item")
    current = [(x["id"], x["count"]) for x in m["items"] if x["count"] > 0]
    if keep[:256] != current:
        m["items"] = [{"id": i, "count": c} for i, c in keep[:256]] + \
                     [{"id": 255, "count": 0} for _ in range(256 - min(len(keep), 256))]
        rec.applied.append(f"inventory ({len(keep)} stacks) taken from the sidecar")


def _apply_rare(m, common, rec, problem):
    rare = common.get("rareItemsEx")
    if rare is None:
        return
    b = bytearray(64)
    mods = []
    for x in rare:
        i = _num((x or {}).get("id"))
        if not isinstance(i, int):
            continue
        if not 0 <= i < 256:
            mods.append(i)
            continue
        if _truthy(x.get("obtained")):
            b[i >> 2] |= 1 << ((i & 3) * 2)
        if _truthy(x.get("used")):
            b[i >> 2] |= 1 << ((i & 3) * 2 + 1)
    if mods:
        problem(f"mod key items {mods[:8]} do not exist on PS1", lambda: None)
    if list(b) != list(m["rare_items"]):
        m["rare_items"] = list(b)
        rec.applied.append("key items taken from the sidecar")


def _apply_cards(m, mg, rec, problem):
    for k in ("sWin", "sLose", "sDraw"):
        v = _num(mg.get(k))
        if isinstance(v, int) and v != m["minigame"][k]:
            rec.applied.append(f"Tetra Master {k} {m['minigame'][k]} -> {v}")
            m["minigame"][k] = v
    cards = mg.get("MiniGameCard")
    if cards is None:
        return
    keep, mods = [], []
    for c in cards:
        rec_ = {k: _num((c or {}).get(k)) for k in CARD_KEYS}
        if not all(isinstance(v, int) for v in rec_.values()):
            continue
        if rec_["id"] == 255:
            continue
        (keep if 0 <= rec_["id"] < 100 else mods).append(rec_)
    if mods:
        problem(f"{len(mods)} mod Tetra Master card(s) do not exist on PS1", lambda: None)
    if len(keep) > PS1_CARD_RECORDS:
        problem(f"{len(keep)} cards exceed the {PS1_CARD_RECORDS} the PS1 holds",
                lambda: keep.__delitem__(slice(PS1_CARD_RECORDS, None)))
    current = [{k: c[k] for k in CARD_KEYS} for c in m["minigame"]["cards"] if c["id"] != 255]
    norm = lambda lst: [(c["id"], c["atk"], c["type"], c["pdef"], c["mdef"], c["arrow"]) for c in lst]
    if norm(keep) != norm(current):
        if len(keep) > len(current) and norm(keep[:len(current)]) == norm(current) and len(current) == 100:
            rec.applied.append(f"{len(keep) - 100} card(s) beyond the container's 100 recovered from the sidecar")
        else:
            rec.applied.append(f"Tetra Master collection ({len(keep)} cards) taken from the sidecar")
        m["minigame"]["cards"] = keep


# ---- synthetic sidecars (test fixtures) ----------------------------------------------------------------
def synthesize(m, playtime=None, vanilla_loaded=True):
    """A sidecar with the content Memoria would write for this vanilla-state model (field order as Memoria's).

    Used to build Memoria test fixtures from vanilla saves; the converter never writes sidecars to a game folder.
    vanilla_loaded=True reproduces what genuine Memoria writes after loading a vanilla save: `sub_replaced` set on
    Quina, Eiko and Amarant even while Cinna, Marcus or Blank use their record (seen in the 2026-11-06 runtime test)."""
    t = m["playtime_seconds"] if playtime is None else playtime
    players = []
    for cid, name in enumerate(CHARACTER_NAMES):
        old = 8 if cid == 11 else cid if cid < 8 else cid - 3
        q = m["players"][old]
        active = True
        if 5 <= old <= 7:
            owner = q["info"]["serial_no"] in PAIR_OWNER_SERIALS[old]
            active = owner if cid < 8 else not owner
        src = q if active else _blank_player(q)
        players.append({
            "name": src["name"] if active else name, "category": src["category"], "level": src["level"],
            "exp": src["exp"],
            "cur": {k: src["cur"][k] for k in ("hp", "mp", "at", "at_coef", "capa")},
            "max": {k: src["max"][k] for k in ("hp", "mp", "at", "at_coef", "capa")},
            "trance": src["trance"], "web_bone": src["web_bone"],
            "elem": {k: src["elem"][k] for k in ("dex", "str", "mgc", "wpr")},
            "defence": {k: src["defence"][k] for k in ("p_def", "p_ev", "m_def", "m_ev")},
            "basis": {k: src["basis"][k] for k in ("max_hp", "max_mp", "dex", "str", "mgc", "wpr")},
            "info": {"slot_no": cid, "serial_no": src["info"]["serial_no"], "row": src["info"]["row"],
                     "win_pose": src["info"]["win_pose"], "party": src["info"]["party"],
                     "menu_type": src["info"]["menu_type"],
                     # Memoria sets the flag on Quina, Eiko and Amarant whenever it loads a vanilla save
                     "sub_replaced": "True" if (cid not in (5, 6, 7) or active or vanilla_loaded) else "False"},
            "status": src["status"], "equip": list(src["equip"]),
            "bonus": {**{k: src["bonus"][k] for k in ("dex", "str", "mgc", "wpr")}, "cap": src.get("bonus_cap", 0)},
            "pa_extended": [{"id": i, "cur": a} for i, a in zip(VANILLA_ABILITY_IDS.get(src["info"]["menu_type"],
                                                                      range(1, 49)), src["pa"])],
            "sa_extended": [b for b in range(64) if (src["sa"][b // 32] >> (b % 32)) & 1],
            **VANILLA_LIMITS, "basis_capa": src["cur"]["capa"], "basis_max_capa": src["max"]["capa"],
        })
    party = m["party"]
    ids = {old: cid for cid, old in enumerate([0, 1, 2, 3, 4, 5, 6, 7, None, None, None, 8]) if old is not None}
    for old in (5, 6, 7):
        if m["players"][old]["info"]["serial_no"] not in PAIR_OWNER_SERIALS[old]:
            ids[old] = old + 3
    return {
        "95000_Setting": {"00001_time": float(t)},
        "20000_Event": {"gStepCount": m["event"].get("gStepCount", 0), "gEventGlobal": m["event"]["gEventGlobal_b64"],
                        "gAbilityUsage": [], "gScriptVector": [], "gScriptDictionary": []},
        "40000_Common": {
            "players": players,
            "slot": [255 if s in (9, 255) else ids[s] for s in party["slot"]],
            "escape_no": party["escape_no"], "summon_flag": party["summon_flag"], "gil": party["gil"],
            "frog_no": party["frog_no"], "steal_no": party["steal_no"], "humanoid_no": 0, "beast_no": 0,
            "devil_no": 0, "dragon_no": party["dragon_no"], "undead_no": 0, "stone_no": 0, "soul_no": 0,
            "flight_no": 0, "kills_per_model": [],
            "items": [{"id": x["id"], "count": x["count"]} for x in m["items"] if x["count"] > 0],
            "rareItemsEx": [{"id": i, "obtained": "True" if (m["rare_items"][i >> 2] >> ((i & 3) * 2)) & 1 else "False",
                             "used": "True" if (m["rare_items"][i >> 2] >> ((i & 3) * 2 + 1)) & 1 else "False"}
                            for i in range(256) if (m["rare_items"][i >> 2] >> ((i & 3) * 2)) & 3],
            "battle_no": 0,
        },
        "30000_MiniGame": {"sWin": m["minigame"]["sWin"], "sLose": m["minigame"]["sLose"],
                           "sDraw": m["minigame"]["sDraw"],
                           "MiniGameCard": [{k: c[k] for k in CARD_KEYS} for c in m["minigame"]["cards"] if c["id"] != 255]},
    }


def _blank_player(q):
    b = copy.deepcopy(q)
    b["level"], b["exp"] = 1, 0
    return b
