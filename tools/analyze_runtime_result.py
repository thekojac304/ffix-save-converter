"""Analyse the SavedData_ww.dat the PC game wrote during a runtime test.

Compares every slot the game (re)wrote against the converted checkpoint it came from, and
lists fields the game changed. Changes in progression fields after only loading and saving
(no play) would indicate the game rejected or "repaired" converted data, e.g. support abilities
cleared by PLAYER.ValidateSupportAbility, or stats rebuilt by ValidateMaxStone.

Usage: python -P tools/analyze_runtime_result.py <runtime_test_package dir> [after-test .dat]
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ffix_conv import model, pc_container  # noqa: E402

PLAYER_KEYS = ("name", "level", "exp", "max", "elem", "defence", "basis", "info", "equip", "bonus", "bonus_cap", "pa", "sa")


def diff_models(a, b):
    out = []
    if a["event"]["scenario_counter"] != b["event"]["scenario_counter"]:
        out.append(f"scenario {a['event']['scenario_counter']} -> {b['event']['scenario_counter']}")
    ga, gb = model.gevent_bytes(a), model.gevent_bytes(b)
    nd = sum(x != y for x, y in zip(ga, gb))
    if nd:
        out.append(f"gEventGlobal: {nd} bytes changed")
    for k in ("fldMapNo", "fldLocNo", "wldMapNo", "mode"):
        if a["state"][k] != b["state"][k]:
            out.append(f"state.{k} {a['state'][k]} -> {b['state'][k]}")
    for k in ("slot", "gil", "frog_no", "steal_no", "dragon_no", "escape_no"):
        if a["party"][k] != b["party"][k]:
            out.append(f"party.{k} {a['party'][k]} -> {b['party'][k]}")
    if a["items"] != b["items"]:
        out.append("inventory changed")
    if a["rare_items"] != b["rare_items"]:
        out.append("key items changed")
    for i, (p, q) in enumerate(zip(a["players"], b["players"])):
        for k in PLAYER_KEYS:
            if p[k] != q[k]:
                out.append(f"player {i} ({p['name']}).{k}: {p[k]} -> {q[k]}")
    return out


def main(pkg, after=None):
    orig = pc_container.Container(open(os.path.join(pkg, "PC/SavedData_ww.dat"), "rb").read())
    if after is None:
        cands = sorted(glob.glob(os.path.join(pkg, "results/SavedData_ww.after-test-*.dat")))
        if not cands:
            raise SystemExit("no results/SavedData_ww.after-test-*.dat found; run collect_and_restore.ps1 first")
        after = cands[-1]
    new = pc_container.Container(open(after, "rb").read())
    report = {"after_file": after, "metadata": {k: v for k, v in vars(new.meta).items() if k != "reserved"},
              "slots": []}
    converted = {sl: model.from_pc(orig.slot_tree(*sl)) for sl in orig.occupied()}
    for sl in new.occupied():
        m = model.from_pc(new.slot_tree(*sl))
        rec = {"slot": f"{sl[0] + 1}/{sl[1] + 1}", "location": new.preview(*sl).location,
               "scenario": m["event"]["scenario_counter"], "playtime_h": round(m["playtime_seconds"] / 3600, 3)}
        if sl in converted and new.slot_plain(*sl) == orig.slot_plain(*sl):
            rec["status"] = "untouched converted slot"
        else:
            # match to the converted checkpoint this save most likely continues from
            base_sl = min(converted, key=lambda k: (converted[k]["playtime_seconds"] > m["playtime_seconds"] + 1,
                                                    abs(converted[k]["event"]["scenario_counter"] - m["event"]["scenario_counter"]),
                                                    abs(converted[k]["playtime_seconds"] - m["playtime_seconds"])))
            base = converted[base_sl]
            rec.update(status="written by the PC game", continues_from=f"{base_sl[0] + 1}/{base_sl[1] + 1}",
                       played_seconds=round(m["playtime_seconds"] - base["playtime_seconds"], 1),
                       changes=diff_models(base, m))
        report["slots"].append(rec)
    out = os.path.join(pkg, "results", "analysis.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, default=str)
    for r in report["slots"]:
        print(r["slot"], r["status"], r["location"], r.get("continues_from", ""), r.get("played_seconds", ""))
        for c in r.get("changes", [])[:30]:
            print("    ", c)
    print("written", out)


if __name__ == "__main__":
    main(*sys.argv[1:3])
