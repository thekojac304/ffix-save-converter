"""Generate fixtures/manifest.json: one record per original file and per save slot.

Usage: python -P tools/build_manifest.py
"""
import datetime
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ffix_conv import model, pc_container, ps1_card, ps1_save  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NAMES = ["Zidane", "Vivi", "Garnet", "Steiner", "Freya", "Quina", "Eiko", "Amarant", "Beatrix/slot8"]

# Story milestones (requested coverage targets) -> scenario counter ranges, from FantasyAnime
# descriptions and the scenario counters observed in those saves.
MILESTONES = [
    ("Opening Alexandria", 0, 1999), ("Evil Forest", 2000, 2399), ("Ice Cavern / Dali", 2400, 2999),
    ("Lindblum", 3000, 3699), ("Burmecia", 3700, 3999), ("Beginning of Disc 2", 4000, 4299),
    ("Treno / Gargan Roo", 4300, 4599), ("Cleyra", 4600, 4999), ("Alexandria rescue", 5000, 5499),
    ("Outer Continent", 5500, 6099), ("Black Mage Village", 6100, 6299), ("Madain Sari / Iifa", 6300, 6989),
    ("Beginning of Disc 3", 6990, 7599), ("Disc 3 Alexandria / Treno", 7600, 9399),
    ("Desert Palace / Oeilvert", 9400, 9899), ("Gulug", 9900, 10399), ("Ipsen's Castle", 10400, 10699),
    ("Terra / Bran Bal / Pandemonium", 10700, 10994), ("Beginning of Disc 4", 10995, 11099),
    ("Disc 4 open world", 11100, 11599), ("Memoria / final dungeon", 11600, 11800),
]


def milestone(sc):
    return [n for n, lo, hi in MILESTONES if lo <= sc <= hi]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def provenance():
    out = {}
    p = os.path.join(ROOT, "fixtures/provenance.jsonl")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            if r.get("ok"):
                out[r["stored_as"]] = r
    return out


def summarize(m):
    party = [NAMES[s] if s < 9 else None for s in m["party"]["slot"]]
    return {
        "scenario_counter": m["event"]["scenario_counter"], "milestones": milestone(m["event"]["scenario_counter"]),
        "state": m["state"], "party": party,
        "levels": {NAMES[i]: p["level"] for i, p in enumerate(m["players"])},
        "exp": {NAMES[i]: p["exp"] for i, p in enumerate(m["players"])},
        "names": [p["name"] for p in m["players"]],
        "gil": m["party"]["gil"], "playtime_hours": round(m["playtime_seconds"] / 3600, 2),
        "item_kinds": sum(1 for x in m["items"] if x["id"] != 255 and x["count"]),
        "rare_item_bits": sum(bin(b).count("1") for b in m["rare_items"]),
        "tetra_master": {"cards": sum(1 for c in m["minigame"]["cards"] if c["id"] != 255),
                         "w/l/d": [m["minigame"][k] for k in ("sWin", "sLose", "sDraw")]},
        "counters": {k: m["party"][k] for k in ("frog_no", "steal_no", "dragon_no", "escape_no")},
        "abilities_with_ap": sum(1 for p in m["players"] for a in p["pa"] if a),
    }


USER_PROVENANCE = {
    "user_Final_Fantasy_IX.srm": "user's own RetroArch card Final Fantasy IX.srm",
    "user_Final_Fantasy_IX-01.srm": "user's own RetroArch card Final Fantasy IX-01.srm",
    "user_FF9_CloudSaveFile_ww.sav": "user's own Steam Cloud copy Documents/Square Enix/FINAL FANTASY IX/FF9_CloudSaveFile_ww.sav",
}


