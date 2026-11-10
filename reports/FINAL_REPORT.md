# FFIX PS1 → PC save conversion: final report (Phase 1)

> **Superseded in part by `reports/RUNTIME_READINESS.md` (Phase 2).** The Phase 2 audit against the vanilla game code
> fixed three defects in this Phase 1 converter (5-bit `menu_type`, −1 achievement lists, default key bindings),
> upgraded most "inferred" fields to verified, and added PC → PS1 conversion. The Phase 1 runtime kit in
> `reports/runtime_test_kit/` predates those fixes. Use `runtime_test_package/` instead.

Date: 2026-11-06 · Code: `src/ffix_conv` · Tests: 157 passed, 0 failed (`reports/test_results.txt`)

## 1. Executive assessment

**Technically feasible but incompletely verified.**

The obstacle earlier tools hit, story progression, turns out to be solvable. The 2016 PC release serialises a
direct port of the PS1 game structures. The PS1 save's 2,048-byte event-variable array (block offset
0x1C0) is the same `gEventGlobal` the PC stores base64-encoded. Saves made by different players at the same
story point agree on 2,024 of 2,048 bytes (scenario 1155) and 1,846 of 2,048 (scenario 9950). Map/location
numbers use the same ID space and match exactly on the overlapping checkpoint. Every field of the PC slot
schema is now either mapped from the PS1 save or filled by a documented rule.

The converter produces structurally valid vanilla PC containers for all 54 PS1 fixtures. Every mapped
value survives a full encode, encrypt, decrypt and decode cycle. **The converted saves have not been
loaded in the game** (§5), so the converter **cannot be called Level 3**. Its capability level is
"Level 3 candidate": character, world-state and story/event data are all transferred, but there is no runtime evidence yet.

## 2. Fixture corpus

| | Count | Notes |
|---|---|---|
| PS1 files | 54 `.mcr` (from 54 zips) | FantasyAnime, NTSC-U, chronological across all 4 discs; all CRCs valid |
| PS1 occupied FF9 slots | 54 | one per card |
| PC files | 5 | 3 Steam-thread containers, the ff9SaveLib test fixture, the ffix-save-editor Memoria example |
| PC occupied slots | 14 | ff9SaveLib fixture 6, Steam "cd 3" thread 6, two jump-rope uploads 1 each; the Memoria example is recognised, not decoded |
| Failed / unusable candidates | 2 dead links (Google Drive 404, matthewfarmery.net 404) | recorded in `fixtures/provenance.jsonl` |
| Not attempted | 39 GameFAQs PS1 saves, GameFAQs PC page | behind a Cloudflare bot challenge; not bypassed |
| Corrupt / mislabeled | 0 | |

**Story coverage:** all 21 milestone bands in `tools/build_manifest.py` have PS1 saves, from the opening
in Alexandria to Necron's antechamber. The PC slots cover the opening of Alexandria, the start of Disc 2,
the start of Disc 3, the Desert Palace/Oeilvert, Gulug, the Disc 4 open world and endgame sidequest saves at level 99.

**Credible cross-platform checkpoint pairs** (`reports/crossplatform_pairs.json`): 6 with identical scenario counters
(1155 Alexandria/Steeple, 1190 A. Castle/Guardhouse [same field 150], 9950 Gulug, 11100 Gegalrich/Pualei,
11765, 11770) and 4 more within 10 units (9400/9410, 9700/9705, 9745/9750, 9825/9830). For 10 of 14 PC slots the
most byte-similar PS1 `gEventGlobal` in the corpus is at the same story point. The other 4 are 99-level
endgame saves with no PS1 equivalent in the corpus.

**Missing:** PAL and Japanese PS1 saves; PC saves that are byte-identical in story state to a PS1 save; a
pair made by the *same* player (which would allow exact value equality for the "inferred" fields).

## 3. Format documentation

* `docs/FORMATS.md`: PS1 memory card, the full FF9 PS1 block (now including the state block, `gEventGlobal`,
  the complete PLAYER record with `info` bitfields, and key items), and the PC container and schema.
* `docs/FIELD_MAPPING.md` / `docs/field_mapping.json`: 48 mapping rows. 21 are verified-equivalent, 6 verified-transformable,
  13 inferred, 3 unknown and 5 platform-specific. Each row lists its evidence and the regression test that covers it.
* `docs/RESEARCH.md`: tool assessment, licensing, and answers to the Phase 1 questions.

