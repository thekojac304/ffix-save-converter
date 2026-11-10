"""Convert every PS1 fixture; write a summary report and a runtime test kit.

Outputs (derived from third-party saves: keep out of public commits):
  reports/batch_conversion_summary.json
  reports/runtime_test_kit/<checkpoint>/SavedData_ww.dat   one converted save in slot 1 file 1
  reports/runtime_test_kit/all_checkpoints/SavedData_ww.dat  ten checkpoints in slot 1 files 1-10 (subset)
Existing outputs are never overwritten; delete the folder yourself to regenerate.

Usage: python -P tools/batch_convert.py
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ffix_conv import convert, model, pc_container, ps1_card, ps1_save  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KIT = os.path.join(ROOT, "reports", "runtime_test_kit")
# Checkpoints chosen for the runtime protocol: early, each disc start, cross-platform pairs, late game.
KIT_PICKS = [1, 2, 8, 15, 20, 32, 41, 49, 50, 53]
FIXED_TS = 1700000000.0


def write_new(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "xb") as f:
        f.write(data)


def main():
    rows, combined = [], convert.blank_container()
    for path in sorted(glob.glob(os.path.join(ROOT, "fixtures/ps1/extracted/fantasyanime/*/*.mcr"))):
        name = os.path.basename(os.path.dirname(path))
        _, entries = ps1_card.parse_file(open(path, "rb").read())
        e = entries[0]
        s = ps1_save.PS1Save(e.data, e.product_code, e.filename)
        m = model.from_ps1(s)
        row = {"fixture": name, "scenario": m["event"]["scenario_counter"], "location": m["preview"]["location"],
               "state": m["state"]}
        try:
            tree, rep = convert.to_pc_tree(m)
            pv = convert.preview_for(tree, m, FIXED_TS)
            single = convert.insert(convert.blank_container(), 0, 0, tree, pv)
            out = single.to_bytes()
            back = model.from_pc(pc_container.Container(out).slot_tree(0, 0))
            row.update(ok=True, warnings=rep.warnings, defaulted=len(rep.defaulted),
                       semantic_round_trip=back["event"] == {**m["event"], "gStepCount": 0} and back["state"] == m["state"])
            n = int(name[7:9])
            if n in KIT_PICKS:
                target = os.path.join(KIT, name, "SavedData_ww.dat")
                if not os.path.exists(target):
                    write_new(target, out)
                    with open(os.path.join(KIT, name, "conversion_report.json"), "x", encoding="utf-8") as fh:
                        json.dump({"fixture": name, **rep.as_dict()}, fh, indent=1, default=str)
                convert.insert(combined, 0, KIT_PICKS.index(n), tree,
                               convert.preview_for(tree, m, FIXED_TS + KIT_PICKS.index(n)))
        except convert.ConversionError as ex:
            row.update(ok=False, error=str(ex))
        rows.append(row)
        print(("OK  " if row["ok"] else "ERR ") + f"{name:34} sc={row['scenario']:5} {row['location']}")
    target = os.path.join(KIT, "all_checkpoints", "SavedData_ww.dat")
    if not os.path.exists(target):
        write_new(target, combined.to_bytes())
    with open(os.path.join(ROOT, "reports/batch_conversion_summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"converted": sum(r["ok"] for r in rows), "total": len(rows), "rows": rows}, fh, indent=1)
    print(f"{sum(r['ok'] for r in rows)}/{len(rows)} converted")


if __name__ == "__main__":
    main()
