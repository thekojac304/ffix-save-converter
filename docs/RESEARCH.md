# Phase 1 — Existing tools, formats and licensing

Research date: 2026-11-06. Repositories were shallow-cloned into `research/repos/` (read-only reference; not modified).

## Tools assessed

| Project | Language | License | PS1 support | PC (2016) support | Cross-platform conversion |
|---|---|---|---|---|---|
| [gjoerulv/Memoria_FF9SaveEditor](https://github.com/gjoerulv/Memoria_FF9SaveEditor) | C# WinForms (.NET 2.0) | No LICENSE file; the bundled help file says "I keep Memoria in the public domain" | Raw cards, DexDrive `.gme`, PSV/VMP (read; checksums not re-signed), CRC repair, editors for characters/items/cards | Experimental `.dat`/`.sav` decrypt and editing of a few known offsets ("all data is editable in hex") | **None.** Templates/export are per-platform raw byte ranges; no story/event mapping |
| [nintendogamer15/ffix-save-editor](https://github.com/nintendogamer15/ffix-save-editor) | C# .NET 10 (Avalonia + CLI) | MIT | 8,192-byte block, 8,320-byte single save, 131,072-byte card; CRC repair | Vanilla rr2016 container (fixed AES key) by fixed offsets; Memoria tagged format | **None.** Edits each format in place; README lists rr2016 ability/AP records as unknown |
| [EuanFH/ff9SaveLib](https://github.com/EuanFH/ff9SaveLib) | Go | GPL-3.0 | **Unsupported** (README) | Full PC container + schema serializer, Switch JSON | PC ⇄ Switch only |
| [Albeoris/Memoria](https://github.com/Albeoris/Memoria) | C# (decompiled/patched game assembly) | MIT | none | The game's own serializer (`JsonParser.cs`, `SharedDataBytesStorage.cs`), runtime event engine | n/a — it is the PC runtime |

Supporting both formats does **not** imply conversion: no assessed tool maps PS1 event/story state to PC.

## Answers to the Phase 1 questions

1. **PS1 memory-card formats already supported:** raw `.mcr/.mcd/.srm` (all three tools that do PS1), `.gme` and PSV/VMP (gjoerulv), single-save `.mcs`-style wrappers (ffix-save-editor). This project supports raw, GME, VGS, VMP, PSV, MCS and bare blocks (`src/ffix_conv/ps1_card.py`); only raw cards were available as real fixtures.
2. **PS1 save block:** one 8 KB block, 0x0000-0x13FF used, CRC-16 at 0x13FE. Before this project only preview, characters (partially), items, gil, party and cards were documented. This project established the state block (0x180/0x1A0), the 2,048-byte event-variable array at 0x1C0, the full PLAYER record incl. `info` bitfields, rare items and party counters. See `docs/FORMATS.md`.
3. **PC serialization:** the game builds a JSON tree and a parallel type-schema tree (`JsonParser.cs`), flattens both depth-first with object keys sorted, and writes raw little-endian values (`SharedDataBytesStorage.cs`). Slot payload is 17,966 bytes after a `SAVE` magic.
4. **PC encryption/validation:** AES-256-CBC, PKCS7, key+IV from PBKDF2-SHA1("System.Security.SecureString", salt 03 03 01 04 07 00 09 07, 1000 iterations). Same key/IV for every section, so encryption is deterministic. Validation is only the `SAVE`/`PREV`/`NONE` magics, padding and the metadata `DataSize`; there is no checksum or signature.
5. **Documented field mappings before this work:** per-platform offsets for gil, items, cards, characters (subset), party, playtime. No cross-platform mapping of event/story state existed.
6. **Existing converters/import-export:** ff9SaveLib PC⇄Switch; gjoerulv raw-byte templates; ffix-save-editor nothing cross-format.
7. **Complete PS1→PC conversion:** no existing tool.
8. **Can Memoria establish more mappings?** Yes, decisively: `JsonParser.cs` writes the PC fields in the order of the original PS1 C structs (state, party, PLAYER), and `EventState.gEventGlobal` is a 2,048-byte array that real fixtures show is byte-compatible with PS1 0x1C0-0x9BF. Memoria also shows which PC fields are dummies (`Settings.time` always -1, `gStepCount` never tracked, `web_bone` never read) and how Memoria's optional sidecar file is applied.
9. **Reuse and licenses:**
   * Memoria (MIT): schema field names/types transcribed into `pc_schema.py`; defaults from `FF9CFG.cs`. Attribution in `NOTICES.md`.
   * ffix-save-editor (MIT): PS1 Latin text table (`ps1_save.py`), offset cross-checks. Attribution in `NOTICES.md`.
   * ff9SaveLib (GPL-3.0): **no code copied**; used only as an independent reference and for its test fixture. Copying its Go code would impose GPL on this project.
   * gjoerulv editor: no code copied (no license file; help file claims public domain). Offsets used as facts.

## Known format differences (summary)

| Aspect | PS1 | PC 2016 |
|---|---|---|
| Container | Memory card, 1 block per save, 15 per card | One 2.9 MB file: metadata + 150 previews + autosave + 150 slots |
| Integrity | CRC-16 over 0x0000-0x13FD | AES-CBC padding + magics only |
| Encoding | Packed C structs | Schema-sorted leaves; strings UTF-8 in 128/4096-byte fields; gEventGlobal base64 |
| Text | Game-specific 8-bit table | UTF-8 |
| Party empty slot | 9 | 255 |
| PLAYER.info | 2 bytes of bitfields | 6 separate bytes |
| bonus.cap | inside PLAYER (+0x46) | separate array `94000_Common.00001_player_bonus` |
| Cards | 105 records x 6 bytes, may have gaps | 100 records x 11 bytes, packed, `cpoint`=10, empty = all 255 |
| Playtime | frames (60 Hz NTSC / 50 Hz PAL) in preview | seconds as double |
| PC-only | — | achievements, Steam settings, world-camera floats, reserved buffers |

## Remaining unknowns at the end of Phase 1 (all addressed or recorded later)

Event-state compatibility (resolved: compatible), PS1 state block (resolved), PLAYER tail fields (resolved except +0x48-0x57), timer and config location (still unknown), PAL/JP differences (no fixtures).