New findings beyond previous public documentation: the PS1 state block (0x180/0x1A0), `gEventGlobal` at
0x1C0 and its equivalence with the PC copy, the 5-bit `serial_no` (bit 4 in +0x35 bit 0), `bonus.cap` at +0x46 mapping
to PC `94000_Common.player_bonus`, the party "empty" code (9 on PS1, 255 on PC), Tetra Master `cpoint` = 10 for all 100 IDs,
the PS1 CRC range, and the PC schema's exact size (17,966 bytes) and ordering rules.

## 4. Converter implementation

Completed:
* Detection of raw cards, GME, VGS, VMP, PSV, single-save and bare-block inputs; FF9 slot listing and `--block` selection.
* PS1 parsing with CRC and region checks; canonical model (`model.py`) with raw unmapped bytes kept in the report.
* PC container read/write with lossless round trips: all 14 real slots and all 4 real containers re-serialise byte-identically.
* A blank vanilla container built from the documented layout; its empty sections are byte-identical to the game's.
* Insertion into an existing container that leaves unrelated slots, previews and settings untouched and refuses to overwrite.
* A JSON conversion report listing mapped, transformed, defaulted and dropped fields, plus warnings.
* A CLI (`python -P -m ffix_conv inspect|convert`), deterministic output (`--timestamp`), and no in-place writes.

Rules for unresolved fields: timer = 0/False/False (PS1 candidate regions are zero in every fixture); `gStepCount` = 0 (the PC never tracks it);
settings from a PC template slot, or else documented defaults; world camera from the template, or else 0; achievements and reserved buffers = 0.

Limitations: Japanese saves are rejected (text table); PAL is accepted with a warning (layout assumed identical); disc-change
saves ("Start of DISC 3/4", `fldLocNo = -1`) convert to valid field IDs but are a special case that needs runtime testing;
Memoria's sidecar format is read-detected only, not written.

## 5. Testing results

* 157 tests pass: 54 PS1 fixtures parsed with CRCs valid, 54 conversions with semantic round trips, 4 PC containers round-tripped
  byte-identically, and cross-platform pair assertions (state, `gEventGlobal` similarity, names, core stats, info bits, party transform,
  items, key items). Negative cases cover corrupt card headers, truncation, bad directory frames, CRC mismatches, invalid
  containers, wrong metadata DataSize, corrupt ciphertext, slot range, occupied target slots, more than 100 cards, invalid party
  or card values, a bad `gEventGlobal` length, out-of-range gil, maximal inventory/abilities, and CLI overwrite refusal.
* Wrapper formats other than raw cards are tested only with synthetic data, built from real blocks and labelled as synthetic.
* **Gameplay verification: not performed.** A vanilla Steam install exists (E:, build 5378074, never launched), but the
  agent has no way to see or drive the game window, and writing to the live save folder would sync to Steam Cloud.
  A ready-made test kit (`reports/runtime_test_kit/`, 10 checkpoints) and a 13-step protocol are provided.

Tested vs untested fields: every mapped field has a round-trip test. Fields with cross-platform equality tests are state,
`gEventGlobal` (similarity), names, category/level/exp/stats/equipment/status/trance, info, party slots and items.
Inferred-only fields are `sa`, `bonus` (incl. cap), key items, party counters, card W/L/D and playtime scaling.

## 6. Remaining blockers

1. Runtime evidence (Phase 9). This is the only thing standing between the current state and a Level 3 claim.
2. Exact-value proof for the inferred fields (`sa` bitmap order, `bonus`, key items, `escape_no`/`summon_flag`/`steal_no`).
   This needs a same-player pair or an in-game check (protocol step 5).
3. The location of the PS1 timer and config fields. Neither is needed at normal save points, but timed sequences would need the timer.
4. PAL and Japanese layouts.
5. Unknown PS1 regions with no PC counterpart (0x0100-0x0104, 0x0174-0x017F, 0x09C0-0x09CF, 0x0EF2-0x0F1F, 0x1160-0x1177,
   0x13F4-0x13FD, PLAYER +0x48-0x57). They are reported in every conversion and not written. Some may be PS1-only runtime caches.

## 7. Next steps (by impact on gameplay continuity)

1. Run `docs/RUNTIME_TEST_PROTOCOL.md` on the 10 kit checkpoints in vanilla PC: first FA 01/02/41 (exact pairs), then the disc-change saves.
2. In-game check of support abilities and key items on the Gulug and Crystal World checkpoints. This settles the `sa` and key-item inferences.
3. Repeat on Memoria/Moguri.
4. Get PAL/JP fixtures (GameFAQs through a normal browser session, or user-supplied) and extend the region handling.
5. Optionally, locate the PS1 timer/config by saving during the Festival of the Hunt or after changing settings on an emulator.
