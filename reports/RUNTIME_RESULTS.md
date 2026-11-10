# In-game runtime results

Date: 2026-11-06. The tests were driven by the agent on the user's unlocked console session (screenshots plus
keyboard/mouse input) against the user's own installs: vanilla Steam FF9 (build 5378074) and DuckStation with the
user's FF9 USA discs. Screenshots of every step are in the session scratchpad. Game-written files are in
`runtime_test_package/results/`.

## Summary

| Direction | Load | Location/party/stats | Story continues | Map transition | Battle | Native save | Restart + reload |
|---|---|---|---|---|---|---|---|
| PS1→PC, your own run (slot 2 FILE01, Bentini Heights) | ✅ | ✅ exact | ✅ Treno first-arrival scene | ✅ world map → Treno | ✅ won | ✅ slot 3 FILE01 | ✅ |
| PS1→PC, Gulug (slot 1 FILE02) | ✅ | ✅ exact | – (walked toward Gulug) | ✅ 3 screens | ✅ won | – | – |
| PS1→PC, Disc 3 transition (FILE03) | ✅ | ✅ | ✅ correct Disc 3 opening (Tot, the crowning) | – | – | – | – |
| PS1→PC, Disc 4 transition (FILE04) | ✅ | ✅ | ✅ correct Disc 4 opening (Black Mage Village) | – | – | – | – |
| PS1→PC, Memoria entrance (FILE05) | ✅ | ✅ | – | – | ✅ ran (party losing; not finished) | – | – |
| PS1→PC, Alexandria Castle (FILE07) | ✅ | ✅ | – | – | – | – | – |
| PC→PS1, Gulug (FILE02) | ✅ (asked for disc 3, correctly) | ✅ exact | – | ✅ | – | – | – |
| PC→PS1, Disc 4 world map (FILE05) | ✅ (asked for disc 4) | ✅ | – | ✅ | ✅ won | ✅ FILE06 | ✅ after emulator reset |
| PC→PS1, your own 2021 PC run (FILE01) | ✅ | ✅ exact | – | – | – | – | – |

Exact means every displayed value matched `expected_values.json`: level, HP/MP current and max, magic stones
used/total, gil and location.

## Field-level evidence after the game re-saved

**PC** (`tools/analyze_runtime_result.py`, converted slot 2/1 vs game-written slot 3/1, 175 s of play):
- The only changes are what was played: +322 gil, Eye Drops, +37 EXP and AP for the fighters, and 6 event-variable bytes.
- Expected PC runtime normalizations:
  - Marcus/Blank `bonus_cap` 0 → 30/20. This is the documented vanilla "0 means derive" rule, and it is what native PC saves contain.
  - Steiner `serial_no` 8 → 7. Vanilla `FF9Play_GetSerialID` always returns 7 for Steiner and recomputes it after battles. PS1 saves can carry 8. This is a model-variant id; the battle rendered Steiner correctly before the normalization.
- Support abilities, magic stones, equipment, key items, story flags and location were **not** changed, so the vanilla load validators accepted the converted data.

**PS1** (`tools/compare_ps1_rewrite.py`, converted FILE05 vs game-written FILE06):
- The game replaced the project-drawn icon and title with its own and incremented the save counter (0x178).
- Other changes: `prevMode` 1 → 3 after a world-map battle, levels/EXP/HP from the battle, gil, one item count, and 7 event bytes.
- The zero-filled PS1-only regions **0x09C0–0x09CF, 0x1160–0x1177 and 0x13F4–0x13FD were kept as zero**. In 0x0EF2–0x0F1F the game itself wrote 4 bytes (0xF0D, 0xF18, 0xF19, 0xF1C), consistent with battle bookkeeping. No region was rejected or "repaired".

## Problems found and fixed

1. **PS1 load-screen preview showed Zidane for empty party positions** (PC→PS1). Cause: empty preview records were written
   as zeros (portrait 0 = Zidane); the game writes `00 FF×11 00`, as all 78 empty records in the corpus do. Fixed in
   `ps1_writer._write_preview`, with regression test `test_empty_preview_records_match_the_game_regression`. Re-verified in
   DuckStation: FILE01 now shows only Zidane, and FILE03 only Dagger and Steiner. Cosmetic only: the game rebuilds the preview when it saves.
2. **Install landed in the wrong place when run by the agent.** The Claude desktop app is MSIX-packaged, so its child
   processes' writes under `%LOCALAPPDATA%`/`LocalLow` are redirected to `...\Packages\Claude_...\LocalCache`, and the
   game saw an empty container ("No FF9 save data"). The fix was environmental: the install/restore scripts were run
   outside the package (WMI process creation, normal user rights). The scripts work as-is when you run them yourself.

## Not tested / remaining

