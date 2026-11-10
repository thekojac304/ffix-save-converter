# FFIX Save Converter: user guide (v0.3)

Moves Final Fantasy IX saves between the **PlayStation** version (emulator memory cards) and the **PC (Steam)**
version, one save or a whole collection at a time. Windows 10/11, 64-bit. No installation, no Python.

Unzip the package anywhere, keep the folder together, and start **FFIX Save Converter.exe**.

## Three steps

| Step | What you do |
|---|---|
| **1 Your saves** | Drag a memory card (`.mcr` `.mcd` `.srm` `.gme` `.vmp` `.psv` `.mcs`) or the PC save `SavedData_ww.dat` onto the window, or click **Browse**. The converter recognises the file and says what it found, for example *"15 Final Fantasy IX saves (FILE01–FILE15)"*, from the first save to the last. **Convert all saves** is selected. To pick some, choose **Choose saves** and tick them; **Show the saves** lists every save with its place, disc, party and levels and play time |
| **2 Where should they go?** | The other version is chosen automatically. **New file** (the default) creates a new PC save file, or new memory cards, in the folder shown (`Documents\FFIX Save Converter` unless you change it). **Add to my existing PC save** / **Add to an existing memory card** puts the saves into a file you already have: the saves already in it are kept, and a backup copy of the file is made first. The line underneath says where the saves go, for example *"They go into slot 2, files 1–13. The 15 saves already in the file are kept."* |
| **3 Convert** | A short summary of what will happen. Before the button is enabled, every save has already been converted and read back in memory, so a problem shows up here, not halfway through. Click **Convert 15 saves** |

**Done** shows how many saves were converted and checked, the files written (and backups), and what to do next.
**Open folder** opens the output folder; **View details** shows everything that was checked; **Convert more saves**
goes back.

## When the converter needs a decision

Nothing is written until the decision is made. The message says what to do:

| Message | What to do |
|---|---|
| *N saves already there would be replaced* | Tick **Replace them** to replace them (a backup copy is made first), or choose another place under **Change placement…** |
| *FILE04 looks damaged* | **Leave it out** converts the others. Advanced > Options can allow damaged saves |
| *… holds data from a game mod* | A Memoria/Moguri save with things the PlayStation version does not have. **Leave it out**, or allow lossy conversion under Advanced > Options (everything dropped is listed) |
| *… has a damaged Memoria data file* | Leave it out, or allow lossy conversion (the save is converted without that file) |
| *… would be covered by old Memoria data* | Choose another slot, or move the old `SavedData_ww_Memoria_…dat` file away |
| *The memory card has room for N more saves* | Choose fewer saves, or create new memory cards |
| *An earlier conversion … was interrupted* | Click **Undo the interrupted conversion**: every file is put back as it was before |
| *Good to know* | Information only, for example a FILE number that was already used on the card |

**Cancel** (or Esc) stops at any time. Nothing is changed: anything already written is put back.

## Using the result

- **PC (Steam):** close the game. If you added the saves to your own `SavedData_ww.dat` in
  `%USERPROFILE%\AppData\LocalLow\SquareEnix\FINAL FANTASY IX\Steam\EncryptedSavedData`, they are already there. If you
  created a new file, back up yours and copy the new one there. Turn off Steam Cloud for Final Fantasy IX first, or do
  not choose "Upload" when Steam asks, so Steam does not replace the file.
- **PlayStation emulators:** use the new card as the game's memory card, for example in DuckStation copy it to
  `memcards\Final Fantasy IX_1.mcd`. With more than one card, `conversion-manifest.txt` says which saves are on which
  card.

## Advanced

**Advanced…** (bottom left) holds what a normal conversion does not need:

- **Placement:** choose where each save goes (SLOT/FILE or CARD/FILE); the PC slot; how saves are put on memory
  cards (automatic, one card per PC slot, as few cards as possible); single-save `.mcs` files; PAL region.
- **Options:** lossy Memoria/Moguri conversion; damaged PlayStation saves; write a new copy instead of updating an
  existing file.
- **Details:** for every save, the field-by-field check, what is preserved, transformed, defaulted or not carried over,
  the Memoria data used, and the file formats and checksums.
- **Log:** what the window did (copy it when reporting a problem).
- **Recovery:** undo an interrupted conversion by choosing its folder.

## Keyboard

Every control has an access key (Alt + the underlined letter): Alt+B browse, Alt+A all saves, Alt+H choose saves,
Alt+N new file, Alt+E existing file, Alt+P placement, Alt+C convert, Alt+D Advanced. Ctrl+O opens a file,
Ctrl+Enter converts, Esc cancels. Tab moves through everything; paths can be typed or pasted.

## Safety

- Your original files are only read.
- Every converted save is read back from the new file and compared with its original before anything is written.
- All files of a conversion appear together or not at all. Existing saves are kept unless you tick Replace.
- An existing file is backed up (and the backup checked) before it is changed.
- Steam Cloud save files are never written.

`ffix-convert.exe` in the same folder is the same converter for the command line (`ffix-convert --help`,
`COMMAND-LINE.txt`).
