# Testing (v0.3.0-dev)

## v0.3: batch conversion and the redesigned app

`python -P -m pytest tests`: **511 passed, 1 skipped** (v0.2: 461 passed). Log: `reports/test_results_v0.3.txt`.
The skip is still symlink creation (needs Windows Developer Mode).

| Suite | What it covers |
|---|---|
| `test_batch.py` (35, new) | Full 15-save card → one PC slot with every save re-verified by `verify`; FILE numbers vs directory blocks (a card written in reverse block order); selected saves in source order; second card → next empty slot with slot 1 byte-identical and a verified backup; copy mode; no empty slot (shared slot); occupied places needing approval; manual mapping and its errors; one damaged save blocking the batch until left out; full PC export to one card; one card per slot; one slot keeping FILE numbers; `.mcs` per save; 28 saves split 15 + 13 with manifest; existing card renumbering, other blocks byte-identical, capacity, approved replacement in place; Memoria sidecars judged per save (valid/stale/corrupt/untimed), identical to single conversion, lossy listed, Moguri-style file, live sidecar refusing PS1 → PC; write failure rolling back every file; failure after the move restoring the in-place original; a simulated crash leaving a journal that blocks the next plan and that `recover` undoes; cancel before and during the write; verification failure writing nothing; destination changed after the review; existing outputs; sources and Steam Cloud never written; the Transaction unit; CLI `batch`/`recover` output and refusals; **batch save data byte-identical to single conversion** (PS1 → PC and PC → PS1) |
| `test_gui.py` (32, rewritten for the new window) | Every v0.2 GUI scenario again (loading, drag and drop, unreadable files, converting with independent verification, double click → one write, occupied places and Replace, in-place updates with backups and untouched slots, wrong destination kinds, Steam Cloud refusal, never overwriting, keyboard and screen-reader names, Memoria lossy) plus: convert all / choose saves / nothing selected; PC → several cards; existing card renumbering note; full card; leave out a damaged save; cancel writing nothing; write failure undone; undoing an interrupted conversion from the window; the GUI plan equal to the service and CLI plans; Advanced details, log and manual placement; unique access keys; light and dark themes; no clipped or overlapping controls at 520×460, 640×600 and 1280×1000; no jargon ("sidecar", "container", "canonical") in the main window |

The v0.2 GUI tests targeted widgets of the old window; their scenarios are re-covered above (the old file is in
`snapshots/v0.2.0-dev-source-baseline.zip`). Every other v0.2 test file is unchanged and passes.

**Single-save output unchanged:** `tools/compare_with_v02_baseline.py` runs `ffix-convert convert` from the v0.2
snapshot and from v0.3 on six cases (PS1 → PC new and at a chosen slot, PC → PS1 card and `.mcs`, Memoria → PS1 with a
sidecar, Memoria lossy): all six outputs are byte-identical.

### Packaged build (fresh extraction, Python removed from PATH)

`reports/v0.3_package_test_results.txt`:

- `smoke_test_exe.ps1` (PowerShell 7): **22/22**: the 17 v0.2 command-line checks plus batch card → PC, batch PC →
  cards, dry run, replacement refused without approval, recover with nothing to undo.
- `smoke_test_gui.ps1`: **33/33** through Windows UI Automation (the screen-reader interface), with the real exe:
  - a full 15-save card → new PC file, slot 1 files 1–15, all 15 saves verified with the packaged CLI, source unchanged;
  - a 13-save card added to an existing 6-save PC file in place: 19 saves, verified backup equal to the original;
  - a 28-save PC file → two cards (15 + 13) and the manifests, verified with the CLI;
  - keyboard only: Alt+C converts, Alt+M returns; every window closes cleanly.
- `gui_matrix.ps1`: **33/33**:
  - light and dark × 520×460, 800×780, 1280×1000 × scale 100 %, 125 %, 150 %, 200 % (24 cases): the theme applies,
    no control is clipped or overlapping, Convert enabled; a screenshot of each;
  - scripted decisions in the real window: occupied slot (Convert stays disabled, file unchanged; after the Replace
    tick, replaced with a verified backup); damaged save explained and left out (the other 12 convert); cancel writes
    nothing; Memoria damaged sidecar blocks, lossy converts all 5, sidecar-reconciled saves verify with the CLI.

### In-game

