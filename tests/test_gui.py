"""The desktop GUI (v0.3 three-step window), driven offscreen.

The window must only gather choices and call the batch service, never write unsafely. Every scenario of the v0.2
GUI tests is covered again here (load, drag and drop, occupied places, in-place updates with backups, wrong
destination kinds, Steam Cloud refusal, no overwriting, one conversion at a time, keyboard access, Memoria), plus
batch selection, multiple memory cards, problem saves, cancel, recovery, themes and window sizes.
"""
import hashlib
import json
import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QMimeData, QPointF, QSettings, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QLineEdit, QRadioButton,  # noqa: E402
                               QTreeWidget)

from conftest import ROOT, USER_CARDS, pcf  # noqa: E402
from ffix_conv import batch, pc_container, ps1_card, safeio, service  # noqa: E402
from ffix_conv.gui import app as gui  # noqa: E402
from ffix_conv.gui import icon  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
MEMORIA = os.path.join(ROOT, "fixtures", "memoria", "runtime_20261106")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def settle(w):
    assert gui.wait_idle(APP, w, 60000), "window did not become idle"


def user_card(n):
    import glob
    m = [f for f in glob.glob(os.path.join(USER_CARDS, "*.srm"))
         if len(ps1_card.parse_file(open(f, "rb").read())[1]) == n]
    if not m:
        pytest.skip(f"user card with {n} saves not present")
    return m[0]


@pytest.fixture
def win(tmp_path):
    w = gui.MainWindow(settings=QSettings(str(tmp_path / "gui.ini"), QSettings.Format.IniFormat))
    w.answers = []
    w.answer = True
    w.confirm = lambda title, text: (w.answers.append(title), w.answer)[1]
    w.out_pick.set_path(str(tmp_path / "out"), emit=False)
    w.resize(760, 900)
    w.show()
    yield w
    settle(w)
    w.close()


def load(w, path):
    w.load_source(str(path))
    settle(w)
    assert w.source is not None, w.src_notice.body.text()


def existing(w, path):
    w.existing_radio.setChecked(True)
    w.into_pick.set_path(str(path))
    settle(w)


def convert(w, ok=True):
    assert w.convert_btn.isEnabled(), (w.summary.text(), w.problem_notice.body.text())
    results = []
    w.conversion_finished.connect(results.append)
    w.convert_btn.click()
    settle(w)
    assert results == [ok], w.fail_notice.body.text()
    return w.last_result


@pytest.fixture
def card15(tmp_path):
    return shutil.copy(user_card(15), tmp_path / "card15.srm")


@pytest.fixture
def card13(tmp_path):
    return shutil.copy(user_card(13), tmp_path / "card13.srm")


@pytest.fixture
def pc6(tmp_path):
    d = tmp_path / "pcsave"
    d.mkdir()
    return shutil.copy(pcf("steam_cd3thread_SavedData_ww.dat"), d / "SavedData_ww.dat")


# ---- loading ---------------------------------------------------------------------------------------
def test_icon_draws_and_writes_ico(tmp_path):
    assert not icon.pixmap(32).isNull()
    p = tmp_path / "app.ico"
    icon.write_ico(p)
    data = p.read_bytes()
    assert data[:4] == b"\0\0\1\0" and int.from_bytes(data[4:6], "little") == 7


def test_load_full_ps1_card(win, card15):
    load(win, card15)
    assert win.save_list.topLevelItemCount() == 15 and win.target() == "pc"
    assert "15 Final Fantasy IX saves (FILE01–FILE15)" in win.src_summary.text()
    assert win.all_radio.isChecked() and win.all_radio.text() == "Convert &all 15 saves"
    assert win.convert_btn.isEnabled() and win.convert_btn.text() == "&Convert 15 saves"
    assert win.place_label.text() == "They go into slot 1, files 1–15."
    assert "PC (Steam)" in win.dir_label.text()
    assert win.save_list.topLevelItem(2).text(0) == "FILE03"
    # plain words in the main window: no internal jargon
    texts = " ".join(x.text() for x in win.findChildren(QtWidgets.QLabel) if x.isVisibleTo(win))
    for word in ("sidecar", "canonical", "serialized", "container"):
        assert word not in texts.lower()