def main():
    prov = provenance()
    files = []
    for f in sorted(glob.glob(os.path.join(ROOT, "fixtures/ps1/extracted/*/*/*"))) + sorted(glob.glob(os.path.join(ROOT, "fixtures/ps1/originals/user_retroarch/*.srm"))):
        if f.lower().endswith(".txt"):
            continue
        raw = open(f, "rb").read()
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        arch = os.path.basename(os.path.dirname(f)) + ".zip" if "/extracted/" in rel else None
        rec = {"path": rel, "sha256": sha(raw), "size": len(raw), "platform": "ps1",
               "origin_archive": arch, "provenance": prov.get(arch), "synthetic": False, "slots": []}
        if os.path.basename(f) in USER_PROVENANCE:
            rec["provenance"] = {"source": USER_PROVENANCE[os.path.basename(f)], "personal": True,
                                 "copied": "read-only, byte-identical (sha256 checked)"}
        try:
            kind, entries = ps1_card.parse_file(raw)
            rec["format"] = kind
            rec["occupied_blocks"] = len(entries)
            for e in entries:
                s = {"block": e.block_index, "filename": e.filename, "directory_ok": e.directory_ok}
                if e.data[:2] == b"SC" and ps1_save.REGIONS.get(e.product_code[:12]):
                    sv = ps1_save.PS1Save(e.data, e.product_code, e.filename)
                    m = model.from_ps1(sv)
                    s.update(game="FINAL FANTASY IX", region=sv.region[0], language=sv.region[1],
                             crc_ok=sv.crc_ok, location=sv.preview()["location"], validity="genuine-structure-valid"
                             if sv.crc_ok else "crc-mismatch", **summarize(m))
                else:
                    s.update(game="other/unknown")
                rec["slots"].append(s)
        except Exception as ex:  # report, never crash the manifest
            rec.update(format="unrecognised", error=str(ex))
        files.append(rec)
    for f in sorted(glob.glob(os.path.join(ROOT, "fixtures/pc/originals/*/*"))):
        raw = open(f, "rb").read()
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        name = os.path.basename(f)
        rec = {"path": rel, "sha256": sha(raw), "size": len(raw), "platform": "pc", "provenance": prov.get(name),
               "synthetic": False, "slots": []}
        if name in USER_PROVENANCE:
            rec["provenance"] = {"source": USER_PROVENANCE[name], "personal": True,
                                 "copied": "read-only, byte-identical (sha256 checked)"}
        if "repos/" in rel:
            rec["provenance"] = {
                "ff9SaveLib_testdata_SavedData_ww.dat": {"source": "github.com/EuanFH/ff9SaveLib testdata/SavedData_ww.dat",
                                                         "license": "GPL-3.0 (repository license)"},
                "ffixsaveeditor_example_SavedData_ww_Memoria_0_0.dat": {
                    "source": "github.com/nintendogamer15/ffix-save-editor examples/", "license": "MIT (repository license)"},
            }.get(name)
        try:
            c = pc_container.Container(raw)
            rec["format"] = "pc-2016-vanilla-encrypted"
            rec["metadata"] = {k: v for k, v in vars(c.meta).items() if k != "reserved"}
            for slot, save in c.occupied():
                pv = c.preview(slot, save)
                m = model.from_pc(c.slot_tree(slot, save))
                rec["slots"].append({"slot": slot + 1, "file": save + 1, "location": pv.location,
                                     "validity": "genuine-structure-valid", **summarize(m)})
        except pc_container.ContainerError as ex:
            rec["format"] = "memoria-unencrypted" if name.endswith(".dat") and "Memoria" in name else "unrecognised"
            rec["note"] = f"not a vanilla container: {ex}"
        files.append(rec)
    man = {"generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "redistribution": "Third-party saves: no explicit redistribution license. Keep out of public commits.",
           "files": files}
    with open(os.path.join(ROOT, "fixtures/manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, default=str)
    slots = [s for r in files for s in r["slots"] if s.get("game") == "FINAL FANTASY IX" or r["platform"] == "pc"]
    print(f"{len(files)} files, {len(slots)} FF9 slots")
    covered = sorted({ms for s in slots for ms in s.get("milestones", [])}, key=lambda n: [x[0] for x in MILESTONES].index(n))
    print("milestones covered:", len(covered), "/", len(MILESTONES))
    print("missing:", [n for n, _, _ in MILESTONES if n not in covered])


if __name__ == "__main__":
    main()