Run on 2026-11-07 with the packaged v0.3 build (zip `9f4fae83…`, fresh extraction), FF9 Steam Cloud switched off by you
and restored afterwards, and your save folder backed up and restored by hash. Screenshots are in
`reports/screenshots_v0.3/ingame/` (git-ignored: game imagery).

The batch files: your 15-save card → new PC file (slot 1); your 13-save card added to it in copy mode (slot 2); that
28-save PC file → `FFIX-PS1-Card-01.mcr` (15) and `FFIX-PS1-Card-02.mcr` (13). All 28 saves verified, sources unchanged.

| Checkpoint | Result |
|---|---|
| PC (Memoria v2025.07.04, isolated install): slot 2 load screen | FILE11–13 show Start of DISC 2 / S. Gate Rest Stop / Bentini Heights with the card's exact times, gil, levels and party; FILE14–15 empty ✅ |
| Slot 2 FILE11 "Start of DISC 2" | Disc 2 opening at South Gate/Bohden Gate; dialogue advances; scene changes to Summit Station (map 812) with Dagger and Steiner ✅ |
| Slot 1 load screen and FILE15 | FILE13–15 match the first card; FILE15 loads at L. Castle/Guest Room beside the Moogle (map 611) ✅ |
| PS1 (DuckStation, your NTSC-U discs): Card 02 | Read natively by the game; FILE01–03 and FILE08–10 match the source card ✅ |
| Card 02 FILE10 Burmecia/Vault | Loads at the Moogle; menu party, levels, HP/MP, time and gil match the source save; walking works ✅ |

After the PS1 → PC → PS1 round trip the save equals the source card save in every field except one documented
normalisation: a not-yet-joined character's `bonus_cap` 0 (PC's "derive") becomes the derived value (Blank Lv5 → 20).
Afterwards: your PC save restored by SHA-256 (`13d42e96…`), Memoria's test autosave removed, the DuckStation test card
unchanged and removed, `cloud_guard.py check` OK (2021 cloud file `00aa9674…` unchanged). Not loaded in game: Card 01
and the Steam build without Memoria (both use the same writer as the saves above).

## v0.2

## Automated

`python -P -m pytest tests`: **461 passed, 1 skipped** (v0.1.0-beta: 381; the new tests are in `test_service.py`,
`test_gui.py`, `test_memoria.py` and `test_memoria_runtime.py`). The skip is symlink creation, which needs Windows Developer Mode; junction and hard-link aliasing are tested instead. Full log: `reports/test_results.txt`.

| Suite | What it covers |
|---|---|
| `test_ps1.py` | Card detection and wrappers, directory/CRC checks, all 54 FantasyAnime saves, malformed cards |
| `test_pc.py` | AES, container layout, byte-identical round trips of all PC containers, invalid/corrupt containers |
| `test_convert.py` | PS1 → PC on all 54 saves, cross-platform field equality on real story-point pairs, edge cases |
| `test_audit.py` | Support abilities, AP, stones and stat growth checked against the vanilla game's own rules on 763 character records; defaults equal what the game writes; no template leakage |
| `test_bidirectional.py` | PS1 → canonical → PS1 byte-identical (82 saves); PS1 → PC → PS1 and PC → PS1 → PC (36 PC slots); card insertion/full/multi-block; unrepresentable values; disc/region |
| `test_service.py` | The shared service layer: CLI and app defaults agree, dry runs write nothing, existing outputs and Steam Cloud files are never written, destination slot listings |
| `test_gui.py` | The desktop app driven offscreen: loading, drag and drop, unreadable files, review then convert with independent verification, a double click starting only one write, occupied-slot warnings and Replace, confirmed in-place updates with backups and untouched slots, PS1 FILE numbers, wrong destination kinds, Steam Cloud refusal, existing names, report dialog, keyboard reachability, mnemonics and screen-reader names, Memoria status and the lossy confirmation |
| `test_memoria.py` | The sidecar format (byte-for-byte on the public sample, trailing bytes, corrupt and hostile inputs), names and slot association, Memoria's one-second staleness rule, sidecar precedence, each refusal and lossy fix, refusals that lossy cannot override, corrupt sidecars, sources untouched, the PS1 → PC overlay guard, and a faithful sidecar being the identity on every vanilla PC slot |
| `test_memoria_runtime.py` | Genuine files from the Memoria runtime test (git-ignored, personal): byte-for-byte sidecar round trips, the party Memoria shows, Memoria's own container losing Marcus, the autosave pair, the four sidecar cases against what Memoria did in the game, the Moguri-style save, vanilla state across PS1 → Memoria → PS1, PS1 portraits |
| `test_safety.py` | Atomic writes, no-clobber, verified backups, destination-changed detection, read-only, aliases (hard link, junction, case, `..`), strict encoding, CLI errors and exit codes, default names, in-place updates, `verify` catching tampering, CLI round trips |

