# FF9 converter: in-game test (about 30–45 minutes)

Nothing here touches your real saves:
- The install script never overwrites a file. If a save already exists, it renames it, and the restore script renames it back.
- Your Steam Cloud save (`Documents\Square Enix\FINAL FANTASY IX\FF9_CloudSaveFile_ww.sav`) is never touched.
- Your RetroArch cards are never touched.

**Rule while testing: never press "Cloud" on the FF9 title screen.** Uploading would replace your 2021 cloud save with these test saves.

## A. PC test (vanilla Steam FF9)

1. Close FF9 if it's running. In this folder, right-click `install_test_save.ps1` → **Run with PowerShell**. Run it yourself from Explorer: when an agent runs it from inside the Claude desktop app, Windows redirects the write to the app's private folder and the game never sees it.
2. Start FINAL FANTASY IX from Steam. Choose **Continue/Load** and pick the slot/file below.
3. For each checkpoint, check the items in the table and write PASS/FAIL plus notes in `results\results.md`. Copy the table below to start it.
4. For at least **Slot 2 File 1** (your own run) and **Slot 1 File 2** (Gulug), also:
   - Fight and win one battle.
   - Leave the screen and come back.
   - Save to an **empty** file, e.g. Slot 3 File 1 or Slot 3 File 2.
   - Quit to desktop, restart FF9, and load that new save.
5. Quit FF9. Run `collect_and_restore.ps1`. It copies the game's file into `results\` for analysis and then restores everything.
6. Tell Claude it's done. Claude will run `tools/analyze_runtime_result.py` on `results\` to check, field by field, that the game kept everything (abilities, stats, items, story) when it re-saved.

| Load | What it is | Expect (location, party) | Check |
|---|---|---|---|
| Slot 2 File 1 | **Your own PS1 run**, latest save | Bentini Heights, Dagger 7 / Steiner 8 / Marcus 7 | Continue as you would on PS1 |
| Slot 2 File 2 | Your run, "Start of DISC 2" | Disc 2 opening plays; Zidane 14 / Vivi 13 / Freya 14 / Quina 13 | The correct Disc 2 opening scene starts |
| Slot 1 File 1 | Early Alexandria | Alexandria steeple, Vivi lv1 (named ??????) | Go up the ladder, follow the rat kid: the scene plays |
| Slot 1 File 7 | Alexandria Castle | Guardhouse, Steiner lv1 | Cinna/Marcus/Blank show correctly in menus/scenes |
| Slot 1 File 2 | Midgame Gulug | Esto Gaza terrace, Zidane 41 / Dagger 35 / Vivi 34 / Freya 36 | Head right into Mount Gulug; check abilities and equipment |
| Slot 1 File 3 | Disc 3 transition | Disc 3 opening plays | Correct story scene |
| Slot 1 File 4 | Disc 4 transition | Disc 4 opening plays | Correct story scene |
| Slot 1 File 5 | Memoria entrance | Zidane 60 / Dagger 59 / Vivi 56 / Freya 58 | Walk in; fight one battle |
| Slot 1 File 6 | Crystal World | Before Deathguise | Optional: fight Deathguise |
| Slot 1 File 9 | World map, Disc 4 | Pualei Plains, airship | Walking/flying on the world map works |
| Slot 1 File 8, 10 | Disc 2 start; Cleyra | as listed in `expected_values.json` | Quick load check |

For every load, check:
- the location;
- party members and levels;
- the Status screen (HP/MP, stats, equipment);
- the Abilities screen (learned AP and equipped support abilities; magic stones shown as used/total);
- Items and Key Items;
- Tetra Master card count.

Exact expected numbers are in `expected_values.json`.

**A load screen alone is not a pass.** The checkpoint passes only if the right story scene or event happens next.

## B. PS1 test (optional, DuckStation)

This checks the reverse direction, PC → PS1. `PS1\FF9_from_PC.mcr` holds 5 saves converted from PC saves (FILE01 is from your own 2021 PC run).

1. Copy `PS1\FF9_from_PC.mcr` to `<DuckStation folder>\memcards\FF9_test_card.mcd`.
2. Simpler alternative, with no settings change: with DuckStation's default per-game cards, name the copy `Final Fantasy IX_1.mcd` in `memcards` (only if no such file exists). It is then card 1 when you start `Final Fantasy IX.m3u`. Otherwise use **Settings → Memory Cards → Memory Card 2** → *Shared Between All Games* and browse to the file.
3. Start your own FF9 disc set (e.g. its `.m3u` playlist). On the title screen choose Continue → **Memory Card 2** and load each FILE:
   - FILE01 Lindblum Inn (Zidane 10)
   - FILE02 Gulug path (Zidane 33, Dagger 29, Steiner 30, Vivi 32)
   - FILE03 S. Gate (Dagger 1, Steiner 1)
   - FILE04 Disc 3 Alexandria (Zidane 1, Vivi 1)
   - FILE05 Gegalrich Shores (Zidane 32, Freya 21, Amarant 30, Steiner 25)
4. Use the same checks as above. Also note whether the game asks for the right disc.
5. Afterwards, set Memory Card 2 back to how it was.

If anything is off, a screenshot or one sentence per checkpoint is enough.
