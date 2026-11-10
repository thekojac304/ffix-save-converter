# Runtime verification protocol

The step-by-step user procedure lives in `tools/runtime_package/START_HERE.md`; it is copied into `runtime_test_package/` by `tools/build_runtime_package.py`. Readiness findings, checkpoint mapping and risks are in `reports/RUNTIME_READINESS.md`.

Pass criteria for a checkpoint (all required for Level 3):

1. It loads, and the location and party match `expected_values.json`.
2. Status, equipment, abilities (AP and equipped SAs, magic stones used/total), items, key items and card count match.
3. The next story trigger plays the correct scene.
4. A map transition and a battle work.
5. After saving with the PC game, quitting, restarting and reloading, everything persists.
6. `tools/analyze_runtime_result.py` shows no unexplained field changes between the converted slot and the game-written slot.

A load screen alone is a partial result. If a save loads but resumes the wrong story event, the conversion counts as failed.
