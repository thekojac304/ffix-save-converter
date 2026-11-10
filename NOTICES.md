# Notices and license audit

## This project's own license

**MIT License**, Copyright (c) 2026 thekojac. Full text: [`LICENSE`](LICENSE) (`LICENSE.txt` in the Windows archive).

The MIT License covers this project's own code and documentation. It does not cover the third-party components below,
which keep their own licenses, or Final Fantasy IX's own data.

## Code and knowledge from other projects (source)

* **Memoria**: https://github.com/Albeoris/Memoria, MIT License, Copyright (c) 2017 Albeoris.
  The PC save schema (field names, types, ordering rules, container constants) in `src/ffix_conv/pc_schema.py`
  and `pc_container.py`, and the settings defaults in `convert.py`, are transcribed from Memoria's
  `JsonParser.cs`, `SharedDataBytesStorage.cs` and `FF9CFG.cs`. License text: `THIRD_PARTY_LICENSES/Memoria-MIT.txt`.
* **ffix-save-editor**: https://github.com/nintendogamer15/ffix-save-editor, MIT License, Copyright (c) 2026
  ffix-save-editor contributors. The PS1 Latin text table in `src/ffix_conv/ps1_save.py` follows its
  `LegacyTextCodec.cs`. License text: `THIRD_PARTY_LICENSES/ffix-save-editor-MIT.txt`. That project credits the table
  to the gjoerulv editor below. It is a byte-to-character mapping of the game's own font encoding, re-checked here
  against real saves.
* **Memoria save loading (v0.2)**: the sidecar format and Memoria's load rules in `src/ffix_conv/memoria.py` were
  written from a reading of Memoria's MIT-licensed source (`JsonParser.cs`, `SharedDataBytesStorage.cs`, SimpleJSON);
  no code is copied. Details: `docs/MEMORIA_RESEARCH.md`. The one sample sidecar used in tests comes from
  ffix-save-editor's `examples/` (MIT) and stays in git-ignored `fixtures/`.
* **ff9SaveLib**: https://github.com/EuanFH/ff9SaveLib, GPL-3.0. **No code is used.** Its test fixture is used
  locally only and is not distributed.
* **Memoria FF9 Save Editor (gjoerulv)**: https://github.com/gjoerulv/Memoria_FF9SaveEditor. No license file; the
  help file states public domain. No code is used; its offset notes are cited as documentation.
* **Vanilla FINAL FANTASY IX (Steam build 5378074)**: the installed `Assembly-CSharp.dll` was decompiled locally,
  for interoperability only, to read the save/load code. **No decompiled code is included.** Small facts needed for
  compatibility (default option values, key-binding defaults, disc ranges, preview portrait ids) appear in the source.
  The ability tables used by the audit stay in git-ignored `research/vanilla_extracts/`. No item, ability or card name
  tables are included.

All reused code and data are under MIT or a public-domain statement, or are interoperability facts. None of it is
under the GPL, and all of it can be distributed under this project's MIT License.

## Components bundled in the Windows executable

`ffix-convert.exe` is built with PyInstaller and contains the following. Their license texts are in `THIRD_PARTY_LICENSES/`.

| Component | Version | License | Notes |
|---|---|---|---|
| Python runtime (`python314.dll`, standard library, `_hashlib`, `_bz2`, `_lzma`, `_zstd`, `_decimal`, `unicodedata`, `select`) | 3.14.5 | PSF License 2.0 | `Python-LICENSE.txt` also lists the bundled libraries' licenses (bzip2, xz, zstd, mpdecimal, …) |
| OpenSSL `libcrypto-3.dll` (used by `hashlib`) | as shipped with Python 3.14.5 | Apache-2.0 | covered in `Python-LICENSE.txt` |
| cryptography (AES for PC saves), including its Rust extension | 50.0.2 | Apache-2.0 OR BSD-3-Clause | `cryptography-LICENSE*.txt` |
| cffi backend | 2.1.1 | MIT-0 | `cffi-LICENSE.txt` |
| Microsoft Visual C++ runtime `VCRUNTIME140.dll` | as shipped with Python | Microsoft redistributable | redistribution permitted with applications |
| Qt for Python (PySide6, shiboken6) and Qt 6 (Core, Gui, Widgets; desktop app only) | 6.12.0 | LGPL-3.0 | dynamically linked, unmodified, shipped as separate replaceable DLLs in the folder build; `LGPL-3.0.txt`, `GPL-3.0.txt` and `Qt-PySide6-NOTICE.txt` (with source links) |
| PyInstaller bootloader | 6.22.3 | GPL-2.0 with bootloader exception | the exception permits distributing executables built with it under any license (`PyInstaller-COPYING.txt`) |

The Windows Universal C Runtime is **not** bundled; it is part of Windows 10/11.

## What is not distributed

Neither the archive nor the source repository contains:
- game files, PS1 BIOS or disc images, or game artwork or screenshots;
- save files of any kind (community, fixture or personal);
- Steam data.

The 2-bit save icon in `ps1_writer.py` was drawn for this project. The screen-recognition test tool (`tools/runtime/`)
needs reference screenshots, which you capture from your own game; they are never committed. The community save fixtures used in testing (FantasyAnime, Steam forum uploads) have no
redistribution license and stay in git-ignored `fixtures/`.

Final Fantasy IX is © Square Enix. This project is not affiliated with or endorsed by Square Enix.
