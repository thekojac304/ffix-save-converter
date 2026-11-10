# Phase 2: runtime readiness, converter audit and bidirectional conversion

Date: 2026-11-06 · Tests: **355 passed, 0 failed** (`reports/test_results.txt`) · In-game verification: **performed, both directions** (`reports/RUNTIME_RESULTS.md`)

## 1. Summary

* An independent audit against the **vanilla** PC game code found and fixed three real defects. All three were invisible to the round-trip tests:
  1. **`menu_type` was read as 4 bits; it is 5.** Early-game Cinna, Marcus and Blank (presets 17/18/19) would have been converted with Vivi's, Garnet's and Steiner's presets. Proven with a PS1/PC pair at the same story point.
  2. **Achievement lists were written as 0 instead of −1.** Vanilla treats every non-(−1) entry as real, so each converted save would have logged a phantom Tetra Master win, phantom learned ability IDs, and so on.
  3. **Default key bindings came from a non-standard fixture.** They are now the vanilla `HonoInputManager` and `FF9CFG` defaults; these bindings match your own PC save exactly. Impact was limited: vanilla ignores stored bindings while `control = 0`.
* Fields previously marked "inferred" are now verified against the vanilla game's own rules, on 763 character records (564 PS1, 199 PC):
  - support abilities (`sa`), AP (`pa`), stat-growth `bonus` and the magic-stone cap;
  - key items (2-bit encoding);
  - the steal, dragon, frog and escape counters (confirmed with your own PS1 playthrough).
* **Bidirectional conversion is implemented.** PC → PS1 writes valid FF9 blocks (CRC, title, icon, disc mask) and memory cards. A blank card plus a block reproduces an emulator-written card byte-for-byte. Round trips:
  - All 82 PS1 saves come back byte-identical through PS1 → canonical → PS1.
  - PS1 → PC → PS1 preserves all gameplay state.
  - PC → PS1 → PC preserves every common field on all 36 PC slots.
* **In-game testing could not be automated here** (§3). A one-file test package with install/restore scripts and expected values is ready (§5).
* **Recommendation (§8):** usable for personal use *as a beta*, after you complete the 15-minute core test. It isn't ready to call "routine" until that test passes.

## 2. Corpus additions in Phase 2 (all read-only copies, byte-identical, git-ignored)

| Source | Content | Why it matters |
|---|---|---|
| `Documents\Square Enix\FINAL FANTASY IX\FF9_CloudSaveFile_ww.sav` | Your 2021 PC save: 22 Disc 1 slots | 9 exact story-point pairs with the FantasyAnime PS1 saves |
| Your RetroArch cards `Final Fantasy IX.srm` and `-01.srm` | Your PS1 playthrough: 28 saves, opening to early Disc 2 | Same-player trajectories; settled the steal/dragon question; real multi-save cards; Disc 2 boundary at scenario 3900 |

Corpus now: 82 PS1 saves (54 FantasyAnime + 28 yours) and 36 PC slots (14 public + 22 yours), with 21/21 story milestones covered.

## 3. Runtime environment findings

