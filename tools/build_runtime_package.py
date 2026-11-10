"""Build runtime_test_package/: converted saves, expected values, install/restore scripts.

Derived from third-party and user saves -> git-ignored. Existing package folders are never
overwritten; delete the folder yourself to rebuild.
Usage: python -P tools/build_runtime_package.py
"""
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ffix_conv import convert, model, pc_container, ps1_card, ps1_save, ps1_writer  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "runtime_test_package")
NAMES = ["Zidane", "Vivi", "Garnet", "Steiner", "Freya", "Quina", "Eiko", "Amarant", "slot 8 (Beatrix)"]
TS = 1700000000.0

# (PC file number, FantasyAnime save, priority label)
PC_CHECKPOINTS = [
    (1, 1, "P1 Early Alexandria (exact PC pair)"),
    (2, 41, "P2 Midgame Gulug (exact PC pair)"),
    (3, 32, "P3 Disc 3 transition (disc-change save)"),
    (4, 49, "P4 Disc 4 transition (disc-change save)"),
    (5, 51, "P5 Memoria entrance (final dungeon)"),
    (6, 53, "P5b Crystal World before Deathguise (endgame)"),
    (7, 2, "Extra: Alexandria Castle - checks the 5-bit menu_type fix (Cinna/Marcus/Blank)"),
    (8, 15, "Extra: Disc 2 start, Summit Station"),
    (9, 50, "Extra: world-map save (mode 3), Disc 4"),
    (10, 20, "Extra: Cleyra, Beatrix guest (bonus.cap rule)"),
]
# The user's own PS1 playthrough (RetroArch card) -> PC slot 2: (PC file number, block, label)
USER_CARD = "fixtures/ps1/originals/user_retroarch/user_Final_Fantasy_IX.srm"
USER_CHECKPOINTS = [
    (1, 13, "YOUR RUN: latest PS1 save, Bentini Heights (Disc 2)"),
    (2, 11, "YOUR RUN: 'Start of DISC 2' disc-change save"),
    (3, 9, "YOUR RUN: Burmecia/Vault (Disc 1, before the Beatrix fight)"),
]
# PC -> PS1 checkpoints for a future emulator test: (label, pc file, slot, save)
PS1_CHECKPOINTS = [
    ("Your own save: Lindblum Inn (Disc 1)", "user_cloud/user_FF9_CloudSaveFile_ww.sav", 1, 0),
    ("Gulug path (Disc 3)", "repos/ff9SaveLib_testdata_SavedData_ww.dat", 0, 0),
    ("Disc 2 start, S. Gate", "steam/steam_cd3thread_SavedData_ww.dat", 1, 0),
    ("Disc 3 start, Alexandria", "steam/steam_cd3thread_SavedData_ww.dat", 1, 1),
    ("Disc 4 open world", "steam/steam_cd3thread_SavedData_ww.dat", 1, 2),
]


def expected(m):
    return {
        "scenario_counter": m["event"]["scenario_counter"],
        "location": (m.get("preview") or {}).get("location"),
        "field_or_world": m["state"],
        "party": [{"name": m["players"][s]["name"], "who": NAMES[s], "level": m["players"][s]["level"],
                   "hp": f"{m['players'][s]['cur']['hp']}/{m['players'][s]['max']['hp']}",
                   "mp": f"{m['players'][s]['cur']['mp']}/{m['players'][s]['max']['mp']}",
                   "magic_stones": f"{m['players'][s]['cur']['capa']}/{m['players'][s]['max']['capa']}",
                   "equip_ids": m["players"][s]["equip"],
                   "support_abilities_equipped": sum(bin(x).count("1") for x in m["players"][s]["sa"])}
                  for s in m["party"]["slot"] if s not in (9, 255)],
        "gil": m["party"]["gil"],
        "playtime": f"{int(m['playtime_seconds'] // 3600)}:{int(m['playtime_seconds'] % 3600 // 60):02d}",
        "item_stacks": sum(1 for x in m["items"] if x["count"]),
        "tetra_master_cards": sum(1 for c in m["minigame"]["cards"] if c["id"] != 255),
    }


