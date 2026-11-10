# Changelog

## 0.3.0-dev (local development build, not published)

### Batch conversion
- New `batch` service (`ffix_conv/batch.py`), used by both the app and the new `ffix-convert batch` command:
  every save of a PS1 memory card into one PC slot (FILE n → file n), or any selection of PC saves into PS1 memory
  cards, automatically split across as many cards as needed (`FFIX-PS1-Card-01.mcr`, …), or one `.mcs` per save.
- In-game FILE numbers are kept, never confused with memory-card directory blocks.
- Automatic placement: a new file; or the first empty slot of an existing PC file (shared slot or a clear conflict
  otherwise); or free FILE numbers on an existing memory card. Advanced: a chosen PC slot, card layout (one card per
  PC slot / as few cards as possible), manual SLOT/FILE or CARD/FILE placement, PAL region.
- Occupied places are listed and are only replaced with explicit approval (`--replace`, the app's Replace tick).
- `conversion-manifest.txt` / `.json` list where every save went, with each save's verification and compatibility.
- Memoria/Moguri: each selected save is reconciled with its own sidecar exactly as in a single conversion; a corrupt or
  modded sidecar blocks that save (named), unless lossy conversion is chosen.
- One invalid save stops the whole batch before anything is written; the app offers "Leave it out", the CLI `--select`.

### Transactional safety
- `safeio.Transaction`: every output (save files, report, manifests) is checked, backed up (verified), staged and
  validated, then moved into place under a journal and re-read by SHA-256. Any failure or Cancel undoes every move
  (new files removed, replaced files restored and checked); a crash leaves a journal that `ffix-convert recover`, the
  app's "Undo the interrupted conversion" or Advanced > Recovery undoes. A destination with an unrecovered journal
  is refused.
- Rollback judges each file by its content, so a move that completed just before a failure is undone too.
- Destination changed since it was read: refused. Sources and Steam Cloud locations: never written.

### Desktop app (redesigned)
- Three steps with one button: **Your saves** (large drop area, plain summary, convert all or choose, expandable save
  list), **Where should they go?** (new file / existing file, default folder `Documents\FFIX Save Converter`,
  automatic placement explained in one line), **Convert** (summary, decisions only when needed, one primary button,
  progress and Cancel). A result page with the files, backups, next steps and Open folder.
- Every choice re-plans in the background (one worker thread; superseded checks are skipped); Convert is enabled
  only for a plan that matches the current choices and passed every check; one conversion at a time.
- **Advanced** dialog: placement table, PC slot, card layout, `.mcs` format, region; lossy / damaged-save / write-a-copy
  options; per-save details (verification, compatibility, Memoria data, checksums); log; recovery.
- Plain language in the main window (no "sidecar", "container", "canonical"). Light and dark themes (including an
  explicit palette where a style cannot switch), Windows 11 style, per-monitor DPI, no clipped controls from 520×460 to
  1280×1000 at 100–200 % scale, unique access keys, F1 help, Ctrl+O, Ctrl+Enter, Esc.
- `--automate job.json` and `--smoke result.json` modes drive the real window for packaged-build tests;
  `--settings`, `--out-folder`, `--theme`, `--size` for isolated runs.

### Command line
- New `batch` (with `--select`, `--out`, `--into`, `--in-place --force`, `--replace`, `--slot`, `--map`, `--layout`,
  `--format`, `--region`, `--allow-lossy`, `--lenient`, `--dry-run`, `--json`) and `recover` commands. `convert`,
  `inspect` and `verify` are unchanged.

### Unchanged
- The conversion engine: single-save output is byte-for-byte what v0.2 wrote, and batch output contains exactly the
  same save data (tested).

## 0.2.0-dev (local development build, not published)

### Desktop app
- New **FFIX Save Converter** Windows app (PySide6/Qt): drag and drop or Browse; save list with location, disc, party
  and levels, play time and gil; automatic direction; new file or an existing file as destination; slot, FILE number
  and card-block choice; occupied-slot warnings; a test conversion (nothing written) that shows preserved,
  transformed, defaulted and unsupported fields before Convert; verification result, report viewer, Show in folder;
  About dialog. Keyboard mnemonics on every control, screen-reader names, per-monitor DPI scaling, light/dark theme.
- Work runs on a background thread; while it runs, Convert and all inputs are disabled, so a double click cannot start
  a second write. Replacing a save or updating an existing file needs an explicit confirmation.
- Packaged as a folder with `FFIX Save Converter.exe` and `ffix-convert.exe` sharing one runtime (Qt stays
  replaceable, as the LGPL requires). Project-drawn icon; no Square Enix artwork.

### Memoria / Moguri
- Memoria sidecars (`SavedData_ww_Memoria_{slot}_{file}.dat`) are read (SimpleJSON binary), matched to their slot and
  judged by Memoria's own rules (valid, stale, untimed, corrupt). The sidecar is applied over the container exactly as
  Memoria loads it.
- Memoria → PS1: refuses modded data the PS1 cannot hold, with the exact reasons; `--allow-lossy` (or the app's
  checkbox) drops or clamps what can be dropped safely, and the report lists every change.
- PS1 → PC: refuses to write a slot whose existing sidecar would be laid over the converted save.
- Opening a sidecar by mistake explains which file to open instead.

### Fixed after the Memoria runtime test
- Memoria → PS1: saves made after Memoria loaded a vanilla save (Memoria then marks Quina/Eiko/Amarant as present and its
  container drops Marcus/Blank/Cinna) were refused. The shared PS1 record now goes to the character really in use
  (party, story position, never-played placeholders), and the report says so.
- Memoria → PS1: a sidecar whose AP differed from the container was refused although Memoria loads it. Ability lists are
  now checked against the vanilla ability-id lists of each ability set; ATB values come from the sidecar too.
- PS1 load-screen portraits follow the character model (Marcus showed Eiko's portrait; Garnet's short-hair model has
  her own). Cosmetic: the game redraws it on its next save.

### Engine and safety
- The conversion flow moved into `service.py`, shared by the CLI and the app; vanilla conversion output is unchanged.
- Steam Cloud saves are never written, even with `--force`.
- Readable report text for grouped PS1-only regions.


## 0.1.0-beta (release candidate, not published)

First packaged release: a standalone Windows x64 executable (`ffix-convert.exe`, Windows 10/11, no Python needed).
Released under the MIT License.

### Conversion
- **Both directions:** PS1 memory card ⇄ PC/Steam `SavedData_ww.dat`.
- **Data carried over:**
  - story/event state (`gEventGlobal`, scenario counter) and location;
  - the party and all 9 character records (stats, equipment, AP, support abilities, magic stones, stat growth);
  - items, key items, gil, counters, Tetra Master cards and record.
- **Inputs:** raw cards (`.mcr` `.mcd` `.srm`), DexDrive `.gme`, `.vmp`, `.psv`, `.mcs`, bare blocks.
- **Outputs:** a raw card or `.mcs`, and vanilla PC containers.
- **Destinations:** insert into an existing card or PC file without touching other saves.

### Command line
- New `ffix-convert` commands: `inspect` (with `--json`), `convert` (`--to`, `--source`, `--dest`, `--into`, `--out`), `verify`, `--version`.
  The old option names (`--from/--to`, `--block`, `--pc-slot`, `--slot/--file`, `--ps1-file`, `--dest-block`) still work.
- Readable save listings: location, disc, field/world map, party with levels, playtime, gil.
- **Default output names** sit next to the input and never overwrite anything.
- **Reports:** every conversion writes a report with SHA-256 hashes, independent verification results, and a compatibility section graded *fully preserved / safely transformed / defaulted / lossy / blocking*.
- **`verify`** re-reads both files independently and explains each difference (equal / documented normalization / unexpected).
- **Exit codes:** 0 OK, 1 verify differences, 2 error. Messages are plain, with no stack traces.

### Safety
- Atomic writes through a temporary file, with the output re-parsed and verified before it is moved into place.
- No overwriting without `--force`. With `--force`, the replaced file is backed up and the backup verified.
- In-place updates require `--in-place --force` and are refused if the file changed since it was read.
- Source/destination aliasing is detected: hard links, junctions, symlinks, `..`, case.
- Other card blocks and PC slots are checked to be unchanged before anything is written.
- Values are never silently truncated: oversized strings, unencodable names and out-of-range values stop the conversion.

### Fixes found by audits and in-game testing
- Character preset (`menu_type`) is 5 bits, not 4. Early Cinna, Marcus and Blank would have got the wrong ability sets.
- PC achievement lists use −1 for "empty"; zeros would have recorded fake entries.
- Default PC key bindings now match the game's own defaults.
- PS1 load screen showed Zidane in empty party positions. Fixed, and confirmed in DuckStation.
- Undecodable PS1 names now block conversion (or warn with `--lenient`) instead of passing through.
- PC fixed-size strings that are too long are rejected instead of cut.

### Known limitations
See COMPATIBILITY.md: NTSC-U only verified, PAL untested, Japanese refused, Memoria/Moguri untested.
