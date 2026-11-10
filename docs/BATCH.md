# Batch conversion (v0.3)

Batch conversion converts many saves in one operation: a whole PS1 memory card into a PC save file, or a whole PC
save file (or any selection) into PS1 memory cards. The desktop app always converts this way; a single save is a batch
of one. The command line has `ffix-convert batch` and keeps `ffix-convert convert` for single saves.

Code: `src/ffix_conv/batch.py` (planning and committing), `src/ffix_conv/safeio.py` (`Transaction`). Every save is
converted by the same engine functions as a single conversion (`convert.to_pc_tree`, `ps1_writer.build_block`,
`memoria.reconcile`); the save data written is byte-for-byte what `ffix-convert convert` writes for that save
(`test_batch_saves_are_byte_identical_to_single_conversion`).

## Numbers: FILE numbers, not card blocks

A PS1 memory card has 15 directory blocks. Where a save sits on the card (its block) is **not** its in-game number.
FF9 names each save `BASLUS-0125100000-NN`, where `NN` is the in-game FILE number minus one, and the Load menu shows
FILE01 to FILE15. Batch conversion keeps FILE numbers. A card whose FILE01 sits in block 15 still becomes PC file 1
(`test_file_numbers_not_directory_blocks`).

A PC save file has 10 slots of 15 files. One full card therefore fits one PC slot exactly, and one PC slot fits one
card.

## PS1 card → PC

