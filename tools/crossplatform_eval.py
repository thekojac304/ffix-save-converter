"""Cross-platform evidence report.

For every PC fixture slot, rank all PS1 fixtures by gEventGlobal byte similarity
and compare scenario counters, map state, and party. Writes
reports/crossplatform_pairs.json and prints a table.

Usage: python -P tools/crossplatform_eval.py
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ffix_conv import model, pc_container, ps1_card, ps1_save  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def ps1_corpus():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "fixtures/ps1/extracted/*/*/*"))):
        if f.lower().endswith(".txt"):
            continue
        try:
            _, entries = ps1_card.parse_file(open(f, "rb").read())
        except ps1_card.CardError:
            continue
        for e in entries:
            if e.data[:2] == b"SC" and ps1_save.REGIONS.get(e.product_code[:12]):
                s = ps1_save.PS1Save(e.data, e.product_code, e.filename)
                out.append((os.path.relpath(f, ROOT).replace("\\", "/"), e.block_index, model.from_ps1(s)))
    return out


def pc_corpus():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "fixtures/pc/originals/*/*SavedData_ww.dat"))):
        c = pc_container.Container(open(f, "rb").read())
        for slot, save in c.occupied():
            out.append((os.path.relpath(f, ROOT).replace("\\", "/"), (slot + 1, save + 1),
                        c.preview(slot, save).location, model.from_pc(c.slot_tree(slot, save))))
    return out


def main():
    ps1, pcs = ps1_corpus(), pc_corpus()
    rows = []
    for f, sl, loc, m in pcs:
        g = model.gevent_bytes(m)
        ranked = sorted(((sum(a == b for a, b in zip(g, model.gevent_bytes(p))), pf, p) for pf, _, p in ps1),
                        key=lambda x: -x[0])
        best_sim, best_f, best = ranked[0]
        rows.append({
            "pc_file": f, "pc_slot": sl, "pc_location": loc, "pc_scenario": m["event"]["scenario_counter"],
            "pc_state": m["state"], "best_ps1": best_f, "best_ps1_location": best["preview"]["location"],
            "best_ps1_scenario": best["event"]["scenario_counter"], "gevent_identical_bytes": best_sim,
            "second_best_identical_bytes": ranked[1][0],
            "scenario_delta": best["event"]["scenario_counter"] - m["event"]["scenario_counter"],
            "same_field": best["state"]["fldMapNo"] == m["state"]["fldMapNo"],
            "ps1_state": best["state"],
        })
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports/crossplatform_pairs.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    for r in rows:
        print(f"{r['pc_location'][:26]:26} sc={r['pc_scenario']:5} <-> {os.path.basename(os.path.dirname(r['best_ps1']))[:26]:26} "
              f"sc={r['best_ps1_scenario']:5} d={r['scenario_delta']:5} same={r['gevent_identical_bytes']:4}/2048 "
              f"(2nd {r['second_best_identical_bytes']}) field_eq={r['same_field']}")


if __name__ == "__main__":
    main()