- **Neither direction:** save → restart → reload on checkpoints other than your Bentini run (PC) and Gegalrich Shores (PS1).
- **PS1→PC:** story triggers beyond the first scene after loading; Memoria/Moguri.
- **PC→PS1:** the converted Disc 2/3 starts in the emulator (only listed, not loaded); the PC timer fields in timed sequences.
- A Steam UAC prompt (Steam re-running FF9's redistributable install script) appeared on two launches; it was left
  untouched and Steam continued without it.

## Environment cleanup (verified by hash)

- **PC save folder:** holds the game's own original (empty) container again (`1657B6D4…`).
- **DuckStation:** memcards and savestates folders match their original listings. No FF9 resume state was created (powered off without saving).
- **Untouched:** your RetroArch FF9 card (`8E30CF54…`), your Steam Cloud save (`00AA9674…`) and the game files.
- **DuckStation settings:** no settings were changed. DuckStation rewrote its own `settings.ini` on exit; the memory-card, pad and save-state sections read back identical.

---

# Release-candidate runtime round (v0.1.0-beta)

Same environment. The PC → PS1 test card was built with the new `ffix-convert` CLI (each conversion self-verified,
0 unexpected fields), saved as `runtime_test_package/results/rc/rc_ps1_test_card.mcr` (sha256 `b6e3ba67…`), and used
as an isolated copy (`memcards/Final Fantasy IX_1.mcd`, removed afterwards).

| FILE | Source (sha256) | Path | Observed in DuckStation 0.1-7878 |
|---|---|---|---|
| 01 | your RetroArch card block 11, "Start of DISC 2" (`8e30cf54…`) | PS1 → PC → PS1 | "Change to DISC 2" prompt; after the swap, the correct Disc 2 opening (South Gate guards) ✅ |
| 02 | FantasyAnime 32, "Start of DISC 3" (`7eeadc8e…`) | PS1 → PC → PS1 | Correct Disc 3 opening (Alexandria boat: Tot, Dagger, Beatrix) ✅ |
| 03 | your 2021 Steam save, slot 1/2, A. Castle/Guardhouse (`00aa9674…`) | PC → PS1 | Steiner Lv1, 120/120 HP, 24/24 MP, 17/17 stones, 10678 gil, as on PC; walked out of the guardhouse into the castle hall ✅ |
| 04 | Steam forum "cd3" save, slot 2/4, Dali/Inn (`9de3fdbe…`) | PC → PS1 | Eiko-led Lv 99 party; HP/MP/stones and gil (4,440,291) identical to the PC source; Mognet option present; **native save to FILE06, emulator reset, reload** ✅ |
| 05 | Steam "cd3" save, slot 2/2, Disc 3 Alexandria | PC → PS1 | listed with correct disc and portraits (not loaded) |

What the game changed when it re-saved FILE04 → FILE06 (`tools/compare_ps1_rewrite.py`):
- The icon and title (regenerated), the preview leader (the game shows Zidane) and the save counter.
- 2 event bytes, and **0x09C0 0 → 52 after walking**, which is evidence that 0x09C0 is the PS1 step counter.
- Everything else is unchanged: all characters, party, gil, items and key items.

## Stopped: PC runtime automation in this round

On the PC title screen my input automation twice ended up on **CLOUD DATA** instead of LOAD GAME. The menu shifts
when CONTINUE is unavailable, and the image-based guard I added misread the cursor. Upload or Download was never
selected:
- `FF9_CloudSaveFile_ww.sav` is unchanged (`00AA9674…`, 2021 timestamp);
- Steam's `remotecache.vdf` is unchanged (same SHA, ChangeNumber 0), checked before and after the game exited.

Because a single wrong key there could overwrite your cloud save, **I stopped automated PC testing**. The new PS1 → PC
checkpoints (PC Disc 2 transition, later Disc 3/4 positions, another late-game save, a second PC save/restart cycle)
are **not run**. The PC test save was removed and the game's own file restored (`1657B6D4…`).

---

# PC round 2: PS1 → PC, with Steam Cloud disabled for FF9 and screenshot-guarded input

**Setup.**
- With your approval, FF9's per-game "Keep game's saves in the Steam Cloud" toggle was turned **off** in Steam → Properties. It was ON before. The global Steam setting was untouched.
- Input went through `tools/runtime/ff9_step.py`, which takes a fresh screenshot and classifies the screen before every confirm. On the title menu it requires two independent pointer detectors to agree on LOAD GAME, and it aborts with Cancel only if the Cloud screen ever appears.
- The guard logged **210 steps**, with **0 cloud-screen detections**. It aborted once, correctly, refusing to confirm while the title intro was still playing.

**Test file.**
- `runtime_test_package/results/pc_round2/round2_SavedData_ww.dat` (sha256 `5e838c24…`), built with `ffix-convert`.
- Sources:
  - your RetroArch card block 11 (`8e30cf54…`);
  - FantasyAnime 33 (`32a6fbcd…`), 50 (`1ce5fdc1…`) and 54 (`d4548676…`).

| PC slot | Source | Result in Steam FF9 (build 5378074) |
|---|---|---|
| 1/1 | **Your "Start of DISC 2"** | Correct Disc 2 opening (South Gate guards), which continues into the next scene (Garnet and Steiner in the cable car) ✅ |
| 1/2 | Treno, Disc 3 (scenario 7550) | Zidane at Treno on the world map. Entered Treno (world → town) and walked back out (town → world). Battle won. **Native save to slot 4 FILE01, full quit and restart, reload**. After reload: Zidane Lv28, HP 1541/1570 (battle damage kept), 3/33 stones, 49,491 gil (+248) ✅ |
| 1/3 | Disc 4 world map (11100) | Loads aboard the Invincible above the Pualei Plains, Disc 4 world map ✅ |
| 1/4 | Crystal World (11770, late game) | Exact stats for all four characters, including Zidane's fully used 0/51 stones (so support abilities survived the PC's load validation). Walking forward triggers the correct final-dungeon event (Trance Kuja above the Crystal) ✅ |

