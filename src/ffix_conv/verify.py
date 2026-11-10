"""Independent verification of a conversion, and the severity-graded compatibility report.

verify: both files are parsed from disk by the normal readers (nothing from the conversion
step is trusted) and every shared gameplay field is compared. Each difference is classified:
  equal            identical
  normalized       differs only by a documented representation rule (listed in NORMALIZATIONS)
  unexpected       anything else -> verification fails
"""
import base64

PLAYER_FIELDS = ("name", "category", "level", "exp", "cur", "max", "trance", "web_bone", "elem", "defence",
                 "basis", "info", "status", "equip", "bonus", "pa", "sa")
NORMALIZATIONS = {
    "party.slot": "empty party position: 9 on PS1, 255 on PC",
    "state.world": "before the first world-map visit PS1 stores wldMapNo/wldLocNo 9009/68, PC stores 0/0",
    "bonus_cap": "PC stores 0 to mean 'derive'; PS1 needs the derived value (level-1)*5 (+extra for serial 10/11)",
    "cards": "PS1 keeps gaps between Tetra Master cards; PC packs them (same cards, same order)",
    "playtime": "PS1 counts frames (1/60 s NTSC, 1/50 s PAL); PC counts seconds",
}


def _derived_cap(p):
    cap = (p["level"] - 1) * 5
    if p["info"]["serial_no"] in (10, 11):
        cap += next((t for t in (10, 20, 30, 40, 50, 60, 70, 80, 90) if p["level"] <= t), 99)
    return cap


def compare(a, b):
    """Compare two canonical models (any platforms). Returns a list of findings."""
    out = []

    def add(field, va, vb, status, note=""):
        out.append({"field": field, "source": va, "converted": vb, "status": status, "note": note})

    pa, pb = a["source"]["platform"], b["source"]["platform"]
    # state
    for k in ("mode", "prevMode", "fldMapNo", "fldLocNo", "btlMapNo", "btlSubMapNo"):
        add(f"state.{k}", a["state"][k], b["state"][k], "equal" if a["state"][k] == b["state"][k] else "unexpected")
    wa = (a["state"]["wldMapNo"], a["state"]["wldLocNo"])
    wb = (b["state"]["wldMapNo"], b["state"]["wldLocNo"])
    if wa == wb:
        add("state.wldMapNo/wldLocNo", wa, wb, "equal")
    elif {wa, wb} == {(0, 0), (9009, 68)} and pa != pb:
        add("state.wldMapNo/wldLocNo", wa, wb, "normalized", NORMALIZATIONS["state.world"])
    else:
        add("state.wldMapNo/wldLocNo", wa, wb, "unexpected")
    # event variables (story)
    ga = base64.b64decode(a["event"]["gEventGlobal_b64"])
    gb = base64.b64decode(b["event"]["gEventGlobal_b64"])
    diff = [i for i in range(len(ga)) if ga[i] != gb[i]]
    add("event.gEventGlobal", f"scenario {a['event']['scenario_counter']}", f"scenario {b['event']['scenario_counter']}",
        "equal" if not diff and len(ga) == len(gb) else "unexpected",
        "" if not diff else f"{len(diff)} bytes differ, first at offset {diff[0]}")
    # party, inventory
    sa = [None if x in (9, 255) else x for x in a["party"]["slot"]]
    sb = [None if x in (9, 255) else x for x in b["party"]["slot"]]
    if a["party"]["slot"] == b["party"]["slot"]:
        add("party.slot", a["party"]["slot"], b["party"]["slot"], "equal")
    else:
        add("party.slot", a["party"]["slot"], b["party"]["slot"], "normalized" if sa == sb else "unexpected",
            NORMALIZATIONS["party.slot"] if sa == sb else "")
    for k in ("escape_no", "summon_flag", "gil", "frog_no", "steal_no", "dragon_no"):
        add(f"party.{k}", a["party"][k], b["party"][k], "equal" if a["party"][k] == b["party"][k] else "unexpected")
    add("items", f"{sum(1 for x in a['items'] if x['count'])} stacks", f"{sum(1 for x in b['items'] if x['count'])} stacks",
        "equal" if a["items"] == b["items"] else "unexpected")
    add("key_items", "", "", "equal" if a["rare_items"] == b["rare_items"] else "unexpected")
    # characters
    for i, (x, y) in enumerate(zip(a["players"], b["players"])):
        bad = [k for k in PLAYER_FIELDS if x[k] != y[k]]
        add(f"players[{i}] {x['name']}", "", "", "unexpected" if bad else "equal",
            f"differs: {', '.join(bad)}" if bad else "")
        ca, cb = x.get("bonus_cap", 0), y.get("bonus_cap", 0)
        if ca == cb:
            add(f"players[{i}].bonus_cap", ca, cb, "equal")
        elif (ca == 0 and cb == _derived_cap(y)) or (cb == 0 and ca == _derived_cap(x)):
            add(f"players[{i}].bonus_cap", ca, cb, "normalized", NORMALIZATIONS["bonus_cap"])
        else:
            add(f"players[{i}].bonus_cap", ca, cb, "unexpected")
    # Tetra Master
    key = lambda c: (c["id"], c["arrow"], c["atk"], c["type"], c["pdef"], c["mdef"])
    ka = [key(c) for c in a["minigame"]["cards"] if c["id"] != 255]
    kb = [key(c) for c in b["minigame"]["cards"] if c["id"] != 255]
    full_a = [key(c) for c in a["minigame"]["cards"]]
    full_b = [key(c) for c in b["minigame"]["cards"]]
    if full_a == full_b:
        add("cards", f"{len(ka)} cards", f"{len(kb)} cards", "equal")
    else:
        add("cards", f"{len(ka)} cards", f"{len(kb)} cards", "normalized" if ka == kb else "unexpected",
            NORMALIZATIONS["cards"] if ka == kb else "")
    for k in ("sWin", "sLose", "sDraw"):
        add(f"cards.{k}", a["minigame"][k], b["minigame"][k], "equal" if a["minigame"][k] == b["minigame"][k] else "unexpected")
    # playtime
    ta, tb = a["playtime_seconds"], b["playtime_seconds"]
    if ta == tb:
        add("playtime", round(ta, 2), round(tb, 2), "equal")
    else:
        add("playtime", round(ta, 2), round(tb, 2), "normalized" if abs(ta - tb) <= 1 / 50 else "unexpected",
            NORMALIZATIONS["playtime"] if abs(ta - tb) <= 1 / 50 else "")
    return out