| Destination | Where the saves go |
|---|---|
| New PC save file | Slot 1, FILE n → file n |
| Existing PC save file | The **first completely empty slot**, FILE n → file n. The saves already in the file are kept byte-for-byte |
| Existing file with no empty slot | The first slot where every needed file is free (a note says the slot is shared). If there is none, the batch stops and asks for a choice: a slot under Advanced (and approval to replace what is there), or a new file |
| Advanced: a chosen slot | That slot, FILE n → file n. Occupied files are listed and need explicit approval (`--replace`, or the app's Replace tick) |
| Advanced: manual placement | Each save at the given SLOT/FILE |

If FILE numbers are missing (a bare save block) or appear twice (NTSC-U and PAL saves on one card), the saves are
numbered 1, 2, 3, … in card order instead, with a note.

Menu time stamps follow play time, so the save played longest is the newest and the game's Continue opens it.

An existing file is updated **in place** after a verified backup (`SavedData_ww.dat.bak-<time>`), so the game sees the
saves at once. Advanced > "write a new copy instead" (or the CLI without `--in-place`) writes a new file next to it
and leaves the original alone. Memoria data files of the saves already in an existing file stay next to that file; a
copy elsewhere does not have them, and the plan says so.

## PC → PS1 cards

| Choice | Result |
|---|---|
| Automatic (default), saves from **one** PC slot | One card; PC file n → FILE n |
| Automatic, saves from **several** slots | As few cards as possible, in slot/file order: FILE01–FILE15 on card 1, then card 2, … |
| Advanced: one card per PC slot | One card per slot used; PC file n → FILE n on that slot's card |
| Advanced: single-save files | One `.mcs` file per save: `FFIX-PS1-Save-01-FILE01.mcs`, … |
| Existing memory card | The saves go on that card. A FILE number already used on the card is replaced by the next free one (with a note). The other saves on the card, including other games, stay byte-for-byte. If the card has too few free blocks or FILE numbers, the batch stops and says how many fit |
| Advanced: manual placement | CARD/FILE for each save (card is always 1 for an existing card); occupied FILE numbers need approval |

New cards are named `FFIX-PS1-Card-01.mcr`, `FFIX-PS1-Card-02.mcr`, … in a new folder. Next to them,
`conversion-manifest.txt` lists where every save went (PC slot/file → card/FILE, with location, disc, play time and
party), and `conversion-manifest.json` holds the same with checksums and every verification result.

Region: NTSC-U by default (PAL under Advanced), as for single conversions.

## Memoria and Moguri

Each selected PC save is read the way Memoria loads it, independently: its own sidecar
(`SavedData_ww_Memoria_{slot}_{file}.dat`) is found and judged (valid, untimed, stale, corrupt) and applied over the
container exactly as in a single conversion. One save's sidecar never affects another save.

- A save whose sidecar holds data the PlayStation cannot represent, or whose sidecar is corrupt, stops the batch until
  it is left out or lossy conversion is chosen (Advanced > Options, or `--allow-lossy`). Lossy changes are listed per
  save in the manifest.
- A stale sidecar is ignored, as Memoria ignores it (noted). An untimed one is applied, as Memoria applies it.
- PS1 → PC into an existing Memoria file: a slot whose sidecar would be loaded over the converted save (play time
  within one second, or an untimed or corrupt sidecar) is refused for that save.

The batch never silently uses the vanilla container alone when a valid sidecar holds the real state.

## What is checked before anything is written

`prepare` (the app runs it in the background whenever a choice changes) does every step in memory:

1. parse every selected save, with its Memoria data;
2. convert each one;
3. work out every destination place;
4. find occupied places;
5. find Memoria files that would be loaded over a converted save;
6. build every output file;
7. re-parse every output file and compare every converted save with its source, field by field
   (`verify.compare`), and check that every other place in an existing destination is byte-identical (PC: every other
   slot block and preview and the autosave; PS1: every other directory frame and block);
8. present the plan: what goes where, what is replaced, notes, and every problem.

Anything wrong with one save (damaged checksum, mod data, Memoria overlay, verification difference, no room) blocks the
whole batch and is named per save. The app offers "Leave them out"; the CLI takes `--select`. Nothing is written for
a blocked batch.

## How it is written: one transaction

`commit` writes all outputs and the report/manifest files as one `safeio.Transaction`:

1. every destination is checked again: new files must not exist, an updated file must still have the SHA-256 it had
   when it was read (otherwise "changed since it was read");
2. a verified backup is made of every file that will be replaced;
3. every file is staged as a temporary file next to its destination, read back and validated;
4. a journal (`.ffix-journal-<time>-<id>.json`) is written in the destination folder, then the files are moved into
   place one by one (atomic rename or no-clobber link), recording each move;
5. every destination is re-read and its SHA-256 compared with what was staged; then the journal is removed.

If anything fails or is cancelled during steps 4–5, every file already moved is undone: new files are removed and
replaced files restored from their backups, each checked by SHA-256, and the error says "every file was put back
exactly as it was". Files are judged by content, so a move that completed just before a failure is undone too.

If the program or computer dies during step 4, the journal stays. The next plan for that folder reports "an earlier
conversion … was interrupted" and the conversion is refused until it is undone: the app's **Undo the interrupted
conversion** button, Advanced > Recovery, or `ffix-convert recover <folder>`. Recovery also judges each file by
content, so it is safe whenever it runs.

Never: an original source file written (also through links and other spellings of the path); a Steam Cloud location
written; an occupied place replaced without approval; a force option applied to unsupported gameplay data (only the
explicit, listed lossy option exists, for Memoria data).

## Cancelling

Cancel works at any time. Before the first move nothing has been written (staged files, backups made for this run and
the journal are removed). During the moves, the transaction stops and undoes what it moved. A cancelled conversion
always reports "Nothing was changed".

## Command line

```bash
ffix-convert batch "Final Fantasy IX.srm" --out "converted\SavedData_ww.dat"
```

```bash
ffix-convert batch "Final Fantasy IX.srm" --into SavedData_ww.dat --in-place --force
```

```bash
ffix-convert batch SavedData_ww.dat --select 2/1 2/2 2/3 --out cards
```

```bash
ffix-convert batch SavedData_ww.dat --dry-run --json
```

```bash
ffix-convert recover "converted"
```

Options: `--select ID …`, `--out`, `--into`, `--in-place --force`, `--replace`, `--slot N`, `--map SAVE=PLACE …`,
`--layout auto|by-slot|compact`, `--format card|mcs`, `--region`, `--allow-lossy`, `--lenient`, `--dry-run`, `--json`.
Exit codes: 0 success, 2 nothing written (the reasons are printed).