def test_load_pc_file_targets_ps1(win, pc6):
    load(win, pc6)
    assert win.target() == "ps1" and win.save_list.topLevelItemCount() == 6
    assert "slots 1, 2, 4" in win.src_summary.text()
    assert "one new memory card" in win.place_label.text() and "FILE01–FILE06" in win.place_label.text()
    assert win.new_radio.text() == "Create &new memory cards"


def test_unreadable_file_shows_a_message(win, tmp_path):
    p = tmp_path / "junk.dat"
    p.write_bytes(b"hello")
    win.load_source(str(p))
    settle(win)
    assert win.source is None and win.src_notice.isVisible()
    assert "Could not read junk.dat" in win.src_notice.title.text()
    assert not win.convert_btn.isEnabled()


def test_drag_and_drop_loads_file(win, card13):
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(card13))])
    ev = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, md, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    win.drop.dropEvent(ev)
    settle(win)
    assert win.source and win.save_list.topLevelItemCount() == 13


# ---- PS1 -> PC ---------------------------------------------------------------------------------------
def test_convert_all_to_new_pc_file(win, card15, tmp_path):
    before = sha(card15)
    load(win, card15)
    r = convert(win)
    out = r["outputs"][0]["path"]
    assert out == str(tmp_path / "out" / "card15 (PC save)" / "SavedData_ww.dat")
    assert pc_container.Container(open(out, "rb").read()).occupied() == [(0, f) for f in range(15)]
    assert sha(card15) == before and win.stack.currentIndex() == 1
    assert "15 saves converted and checked" in win.res_title.text()
    for blk in (1, 8, 15):
        assert service.verify_files(card15, out, str(blk), f"1/{blk}")["counts"]["unexpected"] == 0


def test_choose_some_saves(win, card15):
    load(win, card15)
    win.some_radio.setChecked(True)
    assert win.save_list.isVisible() and win.sel_row.isVisible()
    win._check_all(False)
    for i in (2, 9):
        win.save_list.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked)
    settle(win)
    assert win.convert_btn.text() == "&Convert 2 saves" and "2 of 15 selected" in win.sel_count.text()
    r = convert(win)
    assert pc_container.Container(open(r["outputs"][0]["path"], "rb").read()).occupied() == [(0, 2), (0, 9)]


def test_nothing_selected_disables_convert(win, card15):
    load(win, card15)
    win.some_radio.setChecked(True)
    win._check_all(False)
    settle(win)
    assert not win.convert_btn.isEnabled() and "Tick at least one" in win.summary.text()


def test_add_to_existing_pc_file_keeps_saves_and_backs_up(win, card13, pc6):
    before = sha(pc6)
    orig = pc_container.Container(open(pc6, "rb").read())
    load(win, card13)
    existing(win, pc6)
    assert "slot 3, files 1–13" in win.place_label.text() and "6 saves already in the file are kept" in win.place_label.text()
    assert "is updated (a backup copy is made first)" in win.summary.text()
    r = convert(win)
    assert r["outputs"][0]["path"] == os.path.abspath(pc6) and sha(r["outputs"][0]["backup"]) == before
    c = pc_container.Container(open(pc6, "rb").read())
    for s, f in orig.occupied():
        assert c.slot_plain(s, f) == orig.slot_plain(s, f)
    assert len(c.occupied()) == 19
    assert "added (the saves that were already in it are kept)" in win.res_body.text()


def test_occupied_slot_needs_explicit_replace(win, card13, pc6):
    before = sha(pc6)
    load(win, card13)
    existing(win, pc6)
    win.adv.pc_slot.setCurrentIndex(win.adv.pc_slot.findData(2))
    settle(win)
    assert win.warn_notice.isVisible() and "4 saves already there would be replaced" in win.warn_notice.title.text()
    assert win.replace_box.isVisible() and not win.convert_btn.isEnabled()
    win.replace_box.setChecked(True)
    assert win.convert_btn.isEnabled()
    r = convert(win)
    assert sha(r["outputs"][0]["backup"]) == before


