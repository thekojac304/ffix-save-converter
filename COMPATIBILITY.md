# Compatibility (v0.3.0-dev)

The conversion engine is unchanged from v0.2 (and from v0.1.0-beta for vanilla saves): every earlier test still
passes, and a Memoria-aware path only takes effect when a Memoria sidecar sits next to a PC save.

## Batch conversion (new in v0.3)

Batch conversion calls the same per-save engine as a single conversion; the save data it writes is byte-for-byte
what a single conversion of the same save writes (tested for PS1 → PC and PC → PS1), so the in-game results below
apply to every save of a batch.

| What | Status |
|---|---|
| A full 15-save PS1 card → one PC slot, FILE01–FILE15 → files 1–15 | Tested on your own RetroArch cards (15 and 13 saves): every save re-verified field by field with `ffix-convert verify` |
| A second card into the same PC file | Goes to the next empty slot; the first card's slot stays byte-identical |
| PC → several PS1 cards (28 saves → 15 + 13) | Tested; every card re-read, every save verified |
| Existing memory cards | Other blocks (other games included) byte-identical; clashing FILE numbers renumbered with a note; capacity enforced |
| Memoria sidecars across many saves | Tested on the genuine valid / stale / corrupt / untimed sidecar set and the Moguri-style file; each save judged on its own |
| A batch loaded in the game | **Not run in v0.3.** A batch-written PC file or card was not loaded in Steam/DuckStation for this milestone; the byte-identity test above is the evidence. See TESTING.md |

Limits: one source file per conversion (convert a second card in a second run; it goes to the next empty slot);
15 FF9 saves per memory card; 10 slots of 15 files per PC file.

## Verified

| Component | Version | How it was verified |
|---|---|---|
| FINAL FANTASY IX, Steam (vanilla, no Memoria) | Steam build **5378074** (`Assembly-CSharp.dll` sha256 `2fd5a4b7…`) | Played in the game: loading converted saves, story scenes, field/world transitions, battles, a native save, quit/restart and reload |
| FINAL FANTASY IX, PlayStation | **NTSC-U (SLUS-01251/01295/01296/01297), v1.0** | 82 real PS1 saves parsed and round-tripped. Converted saves played in DuckStation with your own discs |
| DuckStation | **0.1-7878** (Qt, portable) | Loading converted cards, disc-swap prompts, battles, native memory-card save, reset and reload |
| PS1 card files | ePSXe `.mcr` and RetroArch/Beetle `.srm` (real files); DuckStation `.mcd` (output tested) | A blank card plus a block reproduces an ePSXe card byte-for-byte; your RetroArch cards rewrite byte-identically |
| PC container | `SavedData_ww.dat`, 2,937,152 bytes | All 4 public containers and your own re-serialize byte-identically |

## Not verified

| Item | Status |
|---|---|
| PAL PS1 saves (any language) | Accepted with a warning. The layout is assumed identical to NTSC-U; no PAL save was available to test |
| Japanese PS1 saves | **Refused.** The text encoding differs |
| Memoria / Moguri in the game | Played under **Memoria 2025-07-13** (stable v2025.07.04) on Steam build 5378074 at one Disc 2 checkpoint, both directions (see the next section); Moguri textures not installed |
| Steam versions other than 5378074; mobile/console releases | Untested. The PC container check rejects files whose data size differs |
| RetroArch/Beetle as the *runtime* emulator | Card files from it are verified; gameplay was tested in DuckStation only |
| `.gme` `.vmp` `.psv` `.mcs` inputs | Parsers are tested with synthetic files only. PSV/VMP signatures are not regenerated (input only) |

## Memoria and Moguri (new in v0.2)

Memoria keeps writing the vanilla `SavedData_ww.dat` and adds a sidecar file per save,
`SavedData_ww_Memoria_{slot}_{file}.dat`, which overrides the container on load when its play time matches within one
second. Moguri is a visual mod running on Memoria and adds no save data, so a Moguri save is a Memoria save. Research
and sources: [docs/MEMORIA_RESEARCH.md](docs/MEMORIA_RESEARCH.md).

| Direction | Status | What happens |
|---|---|---|
| PS1 → Memoria / Moguri | **Verified in the game** (Memoria 2025-07-13): load, exact stats, story scene, battle, native save, restart and reload | The normal PS1 → PC conversion. Memoria reads vanilla containers unchanged and loads the container alone when there is no sidecar. The converter **refuses** to write a slot whose existing sidecar would be laid over the converted save (play time within 1 s), and warns about an older, ignored one |
| Vanilla PC → Memoria / Moguri | No conversion needed | Memoria loads vanilla saves as they are |
| Memoria / Moguri → PS1, unmodded gameplay or Moguri | **Verified in the game**: a genuine Memoria native save (container + sidecar) loaded in DuckStation with exact stats, then battle, native PS1 save, reset and reload | The sidecar is found automatically, judged as Memoria judges it (valid, stale, untimed, corrupt) and applied over the container. A faithful sidecar changes nothing: the result is byte-identical to converting the container alone (tested on every vanilla PC save) |
| Memoria → PS1, gameplay mods within vanilla ranges | **Experimental** (no real gameplay mod tested) | Values the sidecar holds are taken from it (it wins in Memoria too) and listed in the report |
| Memoria → PS1, modded data the PS1 cannot hold | **Refused by default**, with the exact reasons | See the table below. A clearly labelled lossy option drops or clamps the listed values; the report lists every change |
| Sidecar rules | **Verified against Memoria**: a timed sidecar overrides the container (also when its content differs), a stale one is ignored (Memoria logs it), a corrupt one makes the slot unloadable ("Data corrupted."), one without a time stamp is applied unchecked; the converter matched Memoria in all four cases | `reports/RUNTIME_RESULTS.md` |
| Moguri-style setup (`MoguriFiles` mod folder, `TileSize = 64`, no textures) | **Verified**: identical save structure and converted state | |

