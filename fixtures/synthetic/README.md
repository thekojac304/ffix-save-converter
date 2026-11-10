# Synthetic fixtures

No synthetic save files are stored here. Tests that need synthetic data build it in memory and label it in
the test name/docstring:

* `tests/test_ps1.py::_card_with` builds memory cards (multiple occupied blocks, empty card, corrupted
  directory frame) from real FantasyAnime blocks.
* `tests/test_ps1.py::test_wrappers_detected` wraps a real block in GME / VGS / VMP / MCS / PSV headers.
  These only prove self-consistency of the wrapper parsers; no real GME/VGS/VMP/MCS/PSV files were available.
* `tests/test_convert.py` edge cases mutate a canonical model in memory (too many cards, bad party values,
  out-of-range gil, maximal inventory/abilities).

Synthetic data is never used as evidence for a field mapping.