Fixtures:
- **Third-party:** 54 FantasyAnime PS1 saves; 4 public PC containers (Steam forum uploads, the ff9SaveLib test file).
- **Your own** (personal, never redistributed): 2 RetroArch PS1 cards (28 saves) and your 2021 Steam Cloud PC save (22 slots).

Packaged executable: `tools/packaging/smoke_test_exe.ps1` runs the frozen exe from an isolated folder with no Python. **17/17 checks pass.** They cover:
- inspect for both platforms;
- both conversion directions and both round trips, with `verify`;
- inserting into an existing card;
- refusal of overwrites, unconfirmed in-place updates, invalid inputs, ambiguous sources and missing files;
- source preservation and preservation of other card blocks.

Packaged v0.2 build (`reports/v0.2_package_smoke_results.txt`), run from a fresh extraction of the zip with Python
off the PATH:
- `smoke_test_exe.ps1`: **17/17** command-line checks;
- `smoke_test_gui.ps1`: **15/15**. It drives the desktop app through Windows UI Automation, the interface screen
  readers use: launch with a file, list saves, review, Convert, verify with the packaged CLI, close, sources unchanged;
  both directions;
- Memoria through the packaged CLI: refused by default, converted with `--allow-lossy`.

## In-game runtime tests

All runs used your own installs, isolated save copies and hash-verified restores. Details and screenshots are in `reports/RUNTIME_RESULTS.md`.

### PS1 → PC (vanilla Steam build 5378074)

| Checkpoint | Result |
|---|---|
| Your PS1 run, Bentini Heights (Disc 2) | Exact stats; Treno story scene; world map → Treno; battle won; native PC save; quit, restart and reload ✅ |
| Esto Gaza / Gulug (Disc 3) | Exact stats; 3 screen transitions; battle won ✅ |
| "Start of DISC 3", "Start of DISC 4" | Correct disc openings ✅ |
| Memoria entrance, Alexandria Castle | Correct location and stats; Memoria battle runs ✅ |

### PC → PS1 (DuckStation 0.1-7878, your NTSC-U discs)

| Checkpoint | Result |
|---|---|
| Gulug path (Disc 3) | Asks for disc 3; exact stats; transitions ✅ |
| Disc 4 world map | Asks for disc 4; battle; native card save; reset and reload ✅ |
| Your own 2021 PC save, Lindblum (Disc 1) | Exact stats ✅ |
| **New in RC:** your "Start of DISC 2" save via PC | Asks for disc 2; correct Disc 2 opening (South Gate) ✅ |
| **New in RC:** "Start of DISC 3" via PC | Correct Disc 3 opening ✅ |
| **New in RC:** your 2021 PC early game, Alexandria Castle guardhouse | Exact stats (Steiner Lv1, 120/120, 17/17 stones, 10678 gil); room transition ✅ |
| **New in RC:** late game, Eiko-led Lv 99 party, 4,440,291 gil (Dali) | Exact stats; Mognet available; native save; reset and reload ✅ |

### PS1 → PC round 2 (Steam Cloud off for FF9, screenshot-guarded input)

| Checkpoint | Result |
|---|---|
| Your "Start of DISC 2" | Correct Disc 2 opening, continuing into the cable-car scene ✅ |
| Treno, Disc 3 | World ↔ town transitions; battle; **native save, restart, reload** with HP, stones and gil intact ✅ |
| Disc 4 world map | Correct (aboard the Invincible) ✅ |
| Crystal World, late game | Exact stats including used stones; correct final-dungeon event ✅ |

Guard tooling: `tools/runtime/ff9_gui.py`, `ff9_step.py`, `cloud_guard.py`.

## Not covered (gaps)

- PAL and Japanese saves; other Steam builds.
- **Memoria/Moguri:** played at one Disc 2 checkpoint only, with unmodified gameplay; no real gameplay mod (Alternate
  Fantasy, Beatrix Mod, …) and no Moguri textures were tested.
- RetroArch/Beetle as the runtime emulator (its card files are tested).
- **No clean Windows machine.** The exe was tested from an isolated folder and from the extracted zip, with Python hidden, but on the development PC only.