**Field analysis of the game-written save** (`tools/analyze_runtime_result.py`):
- Only played changes: gil, an item, EXP, 6 event bytes.
- Plus one documented PC normalization: guest Beatrix `bonus_cap` 0 → 80, so her max stones go 16 → 18 and the ATB maximum is recomputed.

**Protection checks** (`tools/runtime/cloud_guard.py`, baseline taken before any change), run before, during and after:
- the local cloud file (`00aa9674…`, SHA-1 `5dcfb59e…` = Steam's record);
- Steam's remote cache for 377840;
- both RetroArch cards.

All three were **unchanged** at every check.

**Restore.**
- The PC save folder was restored to the game's own file (`1657b6d4…`).
- The FF9 cloud toggle was turned back **on**, after confirming the local cloud file was still identical to Steam's cloud record.
- Steam's cloud log immediately afterwards: "File is in sync … FF9_CloudSaveFile_ww.sav". No upload happened.

# Memoria / Moguri runtime round (v0.2.0-dev, 2026-11-06)

**Setup** (approved by you):
- Memoria **v2025.07.04** (`Memoria.Patcher.exe`, SHA-256 `23b9fb8c…` = GitHub's published digest, valid code signature; in-game version string 2025-07-13). Its save code is identical to the source the research used.
- Installed into an **isolated 9.06 GB copy** at `E:\FF9-Memoria-Test`. The patcher was given the copy's path explicitly. Your Steam install was fingerprinted before and after: all 292 files have identical path, size and timestamp.
- **Starting the copy.** The game asks Steam to relaunch it unless it looks Steam-launched, and `steam_appid.txt` did not prevent that. The first attempt raised a Steam "Launch Game with custom arguments" prompt; you cancelled it, and nothing ran. The copy was then started directly with `SteamAppId`/`SteamGameId` set: no prompt, and Steam tracked it as app 377840. Memoria's launcher, which deliberately triggers the relaunch, and `Memoria.SteamFix.exe`, which writes a system-wide registry hook, were never run.
- **Steam Cloud and saves:**
  - FF9's per-game Steam Cloud setting was turned **off** in Steam → Properties (it was ON) and turned back **on** after testing.
  - `cloud_guard.py` checks passed before, during and after. Steam afterwards: "File is in sync … FF9_CloudSaveFile_ww.sav".
  - Saves were installed into the real save folder through WMI and hash-verified. The folder was restored to its original single file (`1657b6d4…`).
- **Input** went through the screenshot guard (`ff9_step.py`); no Cloud Data screen was ever entered.

## 1. PS1 → Memoria ✅

Source: your RetroArch card, block 13, Bentini Heights (Disc 2, story 4390), converted to PC (37 equal, 2 normalized, 0 unexpected).

| Check | Result |
|---|---|
| Load | Memoria's title shows **"World Map: 9002, Bentini Heights"** (= `wldMapNo` 9002) |
| Stats | Dagger Lv7 222/222 12/60 stones 5/16, Steiner Lv8 177/406 35/35 2/21, Marcus Lv7 178/277 31/31 10/10, 40,169 gil: **identical** to the converted save |
| Story | Entered Treno: map 908 (Treno/Gate); Memoria's title shows **counter 4390**; the Steiner/Marcus arrival scene and an Active Time Event played; Memoria autosaved |
| Battle | Trick Sparrow + Carve Spider on the world map, won (+322 gil) |
| Native save | Moogle (Moguo) → slot 1 FILE02. Memoria wrote the container and **`SavedData_ww_Memoria_0_1.dat`** (0-based naming as researched) |
| Restart and reload | Game quit, relaunched, FILE02 loaded: Marcus 146/277, 40,491 gil, all as saved |

## 2. Memoria → PS1 ✅ (after a fix)

The genuine container + sidecar of FILE02 was converted and loaded in DuckStation 0.1-7878 with your discs:
- The game asked "**Change to DISC 2**".
- Dagger 222/222 12/60 5/16, Steiner 177/406, **Marcus Lv7 146/277**, 40,491 gil, Bentini Heights: identical to Memoria.
- PS1 battle won; native save to FILE02/DISC 2 (12:13:03, 40,689 gil); reset and reload showed the saved state (Steiner 157/406).
- The converted FILE01 block was left untouched by the PS1 game.

**Defect found by this test (fixed):**
- Memoria sets `sub_replaced` on Quina, Eiko and Amarant whenever it loads a vanilla-format save. This happens in JsonParser's 94000_Common loop, which calls `GetPlayerFromOldSave(i, false)` for every record.
- Its next container write therefore dropped Marcus from the party (`[2,3,255,255]`) and replaced records 6 and 7 with unused level-1 Eiko and Amarant.
- The sidecar still holds Marcus and Blank, and Memoria itself restores them from it.
- The converter trusted the flag and refused the save. It now decides the shared record by, in order: party membership, story position (switch points measured in 118 vanilla saves: Marcus to 6270, Eiko from 6310; Blank to 6795, Amarant from 6890; Cinna/Quina at 3700), never-played placeholders, then the flag.
- Without the sidecar, this container alone converts to a party without Marcus. That is why the sidecar must never be ignored.

**Vanilla state across PS1 → Memoria → PS1:** compared with the original block 13, the only differences are:
- the Memoria session's play: +322 gil; items 241 and 244 +1 each; +37 EXP for each party member; AP gains; Marcus's HP; last battle map; play time; story bytes 64-72 (world-map/battle bookkeeping);
- documented normalizations: `web_bone` 0 (recomputed every battle; Memoria writes it as `web_bone` but reads `wep_bone`), Steiner's serial 8 → 7, guest stone-growth caps.

Key items, cards, levels, equipment, support abilities and story counter are identical.

## 3. Sidecar rules against real Memoria ✅

One test container, five files:

| File | Sidecar | Memoria in-game | Converter |
|---|---|---|---|
| FILE01 | genuine content, re-timed to within 0.3 s, gil 1,234,567, Dagger HP 111 | **applied**: 1,234,567 gil, Dagger 111/222, Marcus 146 | same |
| FILE02 | genuine pair | applied | same |
| FILE03 | stale (149 s), gil 999,999 | **ignored**; log: "Ignoring the Memoria save SavedData_ww_Memoria_0_2.dat because its internal save time (12:08:25.366) differs from the base save time (12:05:56.517)"; 40,169 gil, Marcus 178 | stale, same values |
| FILE04 | corrupt (16 bytes) | **"Data corrupted."**, slot does not load (`SharedDataBytesStorage.Load` exception) | refused (lossy: container only) |
| FILE05 | no time key, gil 7,777 | **applied without check**: 7,777 gil | same |

A second strict check was too strict and was replaced. The converter had refused FILE01/FILE05 because their AP differed from the container's. Memoria loads the sidecar's AP by ability id, so the converter now accepts a sidecar whose ability-id list equals the vanilla list of that ability set. The lists for 13 ability sets were taken from genuine sidecars and are identical in the 2024 public sample. Unknown sets still need the container to agree; ids ≥ 256 are still refused.

## 4. Moguri-style setup ✅

Memoria with a `MoguriFiles` mod folder active (`FolderNames = "MoguriFiles"`, `[Graphics] TileSize = 64`, exactly what Memoria's launcher writes for Moguri), without the multi-GB textures. The log showed `Mods: 'MoguriFiles'`.

FILE02 loaded identically and a native save to FILE06 produced `SavedData_ww_Memoria_0_5.dat`:
- the same size (51,617 bytes) and **the same structure** as the plain-Memoria sidecar;
- the same converted state apart from one bookkeeping byte and `web_bone`.

## 5. Cosmetic defect found and fixed

The PS1 load-screen portrait for Marcus was Eiko's (the writer chose portraits by record number). The PS1 game draws portrait 9 for Marcus. Portraits now follow the character model; Garnet's short-hair model also gets her own portrait (3).

## Left behind / not reverted
- `E:\FF9-Memoria-Test`: the isolated Memoria install plus working files. Delete the folder when you no longer need it.
- Steam recorded about 22 minutes of FF9 play time for the copy's sessions; Memoria's Steam API was active, so achievement progress could also have been reported.
- DuckStation's `playtime.dat` play-time counter for FF9 grew. DuckStation settings, its other cards and its screenshots folder are unchanged (one accidental emulator screenshot was deleted).