def summarize(findings):
    counts = {"equal": 0, "normalized": 0, "unexpected": 0}
    for f in findings:
        counts[f["status"]] += 1
    return counts


# ---- compatibility report -----------------------------------------------------------------
SEVERITIES = ("fully_preserved", "safely_transformed", "defaulted", "unsupported_or_lossy", "conversion_blocking")


def _plain(x):
    """Readable text for a report entry; nested dicts become their key names (details are listed separately)."""
    if isinstance(x, dict):
        return "; ".join(k.replace("_", " ") for k in x)
    return str(x)


def compat_report(direction, rep, extra_lossy=()):
    """Group a conversion's report into severity levels. rep is the dict from Report.as_dict()
    (PS1->PC) or ps1_writer.build_block (PC->PS1)."""
    if direction == "ps1->pc":
        levels = {
            "fully_preserved": list(rep.get("mapped", [])),
            "safely_transformed": list(rep.get("transformed", [])),
            "defaulted": list(rep.get("defaulted", [])),
            "unsupported_or_lossy": [_plain(x) for x in rep.get("dropped_or_unmapped", [])] + list(extra_lossy),
            "conversion_blocking": list(rep.get("errors", [])),
        }
    else:
        levels = {
            "fully_preserved": list(rep.get("written", [])),
            "safely_transformed": list(rep.get("transformed", [])),
            "defaulted": list(rep.get("generated", [])) + [f"zero-filled PS1-only region {z}" for z in rep.get("zero_filled", [])],
            "unsupported_or_lossy": list(rep.get("dropped", [])) + list(extra_lossy),
            "conversion_blocking": [],
        }
    levels["warnings"] = list(rep.get("warnings", []))
    return levels
