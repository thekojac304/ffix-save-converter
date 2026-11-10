# Roadmap and success criteria (bidirectional)

Goal: move one FF9 playthrough between the original PlayStation version and the 2016 PC version in **both directions**, keeping story and gameplay state.

## Architecture (in place)

```
PS1 card/block ──ps1_card + ps1_save──▶ canonical model (model.py) ──convert──▶ PC slot tree ──pc_container──▶ SavedData_ww.dat
PS1 card/block ◀──ps1_card + ps1_writer── canonical model ◀──model.from_pc── PC slot tree ◀──pc_container── SavedData_ww.dat
```

* One canonical model and one mapping registry (`model.FIELD_MAP`) for both directions; every transform has a documented inverse (`docs/FIELD_MAPPING.md`).
* The canonical model carries the untouched source payload (`platform_extra`). Writing back to the *same* platform restores platform-only bytes losslessly; it's never used for other saves.
* Writers never overwrite files or occupied slots unless explicitly told to (`--overwrite-slot`, `--overwrite-block`), and they never touch multi-block files.

## Success criteria

| Level | PS1 → PC | PC → PS1 |
|---|---|---|
| 1 Character transfer | ✅ static + audit | ✅ static |
| 2 World state | ✅ static + audit | ✅ static (PS1-only regions zero-filled) |
| 3 Complete progression | ✅ runtime: your own run + 5 priority checkpoints load correctly; story, battle, native save and restart/reload verified (`reports/RUNTIME_RESULTS.md`) | ◑ runtime: loads, disc prompt, battle, native save and reset/reload verified on DuckStation; fewer checkpoints |
| Round trip | ✅ PS1→PC→PS1 keeps all gameplay state | ✅ PC→PS1→PC keeps all common fields; PC-only data reported |

"Routine personal use" means Level 3 in that direction, with `analyze_runtime_result.py` showing no unexplained changes after a PC re-save.

## v0.2 (in progress)

* Windows desktop app on the shared service layer (done, packaged and tested; `reports/V0.2_STATUS.md`).
* Memoria/Moguri: sidecar reader, Memoria's load rules, Memoria → PS1 with refusals and an opt-in lossy mode, and a
  write guard for PS1 → Memoria (done at the file level).
* **Open:** play converted saves under Memoria in an isolated test copy of the game (needs your approval: download
  Memoria, a 9.1 GB copy of the game folder, FF9 Steam Cloud off during the test). Then: Memoria native save/reload,
  Memoria → PS1 and PS1 save/reload in DuckStation, and a real gameplay-mod save as a fixture.
* Signed executables, a clean-machine test of the app, PAL fixtures.

## Next steps (by impact)

1. Done 2026-11-06: runtime tests in both directions (see `reports/RUNTIME_RESULTS.md`); one cosmetic PS1 preview bug fixed.
2. More PC → PS1 checkpoints in DuckStation (Disc 2/3 starts), and save/reload on more PS1 → PC checkpoints.
3. Full round trip of your own run: Bentini Heights PS1 → PC → PS1, then continue on the emulator.
4. Identify the PS1-only regions (0x0EF2–0x0F1F first), e.g. by saving on the emulator before and after a Steiner/battle-flag change, so PC → PS1 no longer zero-fills them.
5. Locate the PS1 timer and config fields (save during the Festival of the Hunt; change options and re-save).
6. PAL fixtures.