| Question | Finding |
|---|---|
| Save directory | `%USERPROFILE%\AppData\LocalLow\SquareEnix\FINAL FANTASY IX\Steam\EncryptedSavedData\SavedData_ww.dat`. Confirmed from vanilla `SharedDataBytesStorage.SetPCPath` and Unity company/product `SquareEnix`/`FINAL FANTASY IX`. The folder **does not exist** on this PC yet. |
| Steam Cloud | Steam Auto-Cloud for app 377840 syncs only `Documents\Square Enix\FINAL FANTASY IX\FF9_CloudSaveFile_ww.sav` (`remotecache.vdf`). The game writes that file only when you press **Cloud** on the title screen (vanilla `SiliconStudio.Social`). The working save in LocalLow is **not** synced, so testing there is isolated as long as the in-game Cloud button isn't used. You do have a real cloud save (May 2021), which an upload would overwrite. |
| Isolated local saves | Yes. LocalLow is local-only. The install script renames any existing save (never overwrites) and the restore script puts it back. |
| Temporary Windows profile | Not used: creating accounts changes system security settings, and Steam/DRM would need a full login there. Not needed given the above. |
| Automated control | **Not possible.** The agent's shell has no handle to your interactive desktop: screen capture fails with "handle is invalid", even outside the sandbox. It cannot see the game or send input. |
| PS1 emulator | You have DuckStation, RetroArch (Beetle PSX HW), a SCPH1001 BIOS and FF9 USA discs 1–4 (`.chd`). Same limitation: no screen/input access. A manual DuckStation procedure is in the package and keeps your RetroArch cards untouched. |
| Game files | Not modified. `Assembly-CSharp.dll` was copied to the scratchpad and decompiled locally (ilspycmd) to read the save code. Only facts (field order, defaults, ability gem costs) were extracted, into git-ignored `research/vanilla_extracts/`. |

## 4. Converter audit

| Area | Method | Result |
|---|---|---|
| Support abilities | Vanilla rules: `cur.capa == max.capa − Σcost(sa)`, every set SA learnable by that character | **563/563 + 199/199 pass** → verified (a wrong bit order would make vanilla unequip every SA on load) |
| AP | Every `pa[j] ≤` the vanilla PA-table requirement for the character's preset | all pass → verified |
| Stat-growth bonus | Vanilla `ff9level` formulas must yield one constant base per character | 85 groups, 0 inconsistent → verified |
| Bonus cap | Same formula with `max.capa`; vanilla treats `player_bonus = 0` as "derive" | verified; PS1 guests with cap 0 (Beatrix, early Marcus) get the derived cap on PC, exactly like native PC saves (documented) |
| `menu_type` / `info` | PS1/PC pairs | **bug fixed** (5 bits) + regression test |
| Key items | Vanilla `ff9item`: 2 bits per item; 9 exact pairs | verified (PC obtained ⊆ PS1 obtained; differences are "used" flags and optional items) |
| Counters | Vanilla struct order, CodeBreaker RAM codes, your PS1 trajectory | verified: 0xEEC frog, 0xEEE steal, 0xEF0 dragon, 0xEE4 escape |
| Party | Vanilla loader indexes `player[slot]` directly | 9→255 transform is required (writing 9 would crash the loader); verified |
| Location | Exact pairs; vanilla `GetDisc`/world handling | verified; pre-world-map `wldMapNo` 9009↔0 documented as harmless |
| PC-only defaults | Diffed every PC-only leaf against real PC saves at the same story point | **two bugs fixed** (−1 lists, key bindings); the rest match what the game writes |
| Template leakage | Converted with a level-99 endgame donor template | only `50000_Setting` and `70000_World` differ (test) |
| All 54 + 28 conversions | Canonical comparison, both directions | pass |

Remaining "inferred": `summon_flag`, `mode`/`prevMode`, playtime scale, Tetra Master W/L/D. "Unknown": PS1 timer and config location, and several PS1-only regions (see `docs/FIELD_MAPPING.md`).

## 5. Runtime test package: `runtime_test_package/` (git-ignored)

| File | Content |
|---|---|
| `START_HERE.md` | Step-by-step, about 30–45 minutes |
| `install_test_save.ps1` / `collect_and_restore.ps1` | Safe install, evidence capture and restore |
| `PC/SavedData_ww.dat` (sha256 `ca7924cc…`) | 13 converted checkpoints |
| `PS1/FF9_from_PC.mcr` (sha256 `b746dfb2…`) | 5 PC saves converted to PS1, for DuckStation |
| `expected_values.json` | Expected location, party, HP/MP, stones, gil, items and cards per checkpoint |
| `results/results.md` | Fill-in sheet |

Checkpoint → file mapping:

| Priority | Load menu | Source | Scenario |
|---|---|---|---|
| Your run | Slot 2 File 1 | your RetroArch card, block 13, Bentini Heights | 4390 |
| Your run | Slot 2 File 2 | your card, block 11, "Start of DISC 2" | 3900 |
| Your run | Slot 2 File 3 | your card, block 9, Burmecia/Vault | 3880 |
| 1 Early Alexandria | Slot 1 File 1 | FantasyAnime 01, Steeple | 1155 |
| 2 Midgame Gulug | Slot 1 File 2 | FantasyAnime 41, Esto Gaza | 9950 |
| 3 Disc 3 transition | Slot 1 File 3 | FantasyAnime 32, "Start of DISC 3" | 6990 |
| 4 Disc 4 transition | Slot 1 File 4 | FantasyAnime 49, "Start of DISC 4" | 10995 |
| 5 Memoria / endgame | Slot 1 Files 5, 6 | FantasyAnime 51 (entrance), 53 (Crystal World) | 11615, 11765 |
| extra | Slot 1 Files 7–10 | Castle (menu_type fix), Disc 2 start, world-map save, Cleyra/Beatrix | |

After your run, `python -P tools/analyze_runtime_result.py runtime_test_package` compares each save the game wrote with the converted checkpoint it continues. It flags anything the game silently "repaired" (cleared abilities, rebuilt stats, changed story flags).

## 6. Actual in-game results

See `reports/RUNTIME_RESULTS.md`. Summary:
- **PS1 → PC (vanilla Steam):**
  - Your own PS1 run loaded with exact stats. The correct story scene played (first arrival in Treno). A battle was won, the PC game saved natively, and the save reloaded after a full restart.
  - The Gulug, Disc 3 start, Disc 4 start, Memoria and Alexandria Castle checkpoints all loaded at the correct location with exact stats. The disc-change saves play the correct opening scene.
- **PC → PS1 (DuckStation):**
  - The PS1 game accepted converted saves, asked for the right disc, and showed exact stats.
  - A world-map battle was won, the game saved to the card, and the save reloaded after an emulator reset. Your 2021 PC save also loaded on PS1.
- **Bugs found at runtime:** one PS1 load-screen preview bug (cosmetic), now fixed with a regression test and re-verified in the emulator.

## 7. Remaining compatibility risks (most impactful first)

1. **No runtime evidence.** The only route to Level 3.
2. **Disc-change saves** ("Start of DISC n", `fldLocNo = −1`) on PC: the PC has no disc swaps, and how it resumes such a save is unproven (package checkpoints 2/2, 1/3, 1/4).
3. **PC → PS1 PS1-only regions** are zero-filled when no same-playthrough PS1 save exists: 0x0EF2–0x0F1F (possibly `steiner_state`, battle flags), 0x09C0, 0x1160, 0x13F4. Unknown effect on the PS1 game until an emulator test.
4. Countdown-timer state during timed sequences (unlocated on PS1). Save points are outside timed sequences.
5. PAL/Japanese saves are untested (PAL warns; Japanese is rejected).
6. Memoria/Moguri: compatible by design (sidecar only applied when playtimes match) but untested.

## 8. Recommendation

* **PS1 → PC: ready for routine personal use**, with one caveat: keep the PS1 card as a backup. Runtime evidence covers load, story continuation, map transitions, battles, a native PC save and a restart/reload. The field-level analysis of the game-written save shows nothing unexpected. Every progression field is also verified against the vanilla code.
* **PC → PS1: usable as a beta.** The PS1 game accepted converted saves, continued from them, battled, saved and reloaded. PS1-only regions are zero-filled, and the game kept or managed them itself. Fewer checkpoints have been exercised than PS1 → PC. Use `--ps1-base` with a PS1 save of the same playthrough when available.
* When an AI agent installs test saves from inside the Claude desktop app, writes to `AppData` are redirected by MSIX packaging; run the install scripts yourself, or from outside the package.
