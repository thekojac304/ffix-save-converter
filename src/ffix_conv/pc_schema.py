"""Schema-driven codec for one decrypted PC save slot (vanilla 2016 release).

The game builds a JSON tree plus a parallel "schema" tree of .NET type names
(Memoria: Assembly-CSharp/Global/JsonParser.cs), flattens both depth-first with
object keys *sorted* and arrays in order (SharedDataBytesStorage.cs), and writes
each leaf little-endian. Field names and types below transcribe that source.

Values are kept as a nested dict/list tree mirroring the game's JSON; leaves are
Python ints/floats/bools/str. Encoding a decoded tree reproduces the input bytes
exactly (verified by tests against real fixtures).
"""
import struct
import unicodedata

DATA_SIZE = 17966          # bytes after the 4-byte "SAVE" header (metadata DataSize)
SLOT_PLAIN_SIZE = DATA_SIZE + 4

# type code -> (struct format, size). 's128'/'s4k' are NUL-padded UTF-8 strings.
TYPES = {
    "u8": ("<B", 1), "i8": ("<b", 1), "i16": ("<h", 2), "u16": ("<H", 2),
    "i32": ("<i", 4), "u32": ("<I", 4), "i64": ("<q", 8), "u64": ("<Q", 8),
    "f32": ("<f", 4), "f64": ("<d", 8), "bool": ("<?", 1),
    "s128": (None, 128), "s4k": (None, 4096),
}


def arr(t, n):
    return [t] * n


def _player():
    stat = {"hp": "u16", "mp": "i16", "at": "i16", "at_coef": "i8", "capa": "u8"}
    return {
        "name": "s128", "category": "u8", "level": "u8", "exp": "u32",
        "cur": dict(stat), "max": dict(stat),
        "trance": "u8", "web_bone": "u8",
        "elem": {"dex": "u8", "str": "u8", "mgc": "u8", "wpr": "u8"},
        "defence": {"p_def": "u8", "p_ev": "u8", "m_def": "u8", "m_ev": "u8"},
        "basis": {"max_hp": "i16", "max_mp": "i16", "dex": "u8", "str": "u8", "mgc": "u8", "wpr": "u8"},
        "info": {"slot_no": "u8", "serial_no": "u8", "row": "u8", "win_pose": "u8", "party": "u8", "menu_type": "u8"},
        "status": "u8", "equip": arr("u8", 5),
        "bonus": {"dex": "u16", "str": "u16", "mgc": "u16", "wpr": "u16"},
        "pa": arr("u8", 48), "sa": arr("u32", 2),
    }


SUMMONS = ["shiva", "ifrit", "ramuh", "carbuncle_reflector", "carbuncle_haste", "carbuncle_protect",
           "carbuncle_shell", "fenrir_earth", "fenrir_wind", "atomos", "phoenix", "leviathan", "odin",
           "madeen", "bahamut", "arc"]


def _achievement98():
    d = {"00001_abnormal_status": "u32"}
    for i, s in enumerate(SUMMONS, start=2):
        d[f"0000{i}_summon_{s}"] = "bool"   # game's keys: "00002".."00009", then "000010".."000017"
    d["99999_ReservedBuffer"] = arr("i32", 123)
    return d


SCHEMA = {"Data": {
    "10000_State": {"mode": "u8", "prevMode": "u8", "fldMapNo": "i16", "fldLocNo": "i16", "btlMapNo": "i16",
                    "btlSubMapNo": "i8", "wldMapNo": "i16", "wldLocNo": "i16", "timeCounter": "f32",
                    "timerControl": "bool", "timerDisplay": "bool"},
    "20000_Event": {"gStepCount": "i32", "gEventGlobal": "s4k"},
    "30000_MiniGame": {"sWin": "i16", "sLose": "i16", "sDraw": "i16",
                       "MiniGameCard": [{"id": "u8", "side": "u8", "atk": "u8", "type": "i32", "pdef": "u8",
                                         "mdef": "u8", "cpoint": "u8", "arrow": "u8"} for _ in range(100)]},
    "40000_Common": {"players": [_player() for _ in range(9)], "slot": arr("u8", 4), "escape_no": "u16",
                     "summon_flag": "u16", "gil": "u32", "frog_no": "i16", "steal_no": "i16", "dragon_no": "i16",
                     "items": [{"id": "u8", "count": "u8"} for _ in range(256)], "rareItems": arr("u8", 64)},
    "50000_Setting": {"cfg": {k: "u64" for k in ["sound", "sound_effect", "control", "cursor", "atb", "camera",
                                                 "move", "vibe", "btl_speed", "fld_msg", "here_icon", "win_type",
                                                 "target_win", "control_data"]}
                      | {"control_data_keyboard": arr("i32", 10), "control_data_joystick": arr("s128", 10),
                         "skip_btl_camera": "u64"},
                      "time": "f32"},
    "60000_Sound": {"auto_save_bgm_id": "i32"},
    "70000_World": {"data.cameraState.rotationMax": "f32", "data.cameraState.upperCounter": "i16",
                    "data.cameraState.upperCounterSpeed": "i32", "data.cameraState.upperCounterForce": "bool",
                    "data.cameraState.rotation": "f32", "data.cameraState.rotationRev": "f32",
                    "data.hintmap": "u32"},
    "80000_Achievement": {"AteCheckArray": arr("i32", 100), "EvtReservedArray": arr("i32", 17),
                          "blkMag_no": "i32", "whtMag_no": "i32", "bluMag_no": "i32", "summon_no": "i32",
                          "enemy_no": "i32", "backAtk_no": "i32", "defence_no": "i32", "trance_no": "i32",
                          "abilities": arr("i32", 221), "passiveAbilities": arr("i32", 63),
                          "synthesisCount": "i32", "AuctionTime": "i32", "StiltzkinBuy": "i32",
                          "QuadmistWinList": arr("i32", 300)},
    "91000_State": arr("i32", 128),
    "92000_Event": arr("i32", 128),
    "93000_MiniGame": arr("i32", 128),
    "94000_Common": {"00001_player_bonus": arr("u32", 9), "99999_ReservedBuffer": arr("i32", 119)},
    "95000_Setting": {"00001_time": "f64", "99999_ReservedBuffer": arr("i32", 126)},
    "96000_Sound": arr("i32", 128),
    "97000_World": arr("i32", 128),
    "98000_Achievement": _achievement98(),
    "99000_Other": arr("i32", 384),
}}


