# Memoria / Moguri save research

Status: source-level research (read-only), 2026-11-06. Sources are the local clones under `research/repos/`:

* **Memoria** (`research/repos/Albeoris_Memoria`, MIT). The paths below are relative to `Assembly-CSharp/` unless they say otherwise.
* **ffix-save-editor** (`research/repos/nintendogamer15_ffix-save-editor`, MIT): `src/FFIX.SaveEditor.Core/MemoriaFormat.cs`, `tests/FFIX.SaveEditor.Tests/MemoriaTests.cs`, `NOTICES.md`.
* **Sample sidecar:** `fixtures/pc/originals/repos/ffixsaveeditor_example_SavedData_ww_Memoria_0_0.dat`. It is 32,820 bytes and byte-identical to the editor's `examples/SavedData_ww_Memoria_0_0.dat`. It is a fresh-game save (Zidane Lv1, 500 gil).
* **Memoria mod catalog** (`https://raw.githubusercontent.com/Albeoris/Memoria/mod-catalog/MemoriaCatalog.xml`, the URL in `Memoria.Launcher/Utils/Catalog/MemoriaCatalogEndpoints.cs:7`) and the Moguri Mod site (`https://sites.google.com/view/moguri-mod`). Both were only read.

Everything in this document was paraphrased. No Memoria code was copied.

**Correction to `docs/FORMATS.md` ("Memoria" paragraph):** the sidecar is **not plain JSON**. It is SimpleJSON's *binary* serialization, a tagged little-endian tree described in section 5. The rest of that paragraph is accurate: 0-based `{slot}_{file}`, the 1-second playtime check, and Moguri being visual-only.

---

## 1. The vanilla container `SavedData_ww.dat` under Memoria

**Memoria still writes the vanilla container on every save, with the same layout and encryption.**