def test_copy_instead_leaves_existing_file_alone(win, card13, pc6):
    before = sha(pc6)
    load(win, card13)
    win.adv.copy_instead.setChecked(True)
    existing(win, pc6)
    assert "new copy" in win.summary.text()
    r = convert(win)
    assert sha(pc6) == before and "with_converted_saves" in r["outputs"][0]["path"]


def test_wrong_kind_of_destination_is_explained(win, card13, card15):
    load(win, card13)
    existing(win, card15)                                   # a PS1 card where a PC file is needed
    assert win.problem_notice.isVisible() and "PS1 memory card" in win.problem_notice.body.text()
    assert not win.convert_btn.isEnabled()


def test_cloud_destination_is_refused(win, card13, tmp_path):
    load(win, card13)
    win.out_pick.set_path(str(tmp_path / "Steam" / "userdata" / "1" / "377840" / "remote"))
    settle(win)
    assert win.problem_notice.isVisible() and "Steam Cloud" in win.problem_notice.body.text()
    assert not win.convert_btn.isEnabled()


def test_second_conversion_never_overwrites(win, card13, tmp_path):
    load(win, card13)
    first = convert(win)["outputs"][0]["path"]
    win.back_to_form()
    settle(win)
    second = convert(win)["outputs"][0]["path"]
    assert first != second and os.path.exists(first) and "card13 (PC save)-2" in second


def test_double_click_starts_one_conversion(win, card13, tmp_path):
    load(win, card13)
    win.convert_btn.click()
    win.convert_btn.click()
    win.start_conversion()
    settle(win)
    assert os.listdir(tmp_path / "out") == ["card13 (PC save)"]


def test_damaged_save_can_be_left_out(win, card13, tmp_path):
    raw = bytearray(open(card13, "rb").read())
    raw[4 * ps1_card.BLOCK + 0x400] ^= 0xFF
    bad = tmp_path / "bad.srm"
    bad.write_bytes(raw)
    load(win, bad)
    assert win.problem_notice.isVisible() and "1 save cannot be converted" in win.problem_notice.title.text()
    assert "FILE04 looks damaged" in win.problem_notice.body.text()
    assert not win.convert_btn.isEnabled() and win.save_list.topLevelItem(3).text(5).startswith("⚠")
    leave = [b for b in win.problem_notice.buttons if "Leave" in b.text()][0]
    leave.click()
    settle(win)
    assert win.convert_btn.text() == "&Convert 12 saves"
    convert(win)


# ---- PC -> PS1 ---------------------------------------------------------------------------------------
def big_pc(tmp_path):
    out = str(tmp_path / "big" / "SavedData_ww.dat")
    batch.run(batch.BatchOptions(user_card(15), out=out, timestamp=1.7e9))
    batch.run(batch.BatchOptions(user_card(13), into=out, in_place=True, timestamp=1.7e9))
    return out


def test_pc_to_several_memory_cards(win, tmp_path):
    src = big_pc(tmp_path)
    load(win, src)
    assert "2 new memory cards" in win.place_label.text()
    assert "FFIX-PS1-Card-01.mcr (FILE01–FILE15)" in win.place_label.text()
    r = convert(win)
    names = sorted(os.listdir(os.path.dirname(r["outputs"][0]["path"])))
    assert names == ["FFIX-PS1-Card-01.mcr", "FFIX-PS1-Card-02.mcr", "conversion-manifest.json",
                     "conversion-manifest.txt"]
    assert "conversion-manifest.txt" in win.res_next.text()