def _char_class(c):
    # Culture-aware (UCA-like) primary ordering used by .NET/Mono List<string>.Sort():
    # punctuation < digits < letters, letters compared case-insensitively.
    if c.isdigit():
        return 1
    if c.isalpha():
        return 2
    return 0


def culture_key(s):
    primary = tuple((_char_class(c), c.lower()) for c in s)
    tertiary = tuple(0 if c.islower() or not c.isalpha() else 1 for c in s)  # lowercase first
    return (primary, tertiary)


def sorted_keys(d):
    return sorted(d.keys(), key=culture_key)


def iter_leaves(schema, path=()):
    """Yield (path, type) in on-disk order."""
    if isinstance(schema, dict):
        for k in sorted_keys(schema):
            yield from iter_leaves(schema[k], path + (k,))
    elif isinstance(schema, list):
        for i, s in enumerate(schema):
            yield from iter_leaves(s, path + (i,))
    else:
        yield path, schema


LAYOUT = []
_off = 0
for _p, _t in iter_leaves(SCHEMA):
    LAYOUT.append((_p, _t, _off))
    _off += TYPES[_t][1]
SCHEMA_SIZE = _off
OFFSETS = {p: (t, o) for p, t, o in LAYOUT}


def _set(tree, path, value):
    node = tree
    for i, k in enumerate(path[:-1]):
        nxt = path[i + 1]
        if isinstance(node, dict):
            node = node.setdefault(k, [] if isinstance(nxt, int) else {})
        else:
            while len(node) <= k:
                node.append([] if isinstance(nxt, int) else {})
            node = node[k]
    last = path[-1]
    if isinstance(node, list):
        while len(node) <= last:
            node.append(None)
    node[last] = value


def get(tree, path):
    node = tree
    for k in path:
        node = node[k]
    return node


def decode(data):
    """Decode DATA_SIZE bytes (without the 'SAVE' header) into a tree."""
    if len(data) != SCHEMA_SIZE:
        raise ValueError(f"slot payload is {len(data)} bytes, schema expects {SCHEMA_SIZE}")
    tree = {}
    for path, t, off in LAYOUT:
        fmt, size = TYPES[t]
        raw = data[off:off + size]
        if fmt is None:
            v = raw  # keep raw bytes for strings: exact round trip, interpret lazily
        else:
            v = struct.unpack(fmt, raw)[0]
        _set(tree, path, v)
    return tree


def encode(tree):
    out = bytearray(SCHEMA_SIZE)
    for path, t, off in LAYOUT:
        fmt, size = TYPES[t]
        v = get(tree, path)
        if fmt is None:
            if isinstance(v, str):
                v = v.encode("utf-8")
            b = bytes(v)
            if len(b) > size:
                raise ValueError(f"{'.'.join(map(str, path))}: {len(b)} bytes do not fit the {size}-byte field")
            out[off:off + len(b)] = b
        else:
            out[off:off + size] = struct.pack(fmt, v)
    return bytes(out)


def string_value(raw):
    """Game reads strings as UTF-8 and trims NULs."""
    return raw.decode("utf-8", errors="replace").strip("\x00")


def string_bytes(s, size):
    b = s.encode("utf-8")
    if len(b) > size:
        raise ValueError(f"string of {len(b)} UTF-8 bytes does not fit a {size}-byte field: {s[:40]!r}")
    return b + bytes(size - len(b))