* **Path selection.** `Global/Shared/Data/SharedDataBytesStorage.cs`, `SetPCPath()` (lines 28-80):
  * The folder is `Application.persistentDataPath + "/Steam/EncryptedSavedData"`. On Windows Steam that is `%USERPROFILE%\AppData\LocalLow\SquareEnix\FINAL FANTASY IX\Steam\EncryptedSavedData\`.
  * The file name comes from a `SavedData_??.dat` glob:
    * none present: `SavedData_jp.dat` if the language is JP, otherwise `SavedData_ww.dat`;
    * exactly one present: that file;
    * several present: the one with the newest write time.
  * A quirk on the Microsoft Store build (`PCEStorePlatform`): `DirPath` becomes `My Games/FINAL FANTASY IX/EncryptedSaveData`, but `FilePath` is still built from `Application.persistentDataPath`. The sidecar path is derived from `FilePath` (see section 2).
* **Layout constants.** `MetaData` nested class, lines 1355-1366:
  * 320-byte metadata area;
  * 150 previews of 1,024 bytes (10 slots × 15 files);
  * 1 autosave block plus 150 save blocks, 18,432 bytes each;
  * `BaseSaveBlockOffset = 320 + 150·1024`.
  * The block offset is `Base + 18432·(1 + slot·15 + file)`. The autosave is block 0 (`Load` lines 558-560, `Save` lines 692-694).
  * These are identical to the layout the converter already uses.
* **Encryption.** Encryption is unchanged: `this.Encryption` (`SharedDataAesEncryption.cs`), applied per block.
* **Payload.** The plaintext is `"SAVE"` followed by fixed-width leaves (`WriteDataToStream`, lines 321-374). The leaves are walked depth-first with sorted keys (`ParseJsonTreeToDataList`, lines 154-210).
* **Schema.** The schema comes from `JsonParser.ParseFromFF9StateSystem(root, schema)` (`Global/JsonParser.cs` lines 33-227). It covers modules `10000_State` … `99000_Other`, with the same key names and types the converter already has in `pc_schema.py`. This includes `94000_Common.00001_player_bonus`, `95000_Setting.00001_time` (f64 playtime), and the `98000_Achievement` flags.
* **The schema is necessarily identical to vanilla.**
  * `Load` computes `DataSize` from the schema and rejects any block whose decrypted length is not `DataSize + 4` (lines 563-582).
  * Memoria therefore can read vanilla saves only because the schema byte size matches.
  * Separately, the converter's Memoria-derived `pc_schema.py` produces files that the vanilla Steam build 5378074 loads (see `COMPATIBILITY.md`).
  * **No keys are added and no sizes change.** `gEventGlobal` is still a `String4K` holding base64 of 2,048 bytes.
* **`MemoriaExtraData` never reaches the container.**
  * `ParseFromFF9StateSystem` adds a top-level `MemoriaExtraData` node to the *data* tree (JsonParser lines 229-238) but never to the *schema* tree.
  * `Save()` removes that node from the root before flattening (line 654).
  * So the container never sees it.
* **Slot counts are unchanged** (10 × 15 plus autosave). Strings are unchanged too: names are still String128, UTF-8, zero-padded and truncated at 128 bytes.
* **Autosave.**
  * Vanilla has an autosave block.
  * Memoria adds `[SaveFile]` options (`Memoria.Configuration/Memoria.ini` lines 340-346): `DisableAutoSave` (checked in `WinIosAndrSharedDataSerializer.Autosave`, line 92), `AutoSaveOnlyAtMoogle` (`Global/Event/Engine/EventEngine.cs:618`) and `SaveOnCloud`.
  * `EventEngine.cs:605-623` also adds a list of fields where autosave is suppressed.
* **Cloud.**
  * With `SaveOnCloud`, a moogle save uploads the whole container (`SaveLoadUI.cs:618`).
  * A cloud download writes the raw container with `File.WriteAllBytes` (`SaveRawData`, lines 772-787).
  * **Neither path touches the sidecars.**

### What Memoria changes *inside* the vanilla container (content, not schema)

The container is written with `oldSaveFormat = true`, which projects Memoria's richer runtime state onto the vanilla fields:

| Vanilla field | Memoria projection (JsonParser line) | Consequence |
|---|---|---|
| `40000_Common.players[9]` | `SelectOldSaveSlot` (1818-1838): slots 0-4 = Zidane..Freya; 5/6/7 = Quina/Eiko/Amarant if `sub_replaced`, else Cinna/Marcus/Blank (`category` bit 0x10 = temp); slot 8 = Beatrix; custom character ids ≥ 12 → not stored | Same 9-record model as PS1 |
| `players[].equip[5]` (u8) | `(Int32)equip` cast to **Byte** by the writer (line 857, `WriteDataToStream` 331-332) | Item ids ≥ 256 are **silently wrapped mod 256** (they become a *different* vanilla item) |
| `players[].pa[48]` (u8) | `p.pa[j]` for j < 48, cast to Byte (875-879) | Indexed by the *current* preset's ability list; AP > 255 wraps; extra entries are dropped |
| `players[].sa[2]` (u32) | Bitfield of support abilities 0-63 (`ff9abil.FF9Abil_SetEnableSA`, `Memoria/Data/ff9abil.cs` 118-136) | SAs ≥ 64 (`sa_extended`) are lost |
| `cur/max.capa` (u8) | Explicit `(Byte)` (801, 809) | Memoria's capa is u32 |
| `cur/max.hp` u16, `mp` i16, `basis.max_hp/max_mp` i16 | Writer casts | Values above the vanilla widths wrap |
| `status` (u8) | `(Int32)status` → Byte (854) | Only permanent statuses (bits 0-7: Petrify…EasyKill) survive |
| `info.slot_no/serial_no/menu_type` (u8) | `(Byte)` casts (836-843) | Custom presets/serials survive only if < 256 (PS1 bitfield is narrower: serial 5 bits, menu_type 5 bits) |
| `slot[4]` (party) | `(Byte)SelectOldSaveSlot(member)`; an unmappable member → 255 (920) | A custom character in the party shows as an empty slot |
| `items[256]` | Items with id ≥ 256 are skipped (960-965); count is a Byte (`FF9ITEM.count`) | Mod items are dropped from the container |
| `rareItems[64]` | `GetRareItemByteFormat` (`Global/ff9/State/FF9StateGlobal.cs` 870-885): 2 bits per item, ids 0-255 | Rare items with id ≥ 256 are dropped |
| `dragon_no` | `categoryKillCount[3]` (932) | The other 7 categories are not in the container |
| `30000_MiniGame.MiniGameCard[100]` | Card ids ≥ 100 are skipped; only the first 100 cards (697-735) | `[TetraMaster] MaxCardCount` > 100 (`Memoria.ini` 264/280) is truncated |
| `20000_Event.gEventGlobal` | Written verbatim, 2,048 bytes (579) | Unchanged |

---

## 2. Sidecar files: names and indices

* **Naming.** `MetaData.GetMemoriaExtraSaveFilePath(isAutosave, slotID, saveID)` (SharedDataBytesStorage.cs 1390-1396) strips `.dat` from the container path and appends:
  * `_Memoria_{slotID}_{saveID}.dat` for a normal save;
  * `_Memoria_Autosave.dat` for the autosave.
  * The sidecars sit in the **same folder** as the container, for example:
    * `SavedData_ww_Memoria_0_0.dat` … `SavedData_ww_Memoria_9_14.dat`
    * `SavedData_ww_Memoria_Autosave.dat`
    * `SavedData_jp_Memoria_…` for a JP container.
  * These names do not match the `SavedData_??.dat` glob, so they never get picked as the container.
* **Indices** are the same 0-based `slotID` (0-9) and `saveID` (0-14) that select the container block `1 + slot·15 + save`. Slot index 0 / file index 0 is the first save in the UI.
* **Written by** `Save()` lines 702-703 after the container block is written. This happens every time a normal save or autosave succeeds.
  * Memoria always produces a `MemoriaExtraData` node (JsonParser 229-238), so a sidecar is always (re)written.
  * The container write and the sidecar write are **not atomic**. If the sidecar write throws, `Save` returns false (catch at 707-712), but the container block has already been rewritten.
* **Nothing deletes sidecars.** `GetMemoriaExtraSaveFilePath` is used only by `Load` and `Save`.
* **Non-truncating writer.** `JSONNode.SaveToFile` (`SimpleJSON/JSONNode.cs` 536-543) opens the file with `File.OpenWrite`, which does **not truncate**. A shorter new sidecar therefore leaves the old file's tail behind it.
  * Readers must stop after the root node and ignore trailing bytes. ffix-save-editor tests this case: `MemoriaTests.DocumentPreservesStaleBytesLeftByMemoriasNonTruncatingWriter`.
  * A writer that creates a sidecar should truncate the file (or write a fresh one).

## 3. How a sidecar is associated with a vanilla save

* **By file name only.** The path is derived from the container path plus slot and file numbers.
* **There is no id, hash or link field on disk.** On load, Memoria adds `MetaDataSlotID`, `MetaDataSaveID` and `MetaDataFileName` (SharedDataBytesStorage 633-635), but only to the in-memory node (`-1/-1` for the autosave). They are never written back, because `Save` serializes a fresh tree.
* **The only consistency check is playtime:**
  * the sidecar's `95000_Setting.00001_time` (f64 seconds)
  * is compared with the container's `Data.95000_Setting.00001_time`.

## 4. Load order and precedence

Load runs `WinIosAndrSharedDataSerializer.OnDataLoadFinish` (lines 76-87), then `JsonParser.ParseToFF9StateSystem(rootNode)` (JsonParser 251-358):

1. **Container block.** `SharedDataBytesStorage.Load` (543-640) decrypts the block, checks `SAVE`/`NONE`, and rebuilds the vanilla tree.
2. **Sidecar attach.** If the sidecar file exists, it is deserialized and attached as `rootNode["MemoriaExtraData"]` (627-638).
3. **Vanilla modules.** `ParseToFF9StateSystem` applies the vanilla modules first: `10000_State`, `20000_Event`, `30000_MiniGame`, `40000_Common`, `50000_Setting`, `60000_Sound`, `70000_World`, `80000_Achievement`. It then applies `94000_Common` (bonus.cap), `95000_Setting` (sets `Settings.time`, `hasTime = true`) and `98000_Achievement`.
4. **Staleness check** (322-334). If the sidecar has `95000_Setting.00001_time` and it differs from the container's time by **more than 1.0 s**, the sidecar is ignored and a log message is written.
5. **Sidecar overrides.** If the sidecar is still valid, it is applied *after* the vanilla data, so **the sidecar wins**:
   * `20000_Event` (337-338): `gStepCount`, the whole `gEventGlobal`, `gAbilityUsage`, `gScriptVector`, `gScriptDictionary`;
   * `40000_Common` (339-340): each listed player's fields, party `slot`, gil, counters, the item list (cleared and rebuilt), rare items (cleared and rebuilt), `battle_no`;
   * `30000_MiniGame` (341-342): replaced completely.
   * Each field is applied only if present (`!= null` checks), so a partial sidecar overrides only what it contains.
6. **Post-pass for every player** (344-357): if `bonus.cap == 0`, it is derived; then `ValidateMaxStone`, `FF9Play_Update` and `FF9Play_UpdateSerialNumber` run.

Notes:
* **Legacy ability usage.** When the event module has no `gAbilityUsage` (always true for the container), ability-usage counters are seeded from `gEventGlobal[1100+i]` for i = 1..191 (lines 535-540). This is the legacy location ("used to be stored in gEventGlobal").
  * Current Memoria never writes those bytes back: `EventState.IncreaseAAUsageCounter` (`Global/Event/EventState.cs` 46-51) updates only the dictionary.
  * The counters are read only by Memoria features (`EBin.cs` 448-449 `ABILITY_USE_COUNT` script function; `BattleCalculator.AbilityUsage`).
* **No length check on `gEventGlobal`.** `ParseEventJsonToData` takes `gEventGlobal` from base64 without checking its length (line 522). A sidecar with a different-length array would replace the 2,048-byte buffer. `EventState.cs:10` and `EventEngine.Initialize.cs:54` always allocate exactly 2,048 bytes.

## 5. Sidecar binary format (SimpleJSON binary)

**Sources:**
* writer: `SimpleJSON/JSONClass.cs` 202-211, `JSONArray.cs` 132-139, `JSONData.cs` 55-88;
* reader: `JSONNode.cs` 557-597;
* tags: `JSONBinaryTag.cs`.

The format was confirmed by a Python parse and re-serialize of the sample, which reproduced it byte-for-byte with 0 trailing bytes. Tag counts in the sample: i32 1839, class 689, array 45, string 27, f64 1.

* **Encoding conventions.** Everything is .NET `BinaryWriter` output:
  * little-endian;
  * `int32` = 4 bytes LE;
  * `double` = IEEE-754 8 bytes LE;
  * `float` = 4 bytes LE;
  * `bool` = 1 byte (0/1).
* **Strings.** A string is a .NET `BinaryWriter.Write(string)`: a 7-bit-encoded (LEB128-style) **byte** length, then that many UTF-8 bytes, with no terminator.
* **Nodes.** Every node starts with an `int32` tag:

| Tag | Name | Payload after the tag |
|---|---|---|
| 1 | Array | `int32 count`, then `count` nodes |
| 2 | Class (object) | `int32 count`, then `count` × (`string key`, node) |
| 3 | Value (string) | `string` |
| 4 | IntValue | `int32` |
| 5 | DoubleValue | `float64` |
| 6 | BoolValue | `uint8` |
| 7 | FloatValue | `float32` |

* **The root is a Class.** Any other tag throws "Unknown tag" in Memoria, and an exception there makes `Load` return null, which **fails the whole slot load** (outer catch, SharedDataBytesStorage 641-645). A malformed sidecar therefore makes the save unloadable under Memoria. A missing sidecar does not.
* **Key order** is `Dictionary` insertion order. Memoria's reader does not care about order. To reproduce Memoria output exactly, use the order in the table in section 6.
* **Tag choice when writing** (`JSONData.Serialize`). SimpleJSON stores every leaf as a string, then picks the first tag whose round trip reproduces the string exactly:
  1. **Int.** `Int32.TryParse`, then `ToString()`. Equal → tag 4.
  2. **Float.** `Single` round trip (default "G", about 7 significant digits). Equal → tag 7.
  3. **Double.** `Double` round trip (about 15 digits). Equal → tag 5.
  4. **Bool.** The `AsBool` setter produces lowercase `true`/`false`, so only those exact strings match. Equal → tag 6.
  5. **Otherwise** → tag 3.

  Practical consequences:
  * All ordinary integers that fit in int32 → **tag 4**.
  * C# booleans (`Boolean.ToString()` = `True`/`False`, capitalized) → **tag 3 strings**. This applies to `sub_replaced`, `obtained` and `used`. Memoria's reader parses them case-insensitively.
  * `00001_time` is normally **tag 5**. It is tag 4 if the playtime is an exact integer, and **tag 7** if its shortest decimal form has ≤ 7 significant digits (e.g. `587.5`).
  * Integers > 2^31-1 (u32/u64 such as large `status` or `exp` values) → tag 5 (double). Values above 2^53 lose precision.
* **Reader requirements.**
  * Accept all 7 tags.
  * Treat numbers by value, not by tag.
  * Parse booleans case-insensitively from strings or tag 6.
  * Ignore trailing bytes.
  * Reject negative counts and string lengths that run past the end of the file.
* **Writer recommendations.**
  * Emit ints as tag 4, `time` as tag 5, booleans as tag-3 `"True"/"False"`, strings as tag 3.
  * Use Memoria's key order.
  * Truncate the file.
  * Memoria's reader accepts any of these tag choices, so exact tag mimicry is optional. It is needed only for byte-identical round trips.
* **Culture.** Memoria never sets `CultureInfo`, so `ToString()` uses the process culture. This only affects which tag is chosen for non-integers (the double is stored in binary). It has no effect on the sample, which is all integers plus one double.

## 6. Sidecar fields

The top level has four keys in this order: `95000_Setting`, `20000_Event`, `40000_Common`, `30000_MiniGame` (JsonParser 229-238; the sub-builders run with `oldSaveFormat = false`).

"Container" below means the same data also exists in the vanilla container. "PS1" says whether the value can be represented in a PS1 save. The PS1 limits come from `docs/FIELD_MAPPING.md`.

### `95000_Setting`
| Key | Type (tag) | Meaning | Container | PS1 |
|---|---|---|---|---|
| `00001_time` | f64 (5; may be 4/7) | Playtime in seconds at save; used only for the staleness check | yes (`Data.95000_Setting.00001_time`) | yes (frames) |

### `20000_Event` (575-625)
| Key | Type | Meaning | Container | PS1 |
|---|---|---|---|---|
| `gStepCount` | int | Step counter (not tracked; 0) | yes | n/a (PC-only, dummy) |
| `gEventGlobal` | string, base64 of 2,048 bytes | Event/story variables (identical to the container's copy when written) | yes | yes (0x1C0-0x9BF) |
| `gAbilityUsage` | array of `{id:int BattleAbilityId, count:int}` | Use count per active ability (Memoria-only; read only by Memoria script/battle features) | no (legacy copy at `gEventGlobal[1100+id]` is no longer updated) | no; safe to drop for vanilla scripts |
| `gScriptVector` | array of `{id:int, entries:[int…]}` | Memoria-extended script storage (vector variables) | no | **no**; non-empty means modded scripts depend on it |
| `gScriptDictionary` | array of `{id:int, entries:[{id:int, value:int}…]}` | Memoria-extended script storage (dictionary variables) | no | **no**; non-empty means modded scripts depend on it |

### `40000_Common` (765-1014)
Top-level keys in order: `players`, `slot`, `escape_no`, `summon_flag`, `gil`, `frog_no`, `steal_no`, `humanoid_no`, `beast_no`, `devil_no`, `dragon_no`, `undead_no`, `stone_no`, `soul_no`, `flight_no`, `kills_per_model`, `items`, `rareItemsEx`, `battle_no`.

`players` is an array with **one entry per defined character**. It has 12 in vanilla data (Zidane … Amarant, Cinna, Marcus, Blank, Beatrix), in `PlayerList` order, and more if a mod defines characters. On load, players are matched by `info.slot_no` (a CharacterId), not by array position (1136-1143). Unknown ids are skipped.

Per-player keys, in order:

| Key | Type | Meaning | Container | PS1 |
|---|---|---|---|---|
| `name` | string | Display name | yes (String128) | if encodable in the PS1 table (8 chars) |
| `category` | int | Category bits (0x10 = temporary/guest) | yes | yes |
| `level` | int | Level | yes | yes (≤ 99) |
| `exp` | int (u32) | EXP | yes | yes |
| `cur` / `max` | `{hp, mp, at, at_coef, capa}` ints | Current/max HP, MP, ATB, ATB coefficient, magic stones | yes, capa/hp/mp narrowed | only within u16/i16/u8 ranges |
| `trance` | int | Trance gauge | yes | yes |
| `web_bone` | int | Weapon bone (written as `web_bone`, read as `wep_bone`, so never read) | yes | yes |
| `elem` | `{dex, str, mgc, wpr}` | Current Speed/Strength/Magic/Spirit | yes | yes (u8) |
| `defence` | `{p_def, p_ev, m_def, m_ev}` | Defence values | yes | yes (u8) |
| `basis` | `{max_hp, max_mp, dex, str, mgc, wpr}` | Base stats | yes | i16/u8 ranges |
| `info` | `{slot_no, serial_no, row, win_pose, party, menu_type, sub_replaced}` | CharacterId (0-11+), serial, row, win pose, party flag, preset id, `sub_replaced` ("True"/"False": Quina/Eiko/Amarant own the shared slot) | partly (slot_no remapped, no `sub_replaced`; encoded via `category` 0x10) | slot_no ≤ 8 old index, serial < 32, menu_type < 32 |
| `status` | int/double (u64 `BattleStatus`) | Persistent statuses | low 8 bits | low 8 bits |
| `equip` | array[5] of int | Weapon, head, wrist, armor, accessory item ids (255 = none) | yes, but **wrapped to u8** | only ids < 256 that are vanilla items |
| `bonus` | `{dex, str, mgc, wpr, cap}` | Level-up stat bonuses and stat-cap bonus | yes (`cap` in `94000_Common.player_bonus`) | yes |
| `pa_extended` | array of `{id, cur}` | AP per learnable ability, keyed by "any-ability id" (pool·256 + active id, or pool·256 + 192 + support id; `ff9abil.cs` 316-360) | yes as `pa[48]` by position (vanilla presets) | only if `id < 256` and the list matches the vanilla preset; AP ≤ 255 |
| `sa_extended` | array of int (SupportAbility) | Enabled support abilities | yes as bits 0-63 in `sa[2]` | ids 0-63 only |
| `pa` / `sa` | arrays | Used **instead of** `pa_extended`/`sa_extended` only if the character's preset has no ability table (873-884) | yes | as above |
| `maxHpLimit`, `maxMpLimit`, `maxDamageLimit`, `maxMpDamageLimit` | int | Caps (vanilla 9999 / 999 / 9999 / 999) | no | only the vanilla values are meaningful; other values mean a mod or setting |
| `basis_capa`, `basis_max_capa` | int | Base magic stones | no (derived from cur/max capa when absent, 1293-1300) | derivable |

Party and global keys:

| Key | Type | Meaning | Container | PS1 |
|---|---|---|---|---|
| `slot` | array[4] int | Party members as **CharacterId** (255 = empty); the container uses old indices | yes | ids that map to old slots 0-8 |
| `escape_no`, `summon_flag`, `gil`, `frog_no`, `steal_no` | int | Party counters, gil | yes | yes (within PS1 widths) |
| `dragon_no` | int | Dragon kill count (`categoryKillCount[3]`) | yes | yes |
| `humanoid_no`, `beast_no`, `devil_no`, `undead_no`, `stone_no`, `soul_no`, `flight_no` | int | Other category kill counts | no | no (Memoria-only, safe to drop) |
| `kills_per_model` | array `{id, count}` | Kills per enemy model | no | no (Memoria-only) |
| `items` | array `{id, count}` (only owned stacks, any length) | Inventory | yes (ids < 256, 256 slots) | ids < 256, ≤ 256 stacks, count ≤ 255 (u8) |
| `rareItemsEx` | array `{id, obtained:"True"/"False", used:…}` | Key items | yes (ids < 256 as 2-bit pairs in `rareItems[64]`) | ids < 256 |
| `battle_no` | int | Battle count | **no** | no container slot (check whether the PS1 struct has one before relying on it) |

### `30000_MiniGame` (690-738)
| Key | Type | Meaning | Container | PS1 |
|---|---|---|---|---|
| `sWin`, `sLose`, `sDraw` | int | Tetra Master record | yes | yes |
| `MiniGameCard` | array of `{id, side, atk, type, pdef, mdef, cpoint, arrow}` (only owned cards; `side` always 0) | Card collection | yes (ids < 100, first 100) | ids < 100; the PS1 struct has 105 records, so 101-105 cards fit on PS1 but not in the container |

## 7. Moguri

* **What it is.** The catalog lists "Moguri Mod" (`InstallationPath` `MoguriMain`, author Ze_PilOt / Snouz, category **Visual**). It covers backgrounds, textures, FMVs, place names and some UI, and requires Memoria 2024-08-04 or later. "Moguri 30fps videos" (`MoguriVideo`) is also **Visual**. The orchestral soundtrack is a separate mod.
* **Launcher handling.** `Memoria.Launcher/MainWindow.cs` 453-470 (`HotfixForMoguriMod`) only:
  * writes a `[Graphics] TileSize = 64` `Memoria.ini` into `MoguriFiles`;
  * renames a buggy background file.
* **No save involvement.** Moguri ships no code. It does not add or change save data, and it uses no save infrastructure beyond Memoria's own.
* **Gameplay-like features.** The features on Moguri's site that sound like gameplay (turn-based battles, Triple Triad, PSX behaviours) are **Memoria options**, not Moguri.
* **Saves.** A "Moguri" save is simply a Memoria save: container plus sidecar.

## 8. Memoria features that affect persistent state / PS1 representability

**Memoria records no mod list or settings in either file.** A converter cannot know which mods were active. It can only detect non-vanilla *values*.

**Catalog gameplay mods** change persistent meaning: Alternate Fantasy, Trance Seek, Beatrix Mod, Playable Character Pack, Tantalus, Doppelgängers, Perfect Stats, Ferny Fantasy IX, Kupo Heroes, the "Amazing" series, Black Cat. They can do so even when every value is in range:
* custom ability lists change what `pa[i]` means;
* new characters and presets;
* edited field scripts that use `gEventGlobal` bytes in non-vanilla ways or use `gScriptVector`/`gScriptDictionary`;
* custom items and cards.

**Non-representable on PS1** (reject, or at minimum warn and drop):
1. **Item and equipment ids.**
   * Any `equip` id ≥ 256, or any id not in the vanilla item table. The container holds a *wrapped, wrong* id, so it **must not be trusted**.
   * Any `items` id ≥ 256 (dropped from the container).
2. **Abilities.**
   * `pa_extended` ids ≥ 256, or an id list that differs from the vanilla preset's 48-entry list (modded ability tables). AP > 255.
   * `sa_extended` ≥ 64.
   * `menu_type` ≥ 32, or a preset that is not vanilla for that character.
3. **Characters.**
   * `players` entries with `slot_no` ≥ 12 (custom characters).
   * Any party `slot` containing one. The container shows it as an empty slot, which would make the party wrong.
4. **Limits.**
   * HP > 9,999 or MP > 999 with raised `maxHpLimit`/`maxMpLimit`. The container wraps values at u16/i16.
   * `capa` > 255.
5. **Cards and rare items.**
   * Card ids ≥ 100.
   * More than 100 cards: the container is truncated. Up to 105 cards fit on PS1 if taken from the sidecar.
   * Rare item ids ≥ 256.
6. **Scripts.** Non-empty `gScriptVector` / `gScriptDictionary`: a mod's story state lives outside `gEventGlobal`.
7. **Status.** High `status` bits. These are dropped silently, as vanilla does.

**Representable but "not vanilla-legal"** (worth a warning):
* `[Hacks] AllCharactersAvailable = 1/2` (`Memoria.ini` 242/251): party compositions the story would not allow.
* Cheats such as `LvMax`, `GilMax` and `MasterSkill`: in-range values, but cheated.
* Beatrix in the party outside her story windows (Beatrix Mod / Alternate Fantasy).

**Safe to drop** (vanilla PS1 never reads them):
* `gAbilityUsage`;
* the 7 extra kill categories and `kills_per_model`;
* `maxDamageLimit`/`maxMpDamageLimit` at default values;
* `basis_capa`/`basis_max_capa` (derivable);
* `battle_no` (no vanilla container slot);
* the inactive member of each Quina/Cinna, Eiko/Marcus and Amarant/Blank pair. PS1 shares one record per pair, so vanilla also keeps only one.

**`gEventGlobal` size is unchanged (2,048 bytes)** and the container schema is unchanged.

**Open item: `gEventGlobal[1101..1291]`.** Older Memoria builds stored ability-use counts there (the legacy read path at JsonParser 535-540). A save that passed through such a build may hold non-zero counters in those bytes. Check whether the PS1 game uses that range before copying it verbatim.

## 9. When is the sidecar redundant? (reducing a Memoria save to vanilla)

**The sidecar is redundant when all of the following hold:**
* it is valid (time within 1 s), so it describes the same save;
* its `gEventGlobal` equals the container's;
* `gScriptVector`/`gScriptDictionary` are empty;
* none of the conditions in section 8 is present;
* the 9 representable players, party, gil, items, rare items, cards and kill/steal/frog counters agree with the container after applying the vanilla projection (old slot mapping, Byte casts).

When it is redundant, the vanilla container alone is the save, and Memoria → PS1 is the converter's existing PC → PS1 path.

**Recommended Memoria → PS1 algorithm:**
1. Decrypt the container slot.
2. Look for the matching `_Memoria_{slot}_{file}.dat` (or `_Memoria_Autosave.dat`). Parse it leniently (ignore trailing bytes).
3. If it is present and its time is within 1.0 s of the container's, treat it as authoritative for the fields in section 6. Otherwise ignore it, exactly as Memoria does.
4. Reject or warn on the section 8 conditions. In particular, never take `equip` from the container when the sidecar shows an id ≥ 256.
5. Optionally use the sidecar to recover data the container lost: cards 101-105, the correct `pa` by ability id.
6. Build the PS1 save from the reconciled vanilla model.

When the sidecar is absent or stale, the container is the complete vanilla view of that save. It is what Memoria itself would load.

## 10. Missing sidecar

* **Fallback.** If the file is missing, `Load` simply does not attach `MemoriaExtraData` (628). `rootNode["MemoriaExtraData"]` is then a SimpleJSON lazy node that compares equal to null, so `isMemoriaValid = false` (322-323). The game loads purely from the vanilla container, with ability usage seeded from `gEventGlobal[1100+i]`.
* **Vanilla saves load unchanged.** Memoria reads vanilla saves without modification. Vanilla PC also reads Memoria-written containers, since the schema is the same. Any Memoria-only state is lost or projected as described in section 1.
* **Corrupt sidecar (contrast).** An unparseable sidecar throws inside `Load`, and the slot fails to load with `FileCorruption` (641-645). Never write a malformed sidecar. Deleting it is safe.

## 11. Stale sidecars

**Detection is by playtime only.** The sidecar is ignored if its `00001_time` differs from the container's by more than 1.0 s (JsonParser 324-334). Memoria's own comment says this targets a container replaced by a cloud download.

**Covered:**
* the vanilla game or a cloud sync overwrote the slot after more play;
* the converter wrote a slot whose playtime differs.

**Not covered:**
* **Missing time key.** A sidecar without `95000_Setting/00001_time` (e.g. from an older Memoria) is applied unconditionally.
* **Coincidental match.** A different save whose playtime happens to fall within 1 s.
* **Same playtime, different content.** Two saves with the same playtime but different contents, for example the same moment saved twice with different in-menu changes. Menu time still advances playtime, so this is rare.

**Converter implication (PC writer).** When writing slot *n* of a container, check the user's folder for `SavedData_ww_Memoria_{slot}_{file}.dat`.
* If its time is within 1 s of the new slot's playtime, Memoria would overlay it onto the converted data.
* The realistic case is a Memoria → PS1 → PC round trip with no PS1 play in between. It is harmless only if nothing changed.
* The safest choices are to tell the user to delete or rename that sidecar, or to make sure the written playtime differs by more than 1 s. The converter only writes the container, so this is advice, not an action.

## 12. Python implementation notes (summary)

* **Parser.** A recursive reader over the 7 tags in section 5.
  * `<i` for tags and counts, `<d`, `<f`, 1-byte bool.
  * Strings use a 7-bit varint length followed by UTF-8.
  * Keep `(key, node)` order as a list.
  * Return `(root, end_offset)` and ignore the rest of the file.
* **Writer.** The mirror image, with a varint encoder that emits 7 bits per byte (high bit = more).
* **Verification.** A 40-line scratch implementation of both reproduced the sample sidecar byte-for-byte. The writer emitted the parsed tags unchanged.
* **Recognition** (as in ffix-save-editor `LooksLikeSave`): the root is a Class containing `40000_Common.players` as an Array. The first 4 bytes of a real sidecar are `02 00 00 00` followed by `int32` count `04 00 00 00`.

## 13. Confirmed in the game (2026-11-06, Memoria 2025-07-13)

Runtime evidence: `reports/RUNTIME_RESULTS.md`.

**Confirmed:**
- **Naming.** Slot 1 / FILE02 → `SavedData_ww_Memoria_0_1.dat`; autosave → `SavedData_ww_Memoria_Autosave.dat`. Every save rewrites the sidecar. Genuine sidecars round-trip byte for byte through the converter's reader and writer.
- **Load rules.**
  - A timed sidecar overrides the container, even when its content differs.
  - A sidecar more than 1 s off is ignored, and Memoria logs `[JsonParser] Ignoring the Memoria save … because its internal save time … differs from the base save time …`.
  - A corrupt sidecar makes the slot show "Data corrupted." and refuse to load.
  - A sidecar without `00001_time` is applied unchecked.
- **Moguri-style mod folder.** No effect on save data.

**New findings, not visible from a source read alone:**
1. **Memoria's container drops Tantalus members after a vanilla-save load.**
   - Loading any vanilla-format save runs the `94000_Common` bonus loop. That loop calls `GetPlayerFromOldSave(i, false)` for records 5-7, which sets `sub_replaced` on Quina, Eiko and Amarant.
   - From then on, `SelectOldSaveSlot` maps Cinna/Marcus/Blank to -1: the container written by Memoria shows them as absent (party slot 255) and fills their records with unused level-1 Quina/Eiko/Amarant data.
   - Memoria itself restores them from the sidecar, but the vanilla PC game reading that container would not. Seen with Marcus and Blank at story position 4390.
2. **`web_bone` is lost.** It is written as `web_bone` and read as `wep_bone`, so after a load it is 0 until the next battle recomputes it (vanilla saves also hold 0 for characters who have not fought). Harmless.
3. **Ability lists.** `pa_extended` ids per vanilla ability set (`menu_type`) are stable across Memoria builds (2024 sample, 2025-07-13). Cinna, Marcus and Blank have 48 zero ids.
4. **Starting a copied install outside Steam.** `steam_appid.txt` did not stop `SteamAPI_RestartAppIfNecessary` from handing off to Steam; setting `SteamAppId`/`SteamGameId` did. Memoria's launcher deliberately removes `steam_appid.txt` to force that hand-off, and `Memoria.SteamFix.exe` writes a system-wide Image File Execution Options hook, so neither is used for isolated tests.