def test_pc_to_existing_card_renumbers_and_explains(win, pc6, card13):
    load(win, pc6)
    win.some_radio.setChecked(True)
    win._check_all(False)
    win.save_list.topLevelItem(1).setCheckState(0, Qt.CheckState.Checked)        # slot 2, file 1
    existing(win, card13)
    assert "FILE14" in win.place_label.text() and "13 saves already on the card are kept" in win.place_label.text()
    assert win.warn_notice.isVisible() and "already used on this card" in win.warn_notice.body.text()
    before = sha(card13)
    r = convert(win)
    assert sha(r["outputs"][0]["backup"]) == before


def test_full_existing_card_is_explained(win, pc6, card15):
    load(win, pc6)
    existing(win, card15)
    assert win.problem_notice.isVisible() and "room for 0" in win.problem_notice.body.text()


# ---- Memoria -----------------------------------------------------------------------------------------
def memoria_copy(tmp_path, case):
    src = os.path.join(MEMORIA, case)
    if not os.path.isdir(src):
        pytest.skip("Memoria runtime fixtures not present")
    shutil.copytree(src, tmp_path / case)
    return str(tmp_path / case / "SavedData_ww.dat")


def test_memoria_saves_need_explicit_lossy(win, tmp_path):
    src = memoria_copy(tmp_path, "sidecar_cases")
    load(win, src)
    assert "Memoria extra data found for 3 saves" in win.src_detail.text()
    assert "damaged Memoria data file" in win.problem_notice.body.text()
    assert not win.convert_btn.isEnabled()
    win.adv.lossy.setChecked(True)
    settle(win)
    assert win.convert_btn.isEnabled() and "Lossy conversion is on" in win.warn_notice.body.text()
    convert(win)


def test_vanilla_pc_file_has_no_memoria_wording(win, pc6):
    load(win, pc6)
    assert "Memoria" not in win.src_detail.text()
    assert all(not win.save_list.topLevelItem(i).text(5) for i in range(6))


# ---- safety --------------------------------------------------------------------------------------------
def test_cancel_writes_nothing(win, card15, tmp_path):
    load(win, card15)
    win.engine.submit(lambda progress, cancel: __import__("time").sleep(0.5))     # keep the worker busy
    res = []
    win.conversion_finished.connect(res.append)
    win.convert_btn.click()
    assert win.cancel_btn.isVisible()
    win.cancel()
    settle(win)
    assert res == [False] and "Nothing was changed" in win.fail_notice.body.text()
    assert not os.path.exists(tmp_path / "out" / "card15 (PC save)")


def test_write_failure_is_reported_and_undone(win, card13, pc6, monkeypatch):
    before = sha(pc6)
    load(win, card13)
    existing(win, pc6)

    def fail(tmp, dest, replace):
        raise OSError("simulated disk error")
    monkeypatch.setattr(safeio, "_place", fail)
    convert(win, ok=False)
    assert "Nothing was converted" in win.fail_notice.title.text() and "put back" in win.fail_notice.body.text()
    assert sha(pc6) == before


def test_interrupted_conversion_can_be_undone_from_the_window(win, card13, pc6, monkeypatch):
    before = sha(pc6)
    real = safeio._place

    def crash(tmp, dest, replace):
        real(tmp, dest, replace)
        raise KeyboardInterrupt
    monkeypatch.setattr(safeio, "_place", crash)
    monkeypatch.setattr(safeio, "_undo", lambda entries, done: ["simulated crash"])
    with pytest.raises(safeio.SafetyError):
        batch.run(batch.BatchOptions(card13, into=pc6, in_place=True))
    monkeypatch.undo()
    load(win, card13)
    existing(win, pc6)
    btn = [b for b in win.problem_notice.buttons if "Undo the interrupted" in b.text()]
    assert btn and not win.convert_btn.isEnabled()
    btn[0].click()
    settle(win)
    assert win.answers == ["Undo the interrupted conversion?"]
    assert sha(pc6) == before and "undone" in win.fail_notice.title.text()
    assert win.convert_btn.isEnabled()


