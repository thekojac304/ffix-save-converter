# v0.1.0-beta release readiness

Date: 2026-11-06 (final package, MIT license)

## Decision: **READY FOR PUBLIC GITHUB PUBLICATION** as a beta pre-release, with one disclosed gap

- **Source repository: ready.**
  - MIT `LICENSE` added and all third-party notices kept.
  - Every reused component is MIT-compatible.
  - The publishable file set (68 files) is free of saves, game assets and personal identifiers.
- **Windows binary: ready as a pre-release.** The clean-machine test was not run because Windows Sandbox isn't installed on this PC.

Both directions have in-game evidence that covers:
- disc transitions;
- a mid-game and a late-game checkpoint;
- field and world transitions, battles;
- native save, restart and reload.

| # | Former blocker | Status |
|---|---|---|
| 1 | Project license | **Done:** MIT, Copyright (c) 2026 thekojac (`LICENSE`; `LICENSE.txt` in the zip) |
| 2 | Clean-machine smoke test | **Not run.** `WindowsSandbox.exe` is absent, so the optional feature isn't installed. Enabling it needs elevation and a reboot, which was not done without approval. Residual risk is low: the exe needs only the Windows 10/11 UCRT, and it bundles `VCRUNTIME140.dll`. It passed 17/17 from an extracted zip with Python hidden, but on the development PC. |

### Publication audit (2026-11-06)

**Reused code, all compatible with MIT distribution:**

| Component | License | Use |
|---|---|---|
| Memoria | MIT | PC schema, container constants, settings defaults (notice kept) |
| ffix-save-editor | MIT | PS1 text table (notice kept). Its upstream, the gjoerulv editor, states public domain, and the table is a factual font mapping |
| ff9SaveLib | GPL-3.0 | none (local test fixture only) |
| gjoerulv editor | public domain | none (offset notes cited) |
| Decompiled game | — | none (interoperability facts only) |

No item, ability or card name tables are included.

**Publishable set**, meaning what `git add .` would include under the current `.gitignore` (68 files). It contains no `.mcr/.mcd/.srm/.dat/.sav/.gme/.psv/.mcs/.vmp/.bin/.iso/.chd/.cue/.m3u`, no images and no executables. The only personal-name match is the copyright line in `LICENSE` and `NOTICES.md`; there are no usernames, Steam account IDs, local drive paths or e-mail addresses.

Fixed during this audit:
- `cloud_guard.py` hardcoded the Steam account ID and the RetroArch card paths. It now auto-detects the account (or reads `STEAM_ACCOUNT_ID`) and takes `FF9_PROTECTED`.
- `ff9_step.py` defaulted to a path under the user profile; `FF9_REFS` is now required.
- `build_manifest.py`, `RUNTIME_READINESS.md` and `START_HERE.md` named local drive paths.
- Newly git-ignored, as regenerable inventories that held personal-save details, quoted save-site descriptions and Dropbox links to other players' saves:
  - `fixtures/manifest.json` and `fixtures/provenance.jsonl`;
  - `research/sources_*.json`.

**Public checkout simulation.** Only those 68 files were copied to an empty folder: **15 passed, 90 skipped, 0 failed**. The fixture-dependent tests skip cleanly.

Recommended before or at public beta, not blocking:
- **Unsigned executable.** Windows SmartScreen will warn on first run. Either document it (the README already gives the SHA-256) or code-sign later.
- **Test fixtures can't be published** (community and personal saves). A public checkout runs only the fixture-independent tests; publish the qualification evidence instead. Synthetic generated fixtures would be a good later improvement.
- **Coverage limits:**
  - NTSC-U only: PAL is unverified, Japanese is refused.
  - Memoria/Moguri untested.
  - Steam build 5378074 only.

  These are documented in COMPATIBILITY.md and are acceptable for a beta that says so.

## Release candidate artifacts (local only; nothing published)

| Artifact | SHA-256 |
|---|---|
| `release/v0.1.0-beta/…win-x64.zip` (first RC) | `5ac7d9a065686eb26c004f9e38c49b9906df4708258636ab300382c163d8003d` |
| `release/v0.1.0-beta-rc2/…win-x64.zip` (same converter code, updated docs) | see `release/v0.1.0-beta-rc2/SHA256SUMS.txt` |
| **`release/v0.1.0-beta-final/ffix-convert-0.1.0-beta-win-x64.zip` (final: adds LICENSE.txt and updated NOTICES)** | `64eb5fbe9ff447ae3f71c07ecb16885c0ab96c1945a75998ed728f10d7048e3e` |
| `release/v0.1.0-beta-final/…/ffix-convert.exe` | `9ea75707a3a8a98b7eb8334aa496267241f367949134f0e9b91ee83a5bdb2824` |

