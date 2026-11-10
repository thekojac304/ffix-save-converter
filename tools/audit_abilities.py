"""Audit support-ability (sa), AP (pa) and magic-stone (capa) consistency against the
vanilla game's own rules, on every PS1 and PC fixture.

Rules (vanilla ff9play.FF9Play_UpdateSA / ff9abil):
  A  cur.capa == max.capa - sum(sa_capa[i] for each set bit i)       (gem budget)
  B  every set bit i has ability id 192+i in the character's PA table (learnable)
  C  pa[j] <= AP required by PA table slot j                          (AP saturates)
A wrong sa bit order or a shifted pa array makes these fail on most records.

Needs research/vanilla_extracts/abilities.json (extracted locally from the installed game).
Usage: python -P tools/audit_abilities.py [--json out.json]
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ffix_conv import model, pc_container, ps1_card, ps1_save  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TABLES = os.path.join(ROOT, "research/vanilla_extracts/abilities.json")


def load_tables():
    t = json.load(open(TABLES))
    return t["sa_capa"], t["pa_table_by_menu_type"]


def check_player(p, sa_capa, patab):
    bits = [i for i in range(64) if (p["sa"][i >> 5] >> (i & 31)) & 1]
    used = sum(sa_capa[i] for i in bits)
    mt = p["info"]["menu_type"]
    table = patab[mt] if mt < len(patab) else []
    ids = {a for a, _ in table}
    res = {
        "A_budget": p["max"]["capa"] - p["cur"]["capa"] == used,
        "B_learnable": all(192 + i in ids for i in bits),
        "C_ap_bounds": all(p["pa"][j] <= table[j][1] for j in range(min(48, len(table)))),
        "bits": len(bits),
    }
    return res


def corpus():
    files = sorted(glob.glob(os.path.join(ROOT, "fixtures/ps1/extracted/*/*/*.mcr")))
    files += sorted(glob.glob(os.path.join(ROOT, "fixtures/ps1/originals/user_retroarch/*.srm")))
    for f in files:
        _, es = ps1_card.parse_file(open(f, "rb").read())
        for e in es:
            s = ps1_save.PS1Save(e.data, e.product_code, e.filename)
            yield "ps1", f"{os.path.basename(os.path.dirname(f))}/{os.path.basename(f)}#{e.block_index}", model.from_ps1(s)
    for f in sorted(glob.glob(os.path.join(ROOT, "fixtures/pc/originals/*/*.*"))):
        try:
            c = pc_container.Container(open(f, "rb").read())
        except pc_container.ContainerError:
            continue
        for sl in c.occupied():
            yield "pc", f"{os.path.basename(f)}:{sl[0] + 1}/{sl[1] + 1}", model.from_pc(c.slot_tree(*sl))


def main():
    sa_capa, patab = load_tables()
    stats = {}
    fails = []
    for plat, name, m in corpus():
        for i, p in enumerate(m["players"]):
            if p["level"] <= 1 and not any(p["pa"]) and not any(p["sa"]):
                continue
            r = check_player(p, sa_capa, patab)
            st = stats.setdefault(plat, {"records": 0, "with_sa": 0, "A_budget": 0, "B_learnable": 0, "C_ap_bounds": 0})
            st["records"] += 1
            st["with_sa"] += r["bits"] > 0
            for k in ("A_budget", "B_learnable", "C_ap_bounds"):
                st[k] += r[k]
                if not r[k]:
                    fails.append((plat, name, i, k, p["cur"]["capa"], p["max"]["capa"], r["bits"]))
    print(json.dumps(stats, indent=1))
    for f in fails[:40]:
        print("FAIL", f)
    if "--json" in sys.argv:
        json.dump({"stats": stats, "failures": fails}, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)


if __name__ == "__main__":
    main()


# ---- rule D: stat-growth bonus ------------------------------------------------------
# vanilla ff9level: basis.dex = base + lv/10 + (bonus.dex>>5) (cap 50); str/mgc: lv*3/10 (cap 99);
# wpr: lv*3/20 (cap 50); max.capa = base + lv*4/10 + (bonus.cap>>5) (cap 99).
# The per-character base must come out identical in every save if bonus is mapped correctly.
LEVEL_TERMS = {"dex": (lambda lv: lv // 10, 50), "str": (lambda lv: lv * 3 // 10, 99),
               "mgc": (lambda lv: lv * 3 // 10, 99), "wpr": (lambda lv: lv * 3 // 20, 50)}


def implied_bases(p):
    out = {}
    lv = p["level"]
    for k, (term, cap) in LEVEL_TERMS.items():
        if p["basis"][k] < cap:
            out[k] = p["basis"][k] - term(lv) - (p["bonus"][k] >> 5)
    if p["max"]["capa"] < 99:
        out["cap"] = p["max"]["capa"] - lv * 4 // 10 - (p["bonus_cap"] >> 5)
    return out


def audit_bonus():
    seen = {}
    for plat, name, m in corpus():
        for i, p in enumerate(m["players"]):
            for k, v in implied_bases(p).items():
                seen.setdefault((p["info"]["menu_type"], k), {}).setdefault(v, []).append(f"{plat}:{name}:{i}")
    bad = {key: {v: len(n) for v, n in vals.items()} for key, vals in seen.items() if len(vals) > 1}
    return len(seen), bad


if __name__ == "__main__" and "--bonus" in sys.argv:
    n, bad = audit_bonus()
    print(f"bonus rule D: {n} (character, stat) groups, {len(bad)} inconsistent")
    for k, v in sorted(bad.items()):
        print("  ", k, v)