Memoria → PS1 decisions:

| Found in the Memoria save | Default | With lossy conversion |
|---|---|---|
| Equipped mod item (id ≥ 256; the container shows a wrong wrapped id) | refused | unequipped |
| Mod items, key items or Tetra Master cards | refused | dropped |
| More than 105 cards or 256 item stacks | refused | truncated |
| HP above 9,999, MP above 999, magic stones above 99, AP above 255 (raised limits) | refused | clamped |
| Mod support abilities (id ≥ 64) | refused | dropped |
| Story state in Memoria's script storage (`gScriptVector`/`gScriptDictionary`) | refused | dropped (that mod's progress is lost) |
| Corrupt sidecar (Memoria cannot load the slot either) | refused | sidecar ignored, container converted |
| Mod character in the party, modded ability lists, a story-state block that is not 2,048 bytes | **always refused** | **always refused** |
| Memoria-only statistics (kill counts, battle count, ability-use counters), the unused member of the Quina/Cinna, Eiko/Marcus and Amarant/Blank pairs | dropped, listed in the report | same |
| Ability-use counters an older Memoria build left in story bytes 1101-1291 | cleared (they are zero in all 118 vanilla saves tested) | same |
| Stale sidecar (play time differs by more than 1 s) | ignored, exactly as Memoria does, and reported | same |

**A Memoria quirk the converter corrects.** Whenever Memoria loads a vanilla-format save, it marks Quina, Eiko and Amarant
as present. From then on, Memoria's own `SavedData_ww.dat` drops Cinna, Marcus or Blank from the party while they are
still in use (seen in the runtime test: Marcus vanished from the container's party, Memoria itself kept him through the
sidecar). The vanilla PC game reading that container would lose him. The converter takes the shared PS1 record from the
character who is really in use and says so in the report.

A Memoria save records no list of active mods, so a mod is only detectable through values like these. A gameplay mod
that changes what in-range values mean, such as a rebalanced item table, cannot be detected; the report then says
the result is experimental.

## Known normalizations (expected differences)

| What | Why |
|---|---|
| Empty party position: 9 on PS1, 255 on PC | Different "no one" markers |
| World-map position before you first reach the world map: 9009/68 on PS1, 0/0 on PC | The game overwrites it when the world map opens |
| Tetra Master cards: PS1 can have gaps between cards, PC packs them | Same cards, same order |
| Playtime: PS1 counts frames (60/s NTSC, 50/s PAL), PC counts seconds | Converted exactly to whole frames |
| Guest characters' stone-capacity growth value (`bonus.cap`) 0 → (level−1)×5 on PC | The PC game treats 0 as "derive it". Native PC saves do the same |
| Steiner's model variant (`serial_no`) 8 → 7 after PC battles | The PC game recomputes it; on PC Steiner is always 7 |
| PS1 load-screen "leader" | The PS1 game picks the leader when it saves; converted saves show the first party member until then (cosmetic) |
| PS1 memory-card icon and title | Converted cards use a simple project-drawn icon. The game replaces it with its own on the next save |

## Potentially lossy fields

- **PC → PS1:**
  - Steam achievement progress, PC options and key bindings, the world-map camera angle.
  - The countdown-timer state (only relevant mid-timed-event).
  - Tetra Master card "side/points" (constant on PC).
- **PS1 → PC:**
  - PS1 options (ATB mode, message speed, …); the PC uses its defaults or `--template`.
  - PS1-only bytes, all listed in the report: the step counter at 0x9C0, battle bookkeeping at 0xEF2–0xF1F, 0x1160–0x1177, 0x13F4–0x13FD.
- **Around a PC → PS1 → PC or PS1 → PC → PS1 cycle:** everything above. All shared gameplay data is preserved (tested on 82 PS1 and 36 PC saves).

## Disc numbers for PC → PS1

The PC version has no discs, so the disc is derived from story progress:
- scenario ≤ 3880: disc 1
- 3900–6960: disc 2
- 6990–10980: disc 3
- ≥ 10995: disc 4

Saves inside the narrow gaps between those ranges are refused unless you pass `--disc N`.
