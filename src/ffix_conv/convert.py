"""Canonical model -> vanilla PC slot tree, plus a conversion report.

Rules for values the PS1 save does not provide are explicit (see FIELD_MAP and
DEFAULT_SETTINGS); nothing is guessed silently, and every defaulted or dropped
value is listed in the report.
"""
import base64
import copy
import struct

from . import model, pc_container, pc_schema
from .ps1_save import PARTY_NONE_PS1

PC_PARTY_NONE = 255
PC_CARD_CPOINT = 10        # observed for all 100 card IDs across every PC fixture
PC_EMPTY_CARD = {"id": 255, "side": 255, "atk": 255, "type": 255, "pdef": 255, "mdef": 255, "cpoint": 255, "arrow": 255}
PC_CARD_SLOTS = 100

# Used only when no PC template slot is supplied: the vanilla FF9CFG constructor values and
# HonoInputManager default key/joystick bindings (vanilla Assembly-CSharp, build 5378074).
# Every real PC fixture except one stores exactly these bindings.
DEFAULT_SETTINGS = {
    "cfg": {"sound": 0, "sound_effect": 0, "control": 0, "cursor": 0, "atb": 1, "camera": 0, "move": 0,
            "vibe": 1, "btl_speed": 1, "fld_msg": 3, "here_icon": 0, "win_type": 0, "target_win": 0,
            "control_data": 0, "skip_btl_camera": 1,
            "control_data_keyboard": [120, 99, 118, 98, 103, 104, 102, 106, 8, 49],
            "control_data_joystick": ["JoystickButton1", "JoystickButton0", "JoystickButton3", "JoystickButton2",
                                      "JoystickButton4", "JoystickButton5", "LeftTrigger", "RightTrigger",
                                      "JoystickButton7", "JoystickButton6"]},
    "time": -1.0,
}
# Achievement lists the game pads with -1 ("empty"); vanilla adds every other value to a set.
EMPTY_MINUS_ONE = ("abilities", "passiveAbilities", "QuadmistWinList")
DEFAULT_WORLD = {"data.cameraState.rotationMax": 0.0, "data.cameraState.upperCounter": 0,
                 "data.cameraState.upperCounterSpeed": 0, "data.cameraState.upperCounterForce": False,
                 "data.cameraState.rotation": 0.0, "data.cameraState.rotationRev": 0.0, "data.hintmap": 0}


class ConversionError(ValueError):
    pass


