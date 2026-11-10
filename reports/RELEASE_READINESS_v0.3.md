# Release readiness: v0.3.0-dev (batch conversion and GUI redesign)

Local development build only: nothing was pushed, tagged or published. The v0.2.0-dev baseline is untouched
(`release/v0.2.0-dev`, and its source in `snapshots/v0.2.0-dev-source-baseline.zip`).

## Build

`release/v0.3.0-dev/FFIX-Save-Converter-0.3.0-dev-win-x64.zip` (portable folder: `FFIX Save Converter.exe`,
`ffix-convert.exe`, `_internal/`, docs, `THIRD_PARTY_LICENSES/`). SHA-256 values are in `SHA256SUMS.txt` next to it.
The build script checks that the package holds no save files, disc images, screenshots or the local user name, and that
LICENSE, the LGPL text and both executables are present.

## Success criteria

| Criterion | Status | Evidence |
|---|---|---|
| Drag in a full PS1 card, see all saves, "Convert all", new or existing PC file, Convert, one PC file with every save verified and existing saves protected | ✅ | UI Automation cases A and B on the packaged exe; `test_gui.py`; `test_batch.py` |
| Reverse direction equally simple, several cards when needed | ✅ | UI Automation case C (28 saves → 15 + 13); `test_more_than_fifteen_saves_split_across_cards` |
| FILE numbers preserved, not confused with card blocks | ✅ | `test_file_numbers_not_directory_blocks` |
| Atomic from the user's view; rollback; recovery | ✅ | Transaction tests (failure, failure after a move, crash + recover, cancel during write) |
| No overwrite of sources, no Steam Cloud writes, no replacement without approval, no force for unsupported data | ✅ | `test_never_writes_source_or_cloud`, `test_occupied_destination_needs_approval`, matrix "occupied slot" |
| Memoria per save, same reconciliation as single saves | ✅ | `test_memoria_sidecars_judged_per_save` (identical models), matrix Memoria cases |
| One invalid save in a valid batch | ✅ | Blocks the batch, named per save; "Leave it out" converts the rest |
| GUI and CLI share one service, same answers | ✅ | `test_gui_plan_matches_service_and_cli`, `test_cli_batch_matches_service` |
| Background work, one conversion at a time, progress, cancel | ✅ | `test_double_click_starts_one_conversion`, `test_cancel_writes_nothing` |
| Light/dark, sizes, DPI, keyboard, no clipped controls | ✅ | 24 appearance cases on the packaged exe; unique access keys; Alt+C/Alt+M through UI Automation |
| Single-save conversion unchanged | ✅ | Byte-identical to v0.2 on 6 cases; all v0.2 engine tests unchanged and passing |
| Real in-game test of batch output | ✅ 2026-11-07 | Two-card batch PC file: both slots listed correctly and loaded in the Memoria copy (Disc 2 opening plays into a new map). Batch Card 02 loaded in DuckStation with matching menu stats. See TESTING.md "In-game" |

## Known limits

- One source file per conversion; a second card goes in with a second run (it lands in the next empty slot).
- Merging two PS1 cards into one PC slot is not automatic (each card gets its own slot); manual placement can do it.
- Manual placement is a text table (SLOT/FILE, CARD/FILE) in Advanced, not drag and drop.
- Offscreen test fonts are wider than Windows' own; real-window checks ran on this PC only (no clean machine, no
  Windows 10 machine, no physical 4K monitor; scale factors were emulated with `QT_SCALE_FACTOR`).
- Unchanged from v0.2: NTSC-U verified only, PAL with a warning, Japanese refused; Memoria gameplay mods experimental.

## Before a public release

1. Run the package on a clean Windows 10 and 11 machine.
2. Your decision on publishing (repository, tag, release): nothing has been published.
