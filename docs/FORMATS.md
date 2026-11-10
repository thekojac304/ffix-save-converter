# Save formats

All multi-byte values are little-endian. "Evidence" columns and confidence classes live in `FIELD_MAPPING.md`.

## 1. PS1 memory card

| Offset | Size | Content |
|---|---|---|
| 0x0000 | 128 | Card header frame, `MC` |
| 0x0080 + 128·n | 128 | Directory frame for block n (1-15): u32 state (0x51 = first block in use, 0xA0 = free), u32 size, u16 next-block link, char[20] filename at +0x0A, XOR checksum at +0x7F |
| 0x2000·n | 8192 | Block n |

Wrappers handled: DexDrive `.gme` (3,904-byte header `123-456-STD`), VGS/Connectix (`VgsM`, 64 bytes), PSP/Vita `.vmp` (`\0PMV`, 128 bytes; signature not checked or regenerated), PS3 `.psv` (`\0VSP`, data at 0x84; HMAC not checked), single save (128-byte directory frame + block), bare block (`SC`). Only raw cards were available as real fixtures; the other wrappers are tested with synthetic data.

FF9 directory filenames are `<product code><8 more chars>`, e.g. `BASLUS-0125100000-00`. All 54 fixtures use the disc-1 product code regardless of the disc they were saved on. Region table: `BASLUS-01251/01295/01296/01297` (NTSC-U), `BESLES-x2965..x2969` (PAL en/fr/de/it/es), `BISLPS-02000..02003` (NTSC-J).

## 2. FF9 PS1 save block (8,192 bytes, 0x1400 used)