The final package passed 17/17 smoke checks run from the extracted zip, and the full suite passed (381 passed, 1 skipped). The exe was searched (raw bytes, every archive entry and every bundled module) for the local username, the handle and build paths: none found.

## Qualification

| Check | Result |
|---|---|
| Automated suite | **381 passed, 0 failed, 1 skipped** (symlink creation needs Developer Mode; junction and hard-link aliasing are tested) |
| Packaged exe, run from the extracted zip with no Python | **17/17 passed** (`reports/exe_smoke_results.txt`) |
| PS1 → PC in Steam build 5378074 | Round 1: your Bentini run (story, battle, save, restart, reload), Gulug, Disc 3/4 openings, Memoria, Castle. **Round 2:** your Disc 2 start (correct opening and next scene), Treno Disc 3 (world/town transitions, battle, **save, restart, reload**), Disc 4 world map, Crystal World (exact stats including used stones; correct final-dungeon event) |
| PC → PS1 in DuckStation 0.1-7878 | Gulug; Disc 4 world map (save/reset/reload); Disc 2 and Disc 3 openings; your 2021 early game; Eiko-led Lv 99 late game (save, reset, reload) |
| Your data | 2021 cloud save `00aa9674…` (= Steam's cloud record), Steam remote cache and both RetroArch cards: **unchanged** at every check. PC save folder restored (`1657b6d4…`). FF9 cloud toggle restored to ON; Steam reports "File is in sync" |

## License: **MIT** (adopted 2026-11-06)

**Why MIT:**
- It matches the two projects this code borrows from, both MIT: Memoria (PC save schema) and ffix-save-editor (PS1 text table). Their notices are simply kept.
- It's the norm in the FF9 modding/save-tool community, imposes nothing on users, and is compatible with every bundled component.
- Apache-2.0 would also work and adds an explicit patent grant, but it brings NOTICE/change-marking bookkeeping that brings no practical benefit for a save converter.
- Avoid GPL for the converter itself: nothing requires it (no GPL code is used), and it would complicate reuse by other MIT tools.

**Obligations when distributing the Windows zip.** All are already met by `NOTICES.md` and `THIRD_PARTY_LICENSES/`:

| Component | License | What you must do |
|---|---|---|
| Memoria-derived schema | MIT | keep the copyright notice and license text (done) |
| ffix-save-editor text table | MIT | keep the copyright notice and license text (done) |
| Python 3.14 runtime and stdlib, including bundled bzip2, zstd, OpenSSL 3 (`libcrypto`) and others | PSF-2.0 plus the listed component licenses | include `Python-LICENSE.txt`, which already contains the OpenSSL/Apache-2.0, bzip2 and zstd notices (done) |
| cryptography 50.0.2 (statically includes OpenSSL in its Rust extension) | Apache-2.0 **or** BSD-3-Clause, your choice | ship the license texts (done). Under BSD-3, keep the copyright notice and don't use the authors' names for endorsement. No NOTICE file exists |
| cffi 2.1.1 | MIT-0 | none (text included anyway) |
| PyInstaller 6.22.3 bootloader | GPL-2.0 with bootloader exception | none for your code; the exception allows any license for the built exe. License text included |
| VCRUNTIME140.dll | Microsoft redistributable | permitted to redistribute with the application; no action |

**Not affected:**
- ff9SaveLib (GPL-3.0): no code is used.
- The decompiled game code: none is included. Only facts are, and the extracted tables stay out of the repo.

**What you must not distribute under any license:**
- the save fixtures (community and personal);
- the `research/repos` clones (re-clone them instead);
- `research/vanilla_extracts/`.

All are git-ignored.

## Audit findings across this release cycle

All fixed with regression tests unless marked otherwise.
1. Silent truncation of oversized PC strings.
2. Undecodable PS1 names passing through.
3. Unsafe write path, replaced by atomic writes with verification, backups and alias detection.
4. No independent output verification; now automatic, plus a `verify` command.
5. Silent location shortening (cosmetic).
6. Console apostrophe rendering (cosmetic).
7. Build picking up stray DLLs.
8. The PS1 preview leader is chosen by the game (cosmetic, documented, not changed).
9. 0x09C0 identified as the PS1 step counter (information).
10. Test-automation risk at the Cloud Data menu (process): **resolved** by turning FF9 cloud off for testing and by the screenshot guard.
11. New documented PC normalization: when the PC derives a guest's `bonus_cap` from 0, guest max stones are recomputed (Beatrix 16 → 18). This is native PC behavior.