def main():
    if os.path.exists(OUT):
        raise SystemExit(f"{OUT} exists; delete it to rebuild")
    os.makedirs(os.path.join(OUT, "PC"))
    os.makedirs(os.path.join(OUT, "PS1"))
    os.makedirs(os.path.join(OUT, "results"))
    src = {x["filename"][:-4]: x for x in json.load(open(os.path.join(ROOT, "research/sources_fantasyanime.json")))}
    container = convert.blank_container()
    manifest = {"pc_file": "PC/SavedData_ww.dat", "pc_checkpoints": [], "ps1_file": "PS1/FF9_from_PC.mcr",
                "ps1_checkpoints": []}
    for file_no, fa_no, label in PC_CHECKPOINTS:
        path = glob.glob(os.path.join(ROOT, f"fixtures/ps1/extracted/fantasyanime/ff9save{fa_no:02d}_*/*.mcr"))[0]
        name = os.path.basename(os.path.dirname(path))
        _, es = ps1_card.parse_file(open(path, "rb").read())
        s = ps1_save.PS1Save(es[0].data, es[0].product_code, es[0].filename)
        m = model.from_ps1(s)
        tree, rep = convert.to_pc_tree(m)
        convert.insert(container, 0, file_no - 1, tree, convert.preview_for(tree, m, TS + file_no))
        manifest["pc_checkpoints"].append({
            "load_menu": f"Slot 1, File {file_no}", "label": label, "source": name,
            "what_to_do_next": src[name]["description"], **expected(m),
            "converter_warnings": rep.warnings})
    user_card = os.path.join(ROOT, USER_CARD)
    if os.path.exists(user_card):
        _, entries = ps1_card.parse_file(open(user_card, "rb").read())
        for file_no, blk, label in USER_CHECKPOINTS:
            e = [x for x in entries if x.block_index == blk][0]
            m = model.from_ps1(ps1_save.PS1Save(e.data, e.product_code, e.filename))
            tree, rep = convert.to_pc_tree(m)
            convert.insert(container, 1, file_no - 1, tree, convert.preview_for(tree, m, TS + 100 + file_no))
            manifest["pc_checkpoints"].append({
                "load_menu": f"Slot 2, File {file_no}", "label": label,
                "source": f"your RetroArch card 'Final Fantasy IX.srm', block {blk}",
                "what_to_do_next": "Continue exactly where you left off on PS1", **expected(m),
                "converter_warnings": rep.warnings})
    data = container.to_bytes()
    pc_container.Container(data)
    with open(os.path.join(OUT, "PC/SavedData_ww.dat"), "xb") as f:
        f.write(data)
    manifest["pc_sha256"] = hashlib.sha256(data).hexdigest()

    card = ps1_card.blank_card()
    for k, (label, rel, sl, sv) in enumerate(PS1_CHECKPOINTS, start=1):
        p = os.path.join(ROOT, "fixtures/pc/originals", rel)
        if not os.path.exists(p):
            continue
        c = pc_container.Container(open(p, "rb").read())
        m = model.from_pc(c.slot_tree(sl, sv))
        m["preview"] = {"location": c.preview(sl, sv).location}
        block, rep = ps1_writer.build_block(m, file_no=k)
        card, idx = ps1_writer.place_on_card(block, k, card=card)
        manifest["ps1_checkpoints"].append({"memory_card_file": f"FILE{k:02d}", "block": idx, "label": label,
                                            "source": f"{rel} slot {sl + 1} file {sv + 1}", **expected(m),
                                            "zero_filled_ps1_only_regions": rep["zero_filled"]})
    with open(os.path.join(OUT, "PS1/FF9_from_PC.mcr"), "xb") as f:
        f.write(card)
    with open(os.path.join(OUT, "expected_values.json"), "x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    print(f"package written to {OUT}")


if __name__ == "__main__":
    main()