# ---- same answers as the command line ---------------------------------------------------------------------
def test_gui_plan_matches_service_and_cli(win, pc6, tmp_path):
    load(win, pc6)
    gui_saves = [(a.id, a.dest_label) for a in win.plan.assignments]
    svc = batch.prepare(batch.BatchOptions(pc6))
    assert gui_saves == [(a.id, a.dest_label) for a in svc.assignments]
    import subprocess
    import sys
    p = subprocess.run([sys.executable, "-m", "ffix_conv", "batch", str(pc6), "--json", "--dry-run"],
                       capture_output=True, text=True, cwd=ROOT,
                       env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")})
    j = json.loads(p.stdout[:p.stdout.rindex("}") + 1])
    assert [(s["source"], s["destination"]) for s in j["saves"]] == gui_saves


def test_advanced_details_and_log(win, card13):
    load(win, card13)
    html = win.adv.details.toHtml()
    assert "FILE01" in html and "Checked by reading the converted copy back" in html
    assert "13 save(s)" in win.adv.log_view.toPlainText()
    assert win.adv.table.rowCount() == 13 and win.adv.table.item(0, 2).text() == "1/1"
    win.adv.manual.setChecked(True)
    win.adv.table.item(0, 2).setText("9/9")
    settle(win)
    assert win.plan.assignments[0].dest_label == "Slot 9, file 9"


# ---- keyboard, accessibility, themes, sizes ------------------------------------------------------------
def test_keyboard_and_accessibility(win, card15):
    load(win, card15)
    for w in win.findChildren(QAbstractButton):
        if w.isVisibleTo(win) and w.text():
            assert w.focusPolicy() & Qt.FocusPolicy.TabFocus, w.text()
    for w in (win.all_radio, win.some_radio, win.new_radio, win.existing_radio, win.browse_btn, win.adv_btn):
        assert "&" in w.text(), w.text()
    assert "&" in win.convert_btn.text()
    for w in win.findChildren(QLineEdit) + win.findChildren(QTreeWidget) + win.adv.findChildren(QComboBox):
        assert w.accessibleName(), w
    assert win.convert_btn.accessibleName() == "Convert 15 saves"
    # no two visible controls share an access key (on the main page, with every optional row shown)
    win.some_radio.setChecked(True)
    settle(win)
    keys = {}
    page = win.stack.widget(0)
    for w in page.findChildren(QAbstractButton) + page.findChildren(QtWidgets.QLabel):
        text = w.text() if w.isVisibleTo(win) else ""
        if isinstance(w, QtWidgets.QLabel) and not w.buddy():
            continue
        if "&" in text.replace("&&", ""):
            k = text[text.replace("&&", "  ").index("&") + 1].lower()
            assert k not in keys, (text, keys.get(k))
            keys[k] = text


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_themes(win, card15, scheme):
    from PySide6.QtGui import QPalette
    style, pal, hint = APP.style().name(), QPalette(APP.palette()), APP.styleHints().colorScheme()
    try:
        gui.apply_theme(APP, scheme)
        APP.processEvents()
        load(win, card15)
        win.list_toggle.setChecked(True)
        gui.settle_layout(APP)
        from ffix_conv.gui.widgets import is_dark, tone
        assert is_dark(win) == (scheme == "dark")
        assert tone(win, "error") == ("#ffb4ab" if scheme == "dark" else "#b3261e")
        assert gui.layout_problems(win) == []
        win.grab().save(os.path.join(os.path.dirname(win.settings.fileName()), f"theme-{scheme}.png"))
    finally:
        APP.setStyle(style)
        APP.setPalette(pal)
        APP.styleHints().setColorScheme(hint)


@pytest.mark.parametrize("size", [(520, 460), (640, 600), (1280, 1000)])
def test_window_sizes_have_no_clipped_controls(win, card15, size):
    win.resize(*size)
    load(win, card15)
    win.some_radio.setChecked(True)
    settle(win)
    gui.settle_layout(APP)
    assert gui.layout_problems(win) == []
    assert win.stack.currentWidget().horizontalScrollBar().maximum() == 0 or size[0] < 560