| Offset | Size | Field | Status |
|---|---|---|---|
| 0x0000 | 256 | PS1 title frame: `SC`, 0x11 (1-frame icon), 1 block, full-width SJIS title `FF9/FILEnn/hh:mm` (playtime), 0x5E at 0x25, CLUT 0x60, 16x16 4bpp icon 0x80 | verified |
| 0x0100 | 4 | constant `05 00 03 00` in all 82 saves | constant |
| 0x0104 | 1 | disc bitmask 1/2/4/8 | verified |
| 0x0105 | 1 | leader level (preview) | documented |
| 0x0106 | 10 | leader name (PS1 text) | documented |
| 0x0110 | 28 | location name (PS1 text) — same strings as the PC preview | verified |
| 0x012C | 4 | playtime in frames | documented |
| 0x0130 | 3(+1) | gil (preview) | documented |
| 0x0134 | 4 × 16 | preview party: u8 present, u8 portrait id (Zidane 0, Vivi 1, Garnet 2, Steiner 4, Quina 5, Eiko 6, Freya 7, Amarant 8), name[10], u8 level, 3 junk bytes | new |
| 0x0174 | 12 | 0x178 = per-card save counter (1, 2, 3...); rest unknown | partial |
| 0x0180 | 1 | `mode` (1 field, 3 world) | new |
| 0x0181 | 1 | `prevMode` | new |
| 0x0182 | 30 | always zero in corpus (timer candidate) | unknown |
| 0x01A0 | 2 | `fldMapNo` | new, verified |
| 0x01A2 | 2 | `fldLocNo` (-1 on disc-change saves) | new, verified |
| 0x01A4 | 2 | `btlMapNo` | new, verified |
| 0x01A6 | 1 (+1 sign ext.) | `btlSubMapNo` | new, verified |
| 0x01A8 | 2 | `wldMapNo` (9000-9011) | new, verified |
| 0x01AA | 2 | `wldLocNo` | new, verified |
| 0x01AC | 20 | always zero in corpus (timer candidate) | unknown |
| **0x01C0** | **2048** | **`gEventGlobal`: all persistent event/story variables; u16 at +0 is the scenario counter** | **new, verified** |
| 0x09C0 | 16 | unknown; first u32 grows monotonically (possibly step or frame count) | unknown |
| 0x09D0 | 9 × 144 | PLAYER records (below) | mostly documented, completed here |
| 0x0EE0 | 4 | party `slot[4]` (player index, 9 = empty) | documented, transform new |
| 0x0EE4 | 2 | `escape_no` | verified |
| 0x0EE6 | 2 | `summon_flag` (bitmask, grows as eidolons are seen) | inferred |
| 0x0EE8 | 4 | `gil` | documented |
| 0x0EEC | 2 | `frog_no` | verified |
| 0x0EEE | 2 | `steal_no` | verified (user's own run) |
| 0x0EF0 | 2 | `dragon_no` | verified |
| 0x0EF2 | 46 | unknown; by RAM order 0xEF2-0xEF5 are probably btl_result, btl_flag, btl_rain, steiner_state | unknown |
| 0x0F20 | 256 × 2 | inventory (id, count) | documented |
| 0x1120 | 64 | key items: 2 bits per item (bit 2k obtained, 2k+1 used), as vanilla ff9item | verified |
| 0x1160 | 24 | unknown | unknown |
| 0x1178 | 6 | Tetra Master wins, losses, draws (i16) | documented |
| 0x117E | 105 × 6 | cards: id (0xFF empty), arrows, atk, type, pdef, mdef | documented |
| 0x13F4 | 10 | unknown | unknown |
| 0x13FE | 2 | CRC-16: reflected poly 0x8408, init 0xFFFF, no final XOR, over 0x0000-0x13FD | verified on 54/54 |

### PLAYER record (144 bytes)

| +Off | Field |
|---|---|
| 0x00 | name[10] (PS1 text, 0xFF-terminated; bytes after the terminator are leftovers) |
| 0x0A | `category` |
| 0x0B | `level` |
| 0x0C | `exp` u32 |
| 0x10 | `cur` {hp u16, mp i16, at i16, at_coef i8, capa u8} |
| 0x18 | `max` (same layout) |
| 0x20 | `trance` |
| 0x21 | `web_bone` |
| 0x22 | 2 bytes padding |
| 0x24 | `elem` {dex, str, mgc, wpr} |
| 0x28 | `defence` {p_def, p_ev, m_def, m_ev} |
| 0x2C | `basis` {max_hp i16, max_mp i16, dex, str, mgc, wpr} |
| 0x34 | u32 bitfield: bits 0-3 `slot_no`, 4-8 `serial_no`, 9 `row`, 10 `win_pose`, 11 `party`, 12-16 `menu_type`, 17-31 zero |
| 0x38 | `status` |
| 0x39 | `equip[5]` |
| 0x3E | `bonus` {dex, str, mgc, wpr, cap} u16 |
| 0x48 | 16 bytes unknown (zero in corpus) |
| 0x58 | `pa[48]` ability AP |
| 0x88 | `sa[2]` u32 support-ability bitmap (bit n = ability 192+n) |

Slot order is the "old" 9-slot order used by the PC format too: Zidane, Vivi, Garnet, Steiner, Freya, Quina (Cinna early), Eiko (Marcus early), Amarant (Blank early), Beatrix.

## 3. PC `SavedData_ww.dat` (vanilla 2016, 2,937,152 bytes)

| Offset | Reserved | Encrypted plaintext |
|---|---|---|
| 0x000000 | 320 | metadata (288 B → 304 B cipher): `SAVE`, f32 SaveVersion=1, i32 DataSize=17966, i32 LatestSlot, i32 LatestSave, f64 LatestTimestamp (unix), i32 GameFinished, i32 SelectedLanguage, i8 AutoLogin, u8 SystemAchievementStatuses, u8 ScreenRotation, 249 zero bytes |
| 0x000140 + 1024·(slot·15+file) | 1024 | preview (965 B → 976 B): `PREV`/`NONE`, bool HasData, i64 gil, u64 playtime s, u64 win_type, String128 location, 4 × {i32 serial (-1 = none), i32 level, String128 name}, f64 timestamp, 256 reserved |
| 0x025940 | 18432 | autosave block |
| 0x025940 + 18432·(1+slot·15+file) | 18432 | slot block (17,970 B → 17,984 B): `SAVE`/`NONE` + 17,966-byte schema payload |

10 slots × 15 files (0-based here; 1-based in the game menu). Bytes after each ciphertext inside its reserved area are zero in game-written files and are preserved on rewrite.

### Slot payload schema

Leaves are emitted depth-first with object keys sorted by the .NET culture comparer (punctuation < digits < letters, case-insensitive). Types and the full tree are in `src/ffix_conv/pc_schema.py`. Top-level modules in on-disk order: `10000_State`, `20000_Event` (`gEventGlobal` = base64 of 2,048 bytes in a 4,096-byte field), `30000_MiniGame`, `40000_Common`, `50000_Setting`, `60000_Sound`, `70000_World`, `80000_Achievement`, `91000_State`, `92000_Event`, `93000_MiniGame`, `94000_Common` (`player_bonus` = bonus.cap), `95000_Setting` (`00001_time` = playtime seconds as f64), `96000_Sound`, `97000_World`, `98000_Achievement`, `99000_Other`.

Independent cross-check: ffix-save-editor's fixed offsets (gil 0x1473, items 0x1477, PLAYER 0x1677 stride 0xF4, party 0x1F4B, playtime 0x3832) fall out of this schema exactly (`tests/test_pc.py`).

### Memoria

Memoria keeps writing the vanilla encrypted file (same layout and schema, Memoria-only state narrowed onto the vanilla fields) and adds a sidecar `SavedData_ww_Memoria_{slot}_{file}.dat` (0-based; `_Memoria_Autosave.dat` for the autosave) in SimpleJSON's binary format. On load it applies the container, then the sidecar, but only when the sidecar's `95000_Setting.00001_time` is within 1 s of the container's; a stale sidecar is ignored, a missing one means the container alone is loaded, and a corrupt one makes the slot unloadable. Moguri is a visual mod on top of Memoria and adds no save data. The sidecar format, field list and the converter's handling are in [MEMORIA_RESEARCH.md](MEMORIA_RESEARCH.md) and `src/ffix_conv/memoria.py`.

### Notes added in Phase 2

* **`menu_type` is 5 bits.** Early in the game, Cinna, Marcus and Blank use presets 17, 18 and 19. The first version read 4 bits; the Phase 2 audit found and fixed this.
* **Magic stones and support abilities.** Vanilla `PLAYER.ValidateSupportAbility` unequips *all* support abilities on load if `cur.capa != max.capa − Σ gem cost`. This identity holds on every PS1 and PC record in the corpus.
* **Card writer.** Directory frames are XOR-checked. Free blocks are `A0`, frames 16-35 are `FFFFFFFF`, and frame 63 is a copy of frame 0 (ePSXe layout; Beetle/RetroArch cards differ only in those reserved frames). A blank card plus a block reproduces an emulator-written card byte-for-byte.
* **Disc ranges for PC→PS1.** Scenario ≤3880 is disc 1, 3900–6960 disc 2, 6990–10980 disc 3, ≥10995 disc 4.