def _zero_tree(schema):
    if isinstance(schema, dict):
        return {k: _zero_tree(v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_zero_tree(s) for s in schema]
    if schema in ("s128", "s4k"):
        return bytes(pc_schema.TYPES[schema][1])
    if schema == "bool":
        return False
    if schema in ("f32", "f64"):
        return 0.0
    return 0


def blank_tree():
    """A fully populated PC slot tree with every leaf zero/empty."""
    return _zero_tree(pc_schema.SCHEMA)


def _encode_strings(obj, schema):
    """Encode Python str leaves to the fixed-size byte fields."""
    if isinstance(schema, dict):
        for k, s in schema.items():
            obj[k] = _encode_strings(obj[k], s)
        return obj
    if isinstance(schema, list):
        return [_encode_strings(o, s) for o, s in zip(obj, schema)]
    if schema in ("s128", "s4k") and isinstance(obj, str):
        return pc_schema.string_bytes(obj, pc_schema.TYPES[schema][1])
    return obj


class Report:
    def __init__(self):
        self.mapped, self.transformed, self.defaulted, self.dropped, self.warnings, self.errors = [], [], [], [], [], []

    def as_dict(self):
        return {"mapped": self.mapped, "transformed": self.transformed, "defaulted": self.defaulted,
                "dropped_or_unmapped": self.dropped, "warnings": self.warnings, "errors": self.errors}


def to_pc_tree(m, template_tree=None, strict=True):
    """Return (tree, report). template_tree supplies settings/world camera only."""
    rep = Report()
    src = m["source"]
    if src.get("platform") == "ps1":
        if not src.get("crc_ok"):
            msg = f"PS1 CRC mismatch (stored {src['crc_stored']:#06x}, computed {src['crc_computed']:#06x})"
            (rep.errors if strict else rep.warnings).append(msg)
        if src.get("region") not in ("NTSC-U", "PAL"):
            msg = (f"region {src.get('region')!r} ({src.get('product_code')!r}) not validated; "
                   "Japanese text encoding is unsupported")
            (rep.errors if strict else rep.warnings).append(msg)
        if src.get("region") == "PAL":
            rep.warnings.append("PAL layout assumed identical to NTSC-U; no PAL fixture was available to verify")
        for i, p in enumerate(m["players"]):
            if not p.get("name_fully_decoded", True):
                msg = f"player {i}: name contains bytes outside the PS1 text table: {p['name']!r}"
                (rep.errors if strict else rep.warnings).append(msg)
    if rep.errors:
        raise ConversionError("; ".join(rep.errors))

    t = blank_tree()
    d = t["Data"]

    # --- state -------------------------------------------------------------
    for k, v in m["state"].items():
        d["10000_State"][k] = v
    rep.mapped.append("state: mode, prevMode, fldMapNo, fldLocNo, btlMapNo, btlSubMapNo, wldMapNo, wldLocNo")
    d["10000_State"].update(timeCounter=0.0, timerControl=False, timerDisplay=False)
    rep.defaulted.append("state.timeCounter=0.0, timerControl=False, timerDisplay=False (PS1 location unknown)")

    # --- event ---------------------------------------------------------------
    g = model.gevent_bytes(m)
    if len(g) != 2048:
        raise ConversionError(f"gEventGlobal must be 2048 bytes, got {len(g)}")
    d["20000_Event"]["gEventGlobal"] = pc_schema.string_bytes(base64.b64encode(g).decode("ascii"), 4096)
    d["20000_Event"]["gStepCount"] = 0
    rep.transformed.append(f"event.gEventGlobal (2048 bytes, scenario counter {m['event']['scenario_counter']}) -> base64")
    rep.defaulted.append("event.gStepCount=0 (PC never tracks steps)")

    # --- players -------------------------------------------------------------
    for i, p in enumerate(m["players"]):
        dst = d["40000_Common"]["players"][i]
        for k in ("category", "level", "exp", "trance", "web_bone", "status"):
            dst[k] = p[k]
        for k in ("cur", "max", "elem", "defence", "basis", "info", "bonus"):
            dst[k] = dict(p[k])
        dst["equip"] = list(p["equip"])
        dst["pa"] = list(p["pa"])
        dst["sa"] = list(p["sa"])
        dst["name"] = p["name"]
        d["94000_Common"]["00001_player_bonus"][i] = p["bonus_cap"]
        if "_ps1_unmapped" in p and any(v not in (0, "0000", "0" * 32) for v in p["_ps1_unmapped"].values()):
            rep.dropped.append(f"player {i}: unmapped PS1 bytes {p['_ps1_unmapped']}")
    rep.mapped.append("players[9]: all PC PLAYER fields (category..sa) + bonus cap")
    rep.transformed.append("players[].name: PS1 text -> UTF-8; players[].info: PS1 bitfields -> 6 fields")

    # --- party / inventory -----------------------------------------------------
    pty = m["party"]
    d["40000_Common"]["slot"] = [PC_PARTY_NONE if s == PARTY_NONE_PS1 and src.get("platform") == "ps1" else s
                                 for s in pty["slot"]]
    for s in d["40000_Common"]["slot"]:
        if s != PC_PARTY_NONE and not 0 <= s < 9:
            raise ConversionError(f"invalid party slot value {s}")
    for k in ("escape_no", "summon_flag", "gil", "frog_no", "steal_no", "dragon_no"):
        d["40000_Common"][k] = pty[k]
    d["40000_Common"]["items"] = [{"id": x["id"], "count": x["count"]} for x in m["items"]]
    d["40000_Common"]["rareItems"] = list(m["rare_items"])
    rep.mapped.append("party counters, gil, 256 items, 64 rare-item bytes")
    rep.transformed.append(f"party.slot {pty['slot']} -> {d['40000_Common']['slot']}")

    # --- Tetra Master --------------------------------------------------------------
    mg = d["30000_MiniGame"]
    for k in ("sWin", "sLose", "sDraw"):
        mg[k] = m["minigame"][k]
    cards = [c for c in m["minigame"]["cards"] if c["id"] != 255]
    if len(cards) > PC_CARD_SLOTS:
        raise ConversionError(f"{len(cards)} Tetra Master cards; the PC save holds at most {PC_CARD_SLOTS}")
    for c in cards:
        if c["id"] >= 100 or c["type"] > 3:
            raise ConversionError(f"invalid Tetra Master card {c}")
    mg["MiniGameCard"] = [{"id": c["id"], "side": 0, "atk": c["atk"], "type": c["type"], "pdef": c["pdef"],
                           "mdef": c["mdef"], "cpoint": PC_CARD_CPOINT, "arrow": c["arrow"]} for c in cards]
    mg["MiniGameCard"] += [dict(PC_EMPTY_CARD) for _ in range(PC_CARD_SLOTS - len(cards))]
    rep.transformed.append(f"{len(cards)} Tetra Master cards compacted; side=0, cpoint=10, empty=all-255")

    # --- playtime / settings / world ---------------------------------------------------
    d["95000_Setting"]["00001_time"] = float(m["playtime_seconds"])
    rep.transformed.append(f"playtime {m['playtime_seconds']:.1f}s")
    if template_tree is not None:
        td = template_tree["Data"]
        d["50000_Setting"] = copy.deepcopy(td["50000_Setting"])
        d["70000_World"] = copy.deepcopy(td["70000_World"])
        rep.defaulted.append("settings.cfg and world camera copied from PC template slot")
    else:
        s = copy.deepcopy(DEFAULT_SETTINGS)
        d["50000_Setting"] = s
        d["70000_World"] = dict(DEFAULT_WORLD)
        rep.defaulted.append("settings.cfg = documented defaults; world camera = 0 (no template slot)")
    d["50000_Setting"]["time"] = -1.0
    d["60000_Sound"]["auto_save_bgm_id"] = -1
    for k in EMPTY_MINUS_ONE:
        d["80000_Achievement"][k] = [-1] * len(d["80000_Achievement"][k])
    rep.defaulted.append("achievement counters/flags and reserved buffers = 0; achievement lists "
                         "(abilities, passiveAbilities, QuadmistWinList) = -1 as the game writes them; "
                         "sound.auto_save_bgm_id = -1; settings.time = -1")

    if m.get("unmapped"):
        rep.dropped.append({"ps1_unknown_regions_not_written": m["unmapped"]})
    _encode_strings(t, pc_schema.SCHEMA)
    pc_schema.encode(t)   # validates every value fits its type
    return t, rep


def preview_for(tree, m, timestamp):
    d = tree["Data"]
    cm = d["40000_Common"]
    party = []
    for s in cm["slot"]:
        if s == PC_PARTY_NONE:
            party.append(None)
            continue
        p = cm["players"][s]
        party.append((p["info"]["serial_no"], p["level"], pc_schema.string_value(p["name"])))
    loc = (m.get("preview") or {}).get("location") or "Unknown"
    return pc_container.Preview(True, cm["gil"], int(d["95000_Setting"]["00001_time"]),
                                d["50000_Setting"]["cfg"]["win_type"], loc, party, float(timestamp))


def blank_container(language=-1):
    """A vanilla-format SavedData_ww.dat with every slot empty, built from the
    documented layout (Memoria CreateFileIfDoesNotExist)."""
    from . import pc_crypto
    raw = bytearray(pc_container.CONTAINER_SIZE)
    meta = pc_container.Metadata(1.0, pc_schema.DATA_SIZE, -1, -1, -1.0, 0, language, 0, 0, 0,
                                 reserved=bytes(pc_container.META_PLAIN - 39))
    c = pc_crypto.encrypt(meta.build())
    raw[0:len(c)] = c
    ep = pc_crypto.encrypt(b"NONE" + bytes(pc_container.PREVIEW_PLAIN - 4))
    for i in range(pc_container.TOTAL_SAVES):
        o = pc_container.META_RESERVED + i * pc_container.PREVIEW_RESERVED
        raw[o:o + len(ep)] = ep
    eb = pc_crypto.encrypt(b"NONE" + bytes(pc_schema.SLOT_PLAIN_SIZE - 4))
    for i in range(pc_container.TOTAL_SAVES + 1):
        o = pc_container.BASE_BLOCK + i * pc_container.BLOCK_RESERVED
        raw[o:o + len(eb)] = eb
    return pc_container.Container(bytes(raw))


def insert(container, slot, save, tree, preview, overwrite=False, set_latest=True):
    """Write a converted slot into an in-memory container (never touches disk)."""
    if container.slot_plain(slot, save) is not None and not overwrite:
        raise ConversionError(f"PC slot {slot + 1} file {save + 1} is occupied; refusing to overwrite")
    container.put_slot(slot, save, tree, preview)
    if set_latest:
        meta = copy.copy(container.meta)
        meta.latest_slot, meta.latest_save, meta.latest_timestamp = slot, save, preview.timestamp
        container.set_metadata(meta)
    return container
