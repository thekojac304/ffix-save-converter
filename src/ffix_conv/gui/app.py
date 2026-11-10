"""FFIX Save Converter: the Windows desktop application.

  1  Your saves                 drop or browse a PS1 memory card or a PC save file; convert all saves or choose some
  2  Where should they go?      a new file (or new memory cards), or an existing file of the other version
  3  Convert                    what will happen, anything that needs a decision, and one Convert button

The window decides nothing about save data. Reading (batch.scan), planning and verifying (batch.prepare) and writing
(batch.commit, one all-or-nothing transaction) are service calls, the same code the command line runs, executed on
one worker thread: the window never freezes and two conversions can never run at once. Every change of a choice
re-plans in the background; Convert is enabled only for a plan that matches the current choices and passed every
check. Technical controls live in Advanced.

  "FFIX Save Converter.exe" [save file]               normal start (optionally with a save file)
  "FFIX Save Converter.exe" --automate job.json       drive the real window from a JSON job, write the outcome, exit
  "FFIX Save Converter.exe" --smoke result.json       open, optionally load a file, capture the window, report, exit
  --theme light|dark   --size WIDTHxHEIGHT            (with --smoke/--automate, or alone)
  --settings FILE.ini  --out-folder FOLDER            keep settings in an .ini file; preset the output folder (tests)
"""
import json
import os
import sys
import traceback

from PySide6.QtCore import QElapsedTimer, QRect, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QRadioButton, QScrollArea, QStackedWidget, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import __version__, batch, safeio, service
from . import icon
from .advanced import AdvancedDialog
from .messages import MEMORIA, PLATFORM, PROBLEM, file_ranges, plural, ps1_files
from .widgets import DropArea, Notice, PathPicker, PrimaryButton, Step, label, set_text, soft
from .worker import Engine, skipped

APP_NAME = "FFIX Save Converter"
PC_SAVE_DIR = os.path.join(os.path.expanduser("~"), r"AppData\LocalLow\SquareEnix\FINAL FANTASY IX\Steam\EncryptedSavedData")
SAVE_FILTER = ("Final Fantasy IX saves (*.dat *.mcr *.mcd *.srm *.gme *.vgs *.mem *.vmp *.psv *.mcs *.ps1 *.bin);;"
               "All files (*)")
CONTENT_WIDTH = 760


def default_output_folder():
    return os.path.join(os.path.expanduser("~"), "Documents", "FFIX Save Converter")


def initial_size(app):
    avail = app.primaryScreen().availableGeometry()
    return min(800, int(avail.width() * 0.9)), min(780, int(avail.height() * 0.9))


class MainWindow(QMainWindow):
    conversion_finished = Signal(bool)          # True = written and verified (automation and tests)

    def __init__(self, settings=None, engine=None):
        super().__init__()
        self.settings = settings or QSettings("FFIXSaveConverter", APP_NAME)
        self.engine = engine or Engine(self)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon.app_icon())
        self.setMinimumSize(520, 460)
        self.setAcceptDrops(True)
        self.source = None              # {"path", "head", "items"} from batch.scan
        self.plan = None                # batch.Plan for the current choices
        self.plan_error = None
        self.plan_pending = False
        self.loading = False
        self.running = False            # a conversion is being written
        self.job = None                 # the worker job that is running (for Cancel)
        self.last_result = None
        self._plan_gen = 0
        self._src_gen = 0
        self._filling = False
        self.plan_timer = QTimer(self, singleShot=True, interval=200)
        self.plan_timer.timeout.connect(self.start_plan)
        self.confirm = lambda title, text: QMessageBox.question(
            self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        self.ask_open = lambda: QFileDialog.getOpenFileName(self, "Open a save file", self._start_dir(), SAVE_FILTER)[0]
        self.ask_folder = lambda title: QFileDialog.getExistingDirectory(self, title, self._start_dir())
        self.adv = AdvancedDialog(self)
        self.adv.changed.connect(self.schedule_plan)
        self.adv.recover_requested.connect(lambda: self.recover())
        self._build()
        self.out_pick.set_path(self.settings.value("output_folder", "") or default_output_folder(), emit=False)
        self.refresh()

    # ------------------------------------------------------------------------------------------- layout
    def _build(self):
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.stack.addWidget(self._scroll(self._form_page()))
        self.stack.addWidget(self._scroll(self._result_page()))
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.browse_source)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_conversion)
        QShortcut(QKeySequence("Escape"), self, activated=self.cancel)

    @staticmethod
    def _scroll(inner):
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(16, 14, 16, 14)
        h.addStretch(1)
        inner.setMaximumWidth(CONTENT_WIDTH)
        h.addWidget(inner, 100)
        h.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        sa.setWidget(holder)
        return sa

    def _form_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        head = label(APP_NAME, bold=True, scale=1.45, wrap=False)
        sub = label("Move your Final Fantasy IX saves between the PlayStation and the PC (Steam) version.", muted=True)
        lay.addWidget(head)
        lay.addWidget(sub)

        # 1 -------------------------------------------------------------------------------------
        s1 = Step("1", "Your saves")
        self.drop = DropArea()
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(14, 14, 14, 14)
        dl.setSpacing(6)
        self.drop_title = label("Drag your save file here", bold=True, scale=1.1)
        self.drop_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.drop_hint = label("a PlayStation memory card (.mcr .mcd .srm .gme .vmp .psv .mcs …) "
                               "or the PC save file SavedData_ww.dat", muted=True)
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.browse_btn = QPushButton("&Browse…")
        self.browse_btn.setAccessibleName("Browse for your save file")
        self.browse_btn.clicked.connect(self.browse_source)
        brow = QHBoxLayout()
        brow.addStretch(1)
        brow.addWidget(self.browse_btn)
        brow.addStretch(1)
        dl.addWidget(self.drop_title)
        dl.addWidget(self.drop_hint)
        dl.addLayout(brow)
        self.drop.dropped.connect(self.load_source)
        s1.body.addWidget(self.drop)
        self.src_summary = label(selectable=True, bold=True)
        self.src_detail = label(selectable=True)
        self.src_notice = Notice()
        for w in (self.src_summary, self.src_detail, self.src_notice):
            s1.body.addWidget(w)
        self.pick_row = QWidget()
        pr = QVBoxLayout(self.pick_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(4)
        self.all_radio = QRadioButton("Convert &all saves")
        self.some_radio = QRadioButton("C&hoose saves")
        self.all_radio.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.all_radio)
        grp.addButton(self.some_radio)
        self.all_radio.toggled.connect(self._selection_mode_changed)
        self.list_toggle = QToolButton()
        self.list_toggle.setCheckable(True)
        self.list_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.list_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.list_toggle.setText("Show the saves")
        self.list_toggle.setAutoRaise(True)
        self.list_toggle.toggled.connect(self._list_toggled)
        pr.addWidget(self.all_radio)
        pr.addWidget(self.some_radio)
        pr.addWidget(self.list_toggle)
        s1.body.addWidget(self.pick_row)
        self.save_list = QTreeWidget()
        self.save_list.setHeaderLabels(["Save", "Where", "Disc", "Party", "Play time", "Note"])
        self.save_list.setRootIsDecorated(False)
        self.save_list.setUniformRowHeights(True)
        self.save_list.setAccessibleName("Saves in this file")
        self.save_list.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.save_list.header().setStretchLastSection(False)
        self.save_list.setMinimumHeight(150)
        self.save_list.itemChanged.connect(self._item_checked)
        s1.body.addWidget(self.save_list)
        self.sel_row = QWidget()
        sr = QHBoxLayout(self.sel_row)
        sr.setContentsMargins(0, 0, 0, 0)
        self.sel_all = QPushButton("Tic&k all")
        self.sel_none = QPushButton("&Untick all")
        self.sel_all.clicked.connect(lambda: self._check_all(True))
        self.sel_none.clicked.connect(lambda: self._check_all(False))
        self.sel_count = label(muted=True)
        sr.addWidget(self.sel_all)
        sr.addWidget(self.sel_none)
        sr.addWidget(self.sel_count, 1)
        s1.body.addWidget(self.sel_row)
        lay.addWidget(s1)

        # 2 -------------------------------------------------------------------------------------
        s2 = Step("2", "Where should they go?")
        self.s2 = s2
        self.dir_label = label()
        s2.body.addWidget(self.dir_label)
        self.new_radio = QRadioButton("&New file")
        self.existing_radio = QRadioButton("Add to an &existing file")
        self.new_radio.setChecked(True)
        g2 = QButtonGroup(self)
        g2.addButton(self.new_radio)
        g2.addButton(self.existing_radio)
        self.new_radio.toggled.connect(self._dest_mode_changed)
        s2.body.addWidget(self.new_radio)
        self.out_row = QWidget()
        orow = QHBoxLayout(self.out_row)
        orow.setContentsMargins(24, 0, 0, 0)
        olab = label("Save in:", wrap=False)
        self.out_pick = PathPicker("Choose where the converted saves are created", "folder", name="Output folder")
        olab.setBuddy(self.out_pick.edit)
        self.out_pick.changed.connect(lambda _: self.schedule_plan())
        orow.addWidget(olab)
        orow.addWidget(self.out_pick, 1)
        s2.body.addWidget(self.out_row)
        s2.body.addWidget(self.existing_radio)
        self.into_row = QWidget()
        irow = QVBoxLayout(self.into_row)
        irow.setContentsMargins(24, 0, 0, 0)
        self.into_pick = PathPicker("Choose the file to add the saves to", "file", SAVE_FILTER, name="Existing file")
        self.into_pick.changed.connect(lambda _: self.schedule_plan())
        self.into_hint = label(muted=True)
        irow.addWidget(self.into_pick)
        irow.addWidget(self.into_hint)
        s2.body.addWidget(self.into_row)
        self.place_label = label(selectable=True)
        s2.body.addWidget(self.place_label)
        prow = QHBoxLayout()
        self.place_btn = QPushButton("Change &placement…")
        self.place_btn.setFlat(True)
        self.place_btn.clicked.connect(lambda: self.adv.show_tab("placement"))
        prow.addWidget(self.place_btn)
        prow.addStretch(1)
        s2.body.addLayout(prow)
        lay.addWidget(s2)

        # 3 -------------------------------------------------------------------------------------
        s3 = Step("3", "Convert")
        self.summary = label(selectable=True)
        s3.body.addWidget(self.summary)
        self.problem_notice = Notice()
        s3.body.addWidget(self.problem_notice)
        self.warn_notice = Notice()
        s3.body.addWidget(self.warn_notice)
        self.replace_box = QCheckBox()
        self.replace_box.toggled.connect(lambda *_: self.refresh())
        s3.body.addWidget(self.replace_box)
        self.progress_row = QWidget()
        pl = QVBoxLayout(self.progress_row)
        pl.setContentsMargins(0, 0, 0, 0)
        self.progress = QProgressBar()
        self.progress.setAccessibleName("Progress")
        self.progress.setTextVisible(False)
        self.progress_label = label(muted=True)
        pl.addWidget(self.progress)
        pl.addWidget(self.progress_label)
        s3.body.addWidget(self.progress_row)
        brow = QHBoxLayout()
        self.convert_btn = PrimaryButton("&Convert")
        self.convert_btn.setDefault(True)
        self.convert_btn.clicked.connect(self.start_conversion)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel)
        brow.addWidget(self.convert_btn, 1)
        brow.addWidget(self.cancel_btn)
        s3.body.addLayout(brow)
        self.reassure = label("Your original files are never changed. Every converted save is read back and "
                              "checked before anything is written.", muted=True)
        s3.body.addWidget(self.reassure)
        self.fail_notice = Notice()
        s3.body.addWidget(self.fail_notice)
        lay.addWidget(s3)

        lay.addStretch(1)
        bottom = QHBoxLayout()
        self.adv_btn = QPushButton("A&dvanced…")
        self.adv_btn.setFlat(True)
        self.adv_btn.clicked.connect(lambda: self.adv.show_tab("placement"))
        help_btn = QPushButton("Help (F1)")
        help_btn.setFlat(True)
        help_btn.clicked.connect(lambda: self._open_doc("GUI_GUIDE.md"))
        QShortcut(QKeySequence("F1"), self, activated=lambda: self._open_doc("GUI_GUIDE.md"))
        about_btn = QPushButton("Abou&t")
        about_btn.setFlat(True)
        about_btn.clicked.connect(self.about)
        bottom.addWidget(self.adv_btn)
        bottom.addStretch(1)
        bottom.addWidget(help_btn)
        bottom.addWidget(about_btn)
        lay.addLayout(bottom)
        return page

    def _result_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.res_title = label("Done", bold=True, scale=1.45)
        self.res_body = label(selectable=True)
        self.res_files = QLineEdit()
        self.res_files.setReadOnly(True)
        self.res_files.setAccessibleName("Output folder")
        self.res_notice = Notice()
        self.res_next = label(selectable=True)
        for w in (self.res_title, self.res_body, self.res_files, self.res_notice, self.res_next):
            lay.addWidget(w)
        row = QHBoxLayout()
        self.open_btn = PrimaryButton("&Open folder")
        self.open_btn.clicked.connect(self.open_output)
        self.details_btn = QPushButton("View &details")
        self.details_btn.clicked.connect(lambda: self.adv.show_tab("details"))
        self.again_btn = QPushButton("Convert &more saves")
        self.again_btn.clicked.connect(self.back_to_form)
        row.addWidget(self.open_btn)
        row.addWidget(self.details_btn)
        row.addStretch(1)
        row.addWidget(self.again_btn)
        lay.addLayout(row)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------------------------------------- helpers
    def _start_dir(self):
        if self.source:
            return os.path.dirname(self.source["path"])
        return os.path.expanduser("~")

    def target(self):
        if not self.source:
            return None
        return "ps1" if self.source["head"]["platform"] == "pc" else "pc"

    def log(self, text):
        self.adv.log(text)

    def selected_ids(self):
        """None = all saves; else the checked save ids in source order."""
        if not self.source or self.all_radio.isChecked():
            return None
        return [self.save_list.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
                for i in range(self.save_list.topLevelItemCount())
                if self.save_list.topLevelItem(i).checkState(0) == Qt.CheckState.Checked]

    def count_selected(self):
        ids = self.selected_ids()
        return len(self.source["items"]) if ids is None and self.source else len(ids or [])

    # ------------------------------------------------------------------------------------------- source
    def browse_source(self):
        if self.running:
            return
        path = self.ask_open()
        if path:
            self.load_source(path)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and not self.running:
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files and not self.running:
            self.load_source(files[0])

    def load_source(self, path):
        if self.running:
            return
        path = os.path.normpath(path)
        self._src_gen += 1
        gen = self._src_gen
        self.loading = True
        self.stack.setCurrentIndex(0)
        self.src_notice.clear()
        set_text(self.src_summary, f"Reading {os.path.basename(path)}…")
        set_text(self.src_detail, "")
        self.log(f"open {path}")
        self.engine.submit(lambda progress, cancel: batch.scan(path),
                           lambda r: self._source_loaded(gen, path, r), lambda e, tb: self._source_failed(gen, path, e, tb))
        self.refresh()

    def _source_loaded(self, gen, path, result):
        if gen != self._src_gen:
            return
        self.loading = False
        head, items = result
        self.source = {"path": path, "head": head, "items": items}
        self.plan = None
        self.last_result = None
        self.fail_notice.clear()
        self._filling = True
        try:
            self.save_list.clear()
            for it in items:
                row = QTreeWidgetItem([it["label"], it["location"] or "—", str(it["disc"] or "?"),
                                       ", ".join(it["party"]) or "—", it["playtime"], MEMORIA.get(it.get("memoria"), "")])
                row.setData(0, Qt.ItemDataRole.UserRole, it["id"])
                row.setCheckState(0, Qt.CheckState.Checked)
                row.setToolTip(1, f"Story position {it['scenario_counter']}, {it['map']}, {it['gil']:,} gil")
                self.save_list.addTopLevelItem(row)
            for i in range(self.save_list.columnCount()):
                if i != 3:
                    self.save_list.resizeColumnToContents(i)
            self.all_radio.setChecked(True)
            self.new_radio.setChecked(True)
            self.into_pick.set_path("", emit=False)
            self.replace_box.setChecked(False)
        finally:
            self._filling = False
        self.adv.reset()
        self.adv.set_target(self.target())
        n = len(items)
        tgt = self.target()
        if head["platform"] == "ps1":
            what = "PlayStation memory card"
            files = [i["file_no"] for i in items if i["file_no"]]
            nums = f" ({ps1_files(files)})" if files and len(files) == n else ""
            summary = f"{what}: {plural(n, 'Final Fantasy IX save')}{nums}"
        else:
            what = "PC (Steam) save file"
            slots = sorted({i["slot"] for i in items})
            summary = f"{what}: {plural(n, 'save')}" + (f" in slot{'s' if len(slots) > 1 else ''} "
                                                         f"{', '.join(map(str, slots))}" if slots else "")
        set_text(self.src_summary, f"{breakable(os.path.basename(path))} — {summary}")
        bits = []
        if items:
            first, last = min(items, key=_seconds), max(items, key=_seconds)
            bits.append(f"From {first['location'] or '?'} (disc {first['disc'] or '?'}, {first['playtime']}) to "
                        f"{last['location'] or '?'} (disc {last['disc'] or '?'}, {last['playtime']})." if n > 1 else
                        f"{first['location'] or '?'}, disc {first['disc'] or '?'}, play time {first['playtime']}.")
        if head.get("other_saves"):
            bits.append(f"{plural(len(head['other_saves']), 'save')} of other games on the card "
                        f"{'is' if len(head['other_saves']) == 1 else 'are'} left alone.")
        mem = [i for i in items if i.get("memoria") in ("valid", "untimed")]
        if mem:
            bits.append(f"Memoria extra data found for {plural(len(mem), 'save')}; it is used automatically.")
        set_text(self.src_detail, " ".join(bits))
        if not items:
            self.src_notice.show_message("warn", "No Final Fantasy IX saves in this file",
                                         "Choose another memory card or PC save file.")
        self.drop_title.setText(breakable(os.path.basename(path)))
        self.drop_hint.setText("Drag another file here to use it instead")
        self.dir_label.setText(f"They become {PLATFORM[tgt]} saves.")
        if tgt == "pc":
            self.new_radio.setText("Create a &new PC save file")
            self.existing_radio.setText("Add to my &existing PC save")
            self.into_pick.filter = "PC save (SavedData_ww.dat);;All files (*)"
            self.into_pick.start_dir = PC_SAVE_DIR if os.path.isdir(PC_SAVE_DIR) else self._start_dir()
            self.into_pick.edit.setPlaceholderText("Your SavedData_ww.dat")
        else:
            self.new_radio.setText("Create &new memory cards")
            self.existing_radio.setText("Add to an &existing memory card")
            self.into_pick.filter = "Memory cards (*.mcr *.mcd *.srm);;All files (*)"
            self.into_pick.start_dir = self._start_dir()
            self.into_pick.edit.setPlaceholderText("A memory card file (.mcr .mcd .srm)")
        self.list_toggle.setChecked(n <= 1)
        self.log(f"read {head['format']}: {n} save(s)")
        self.schedule_plan()
        self.save_list.setFocus()

    def _source_failed(self, gen, path, e, tb):
        if gen != self._src_gen:
            return
        self.loading = False
        self.source = None
        self.plan = None
        self.save_list.clear()
        set_text(self.src_summary, "")
        set_text(self.src_detail, "")
        msg = service.explain_error(e) or f"unexpected error ({type(e).__name__}: {e})"
        self.src_notice.show_message("error", f"Could not read {os.path.basename(path)}", msg,
                                     detail="" if service.explain_error(e) else tb)
        self.log(f"could not read {path}: {msg}")
        self.drop_title.setText("Drag your save file here")
        self.refresh()

    def _selection_mode_changed(self):
        if self._filling:
            return
        if self.some_radio.isChecked():
            self.list_toggle.setChecked(True)
        self.refresh()
        self.schedule_plan()

    def _list_toggled(self, on):
        self.list_toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.list_toggle.setText("Hide the saves" if on else "Show the saves")
        self.refresh()

    def _item_checked(self, item, col):
        if not self._filling and col == 0 and self.some_radio.isChecked():
            self.schedule_plan()

    def _check_all(self, on):
        self._filling = True
        try:
            for i in range(self.save_list.topLevelItemCount()):
                self.save_list.topLevelItem(i).setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        finally:
            self._filling = False
        self.schedule_plan()

    def leave_out_problems(self):
        """Uncheck every save that cannot be converted, so the rest can be."""
        if not self.plan:
            return
        bad = {a.id for a in self.plan.assignments if a.problem}
        self._filling = True
        try:
            self.some_radio.setChecked(True)
            for i in range(self.save_list.topLevelItemCount()):
                it = self.save_list.topLevelItem(i)
                if it.data(0, Qt.ItemDataRole.UserRole) in bad:
                    it.setCheckState(0, Qt.CheckState.Unchecked)
        finally:
            self._filling = False
        self.list_toggle.setChecked(True)
        self.log(f"left out {', '.join(sorted(bad))}")
        self.schedule_plan()

    # ------------------------------------------------------------------------------------------- destination
    def _dest_mode_changed(self):
        if self._filling:
            return
        self.replace_box.setChecked(False)
        self.refresh()
        self.schedule_plan()
        if self.existing_radio.isChecked() and not self.into_pick.path():
            self.into_pick.edit.setFocus()

    def options(self):
        """BatchOptions for the current choices, or None while something is missing."""
        if not self.source or not self.source["items"]:
            return None
        sel = self.selected_ids()
        if sel is not None and not sel:
            return None
        o = batch.BatchOptions(input=self.source["path"], select=sel)
        stem = os.path.splitext(os.path.basename(self.source["path"]))[0]
        if self.existing_radio.isChecked():
            into = self.into_pick.path()
            if not into:
                return None
            o.into, o.in_place = into, True
        else:
            folder = self.out_pick.path() or default_output_folder()
            if self.target() == "pc":
                o.out = os.path.join(service.unique(os.path.join(folder, f"{stem} (PC save)")), "SavedData_ww.dat")
            else:
                o.out = service.unique(os.path.join(folder, f"{stem} (PS1 memory cards)"))
        self.adv.apply(o)
        o.replace = self.replace_box.isChecked() and self.replace_box.isVisible()
        return o

    # ------------------------------------------------------------------------------------------- planning
    def schedule_plan(self):
        if self._filling:
            return
        self._plan_gen += 1                     # results of earlier choices are dropped
        if self.job is not None and not self.running:
            self.job.cancel.set()
        self.plan = None
        self.plan_error = None
        self.plan_pending = True
        self.plan_timer.start()
        self.refresh()

    def start_plan(self):
        if self.running:
            return
        o = self.options()
        gen = self._plan_gen
        if o is None:
            self.plan_pending = False
            self.refresh()
            return
        self.log(f"check {len(o.select) if o.select is not None else 'all'} save(s) -> "
                 f"{o.into or o.out}{' (in place)' if o.in_place else ''}")
        self.job = self.engine.submit(lambda progress, cancel: batch.prepare(o, progress, cancel),
                                      lambda plan: self._planned(gen, plan), lambda e, tb: self._plan_failed(gen, e, tb),
                                      lambda d, t, w: self._progress(gen, d, t, w), skippable=True)

    def _planned(self, gen, plan):
        if gen != self._plan_gen:
            return
        self.job = None
        self.plan = plan
        self.plan_pending = False
        self.adv.set_plan(plan, self.source["head"] if self.source else None)
        self.log(f"checked: {'ready' if plan.ok else 'problems: ' + '; '.join(plan.blocking())[:300]}")
        self._mark_list(plan)
        self.refresh()

    def _plan_failed(self, gen, e, tb):
        if gen != self._plan_gen or skipped(e) or isinstance(e, safeio.Cancelled):
            return
        self.job = None
        self.plan_pending = False
        self.plan = None
        msg = service.explain_error(e)
        self.plan_error = (msg or f"unexpected error ({type(e).__name__}: {e})", "" if msg else tb)
        self.log(f"cannot convert: {self.plan_error[0]}" + (f"\n{tb}" if not msg else ""))
        self.refresh()

    def _progress(self, gen, done, total, what):
        if gen is not None and gen != self._plan_gen:
            return
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.progress_label.setText(what[:1].upper() + what[1:] + (f"  ({min(done + 1, total)} of {total})"
                                                                     if total > 1 and done < total else ""))

    def _mark_list(self, plan):
        notes = {a.id: a for a in plan.assignments}
        self._filling = True
        try:
            for i in range(self.save_list.topLevelItemCount()):
                it = self.save_list.topLevelItem(i)
                a = notes.get(it.data(0, Qt.ItemDataRole.UserRole))
                base = MEMORIA.get(self.source["items"][i].get("memoria"), "") if self.source else ""
                if a and a.problem:
                    it.setText(5, "⚠ " + PROBLEM.get(a.problem_kind, PROBLEM[None])[0])
                    it.setToolTip(5, a.problem)
                else:
                    it.setText(5, base)
                    it.setToolTip(5, (a.dest_label if a else ""))
        finally:
            self._filling = False

    # ------------------------------------------------------------------------------------------- state -> widgets
    def refresh(self):
        has = bool(self.source and self.source["items"])
        idle = not self.running
        tgt = self.target()
        for w in (self.drop, self.browse_btn, self.all_radio, self.some_radio, self.save_list, self.sel_all,
                  self.sel_none, self.new_radio, self.existing_radio, self.out_pick, self.into_pick, self.place_btn,
                  self.replace_box, self.adv_btn):
            w.setEnabled(idle and not self.loading)
        self.pick_row.setVisible(has)
        listed = has and self.list_toggle.isChecked()
        self.save_list.setVisible(listed)
        choose = self.some_radio.isChecked()
        self.sel_row.setVisible(listed and choose)
        self._filling = True
        try:
            for i in range(self.save_list.topLevelItemCount()):
                it = self.save_list.topLevelItem(i)
                flags = it.flags() | Qt.ItemFlag.ItemIsUserCheckable if choose else \
                    it.flags() & ~Qt.ItemFlag.ItemIsUserCheckable
                it.setFlags(flags)
                if not choose:
                    it.setCheckState(0, Qt.CheckState.Checked)
        finally:
            self._filling = False
        n = self.count_selected()
        if has:
            self.all_radio.setText(f"Convert &all {plural(len(self.source['items']), 'save')}"
                                   if len(self.source["items"]) > 1 else "Convert &this save")
            self.some_radio.setVisible(len(self.source["items"]) > 1)
            self.list_toggle.setVisible(len(self.source["items"]) > 1 or not self.list_toggle.isChecked())
            self.sel_count.setText(f"{n} of {len(self.source['items'])} selected")
        self.s2.setEnabled(has)
        self.dir_label.setVisible(has)
        existing = self.existing_radio.isChecked()
        self.out_row.setVisible(not existing)
        self.into_row.setVisible(existing)
        self.place_btn.setVisible(has)
        if tgt == "pc":
            self.into_hint.setText("The saves already in it are kept, and a backup copy is made first. Your PC "
                                   f"saves are usually in {soft(PC_SAVE_DIR)}")
        else:
            self.into_hint.setText("The saves already on the card are kept, and a backup copy is made first.")
        if self.adv.copy_instead.isChecked():
            self.into_hint.setText("The file itself is not changed: a new copy with the saves added is created "
                                   "next to it (Advanced > Options).")
        self._refresh_plan_texts(has)
        busy = self.running or self.loading or self.plan_pending
        ready = (idle and has and self.plan is not None and self.plan.ok and not self.plan_pending and
                 (not self.plan.replacements or self.replace_box.isChecked()))
        self.convert_btn.setEnabled(bool(ready))
        self.convert_btn.setText("Converting…" if self.running else
                                 (f"&Convert {plural(len(self.plan.assignments), 'save')}" if self.plan else "&Convert"))
        self.convert_btn.setAccessibleName(self.convert_btn.text().replace("&", ""))
        self.cancel_btn.setVisible(self.running or (self.plan_pending and self.job is not None))
        self.cancel_btn.setEnabled(self.job is not None and not self.job.cancel.is_set())
        self.progress_row.setVisible(busy and self.job is not None)

    def _refresh_plan_texts(self, has):
        p = self.plan
        tgt = self.target()
        self.problem_notice.clear()
        self.warn_notice.clear()
        self.replace_box.setVisible(False)
        if not has:
            set_text(self.place_label, "")
            set_text(self.summary, "Start with step 1." if not self.loading else "")
            return
        if self.existing_radio.isChecked() and not self.into_pick.path():
            set_text(self.place_label, "")
            set_text(self.summary, f"Choose your existing {'PC save file' if tgt == 'pc' else 'memory card'} in step 2.")
            return
        if self.count_selected() == 0:
            set_text(self.place_label, "")
            set_text(self.summary, "Tick at least one save in step 1.")
            return
        if self.plan_error:
            set_text(self.place_label, "")
            set_text(self.summary, "")
            self.problem_notice.show_message("error", "These saves cannot be converted with these choices",
                                             self.plan_error[0], detail=self.plan_error[1])
            return
        if p is None:
            set_text(self.place_label, "Working out where the saves go…" if self.plan_pending else "")
            set_text(self.summary, "Checking every save…" if self.plan_pending else "")
            return
        set_text(self.place_label, placement_text(p))
        set_text(self.summary, summary_text(p))
        bad = [a for a in p.assignments if a.problem]
        if bad or p.problems:
            lines = [f"• {a.source_label} {PROBLEM.get(a.problem_kind, PROBLEM[None])[0]}. "
                     f"{PROBLEM.get(a.problem_kind, PROBLEM[None])[1]}" for a in bad[:6]]
            if len(bad) > 6:
                lines.append(f"• … and {len(bad) - 6} more")
            lines += [f"• {_sentence(x)}" for x in p.problems]
            actions = []
            if bad and len(bad) < len(p.assignments):
                actions.append((f"&Leave {'it' if len(bad) == 1 else 'them'} out", self.leave_out_problems))
            if any("interrupted" in x for x in p.problems):
                actions.append(("&Undo the interrupted conversion",
                                lambda: self.recover(os.path.dirname(p.options.into or p.options.out))))
            title = (f"{plural(len(bad), 'save')} cannot be converted" if bad else "Cannot convert yet")
            detail = "\n".join([f"{a.source_label}: {a.problem}" for a in bad] + p.problems)
            self.problem_notice.show_message("error", title, "\n".join(lines), detail=detail, actions=actions)
            return
        notes = [f"{a.source_label}: {a.note}" for a in p.assignments if a.note] + p.warnings
        notes += [f"{a.source_label}: {w}" for a in p.assignments for w in a.warnings]
        lossy = [a for a in p.assignments if (a.report or {}).get("memoria", {}).get("lossy")]
        if lossy:
            notes.insert(0, f"Lossy conversion is on: data the PlayStation cannot hold is dropped from "
                            f"{plural(len(lossy), 'save')} (listed under Advanced > Details).")
        if p.replacements:
            self.warn_notice.show_message(
                "warn", f"{plural(len(p.replacements), 'save')} already there would be replaced",
                "\n".join(f"• {_sentence(r)}" for r in p.replacements[:8]) +
                (f"\n• … and {len(p.replacements) - 8} more" if len(p.replacements) > 8 else ""),
                detail="\n".join(notes))
            self.replace_box.setText(f"&Replace {'it' if len(p.replacements) == 1 else 'them'}" +
                                     (" (a backup copy of the file is made first)" if p.destination == "in-place" else ""))
            self.replace_box.setVisible(True)
        elif notes:
            self.warn_notice.show_message("info", "Good to know", "\n".join(f"• {_sentence(n)}" for n in notes[:6]),
                                          detail="\n".join(notes) if len(notes) > 6 else "")

    # ------------------------------------------------------------------------------------------- convert
    def start_conversion(self):
        if self.running or not self.convert_btn.isEnabled() or self.plan is None:
            return
        plan = self.plan
        if plan.replacements and self.replace_box.isChecked():
            plan.options.replace = True
        self.running = True
        self.fail_notice.clear()
        self.log(f"convert {len(plan.assignments)} save(s)")
        self._progress(None, 0, len(plan.outputs) + 1, "writing")
        self.job = self.engine.submit(lambda progress, cancel: batch.commit(plan, cancel, progress),
                                      self._converted, self._convert_failed, lambda d, t, w: self._progress(None, d, t, w))
        self.refresh()

    def cancel(self):
        if self.job is not None and not self.job.cancel.is_set():
            self.job.cancel.set()
            self.log("cancel requested")
            if not self.running:                # stop checking; any change of a choice checks again
                self._plan_gen += 1
                self.job = None
                self.plan_pending = False
                self.plan_error = ("Checking was cancelled. Change a choice, or choose the file again, to check "
                                   "again.", "")
                self.refresh()
                return
            self.progress_label.setText("Cancelling… (anything already written is put back)")
            self.refresh()

    def _converted(self, r):
        self.running = False
        self.job = None
        self.last_result = r
        plan = r["plan"]
        self.settings.setValue("output_folder", self.out_pick.path())
        self.log("written: " + ", ".join(x["path"] for x in r["outputs"]))
        n = len(plan.assignments)
        self.res_title.setText(f"✔ {plural(n, 'save')} converted and checked")
        lines = []
        for x, out in zip(r["outputs"], plan.outputs):
            saves = [a for a in plan.assignments if a.id in out.saves]
            lines.append(f"{os.path.basename(x['path'])}: {plural(len(saves), 'save')}"
                         + (" added (the saves that were already in it are kept)" if out.replace else ""))
            if x["backup"]:
                lines.append(f"    backup of the previous file: {os.path.basename(x['backup'])}")
        lines.append("")
        lines.append("Every save was read back from the new file and matched its original before it was written.")
        self.res_body.setText("\n".join(lines))
        self.res_files.setText(os.path.dirname(r["outputs"][0]["path"]))
        self.res_notice.clear()
        if plan.direction == "ps1->pc":
            live = os.path.normcase(os.path.abspath(PC_SAVE_DIR)) in os.path.normcase(r["outputs"][0]["path"])
            self.res_next.setText(
                "The PC game sees the saves now. Load them from the game's Load menu." if live else
                "To play: back up your current SavedData_ww.dat, then copy the new SavedData_ww.dat into\n"
                f"{PC_SAVE_DIR}\n(or add the saves straight to your own PC save next time, in step 2). Turn off Steam "
                "Cloud for Final Fantasy IX first, so Steam does not replace the file.")
        else:
            self.res_next.setText(
                "To play in an emulator such as DuckStation: choose the new memory card file as the card for slot 1 "
                "(Settings > Memory Cards), then load the game. On a real PlayStation, copy the card with a memory "
                "card adapter. A list of where every save went is in conversion-manifest.txt."
                if plan.destination == "new" else
                "Use the updated memory card in your emulator as before; the converted saves appear as their FILE "
                "numbers in the game's Load menu.")
        self.stack.setCurrentIndex(1)
        self.open_btn.setFocus()
        self.refresh()
        self.conversion_finished.emit(True)

    def _convert_failed(self, e, tb):
        self.running = False
        self.job = None
        if isinstance(e, safeio.Cancelled):
            self.fail_notice.show_message("info", "Cancelled", "Nothing was changed.")
            self.log("cancelled; nothing changed")
        else:
            msg = service.explain_error(e) or f"unexpected error ({type(e).__name__}: {e})"
            self.fail_notice.show_message("error", "Nothing was converted", msg,
                                          detail="" if service.explain_error(e) else tb)
            self.log(f"not converted: {msg}" + ("" if service.explain_error(e) else f"\n{tb}"))
        self.refresh()
        self.schedule_plan()                    # the destination may have changed meanwhile
        self.conversion_finished.emit(False)

    def back_to_form(self):
        self.stack.setCurrentIndex(0)
        self.last_result = None
        self.schedule_plan()                    # the destination now holds the converted saves

    def open_output(self):
        if self.last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.res_files.text()))

    # ------------------------------------------------------------------------------------------- recovery, help
    def recover(self, folder=None):
        if self.running:
            return
        folder = folder or self.ask_folder("Choose the folder of the interrupted conversion")
        if not folder:
            return
        if not safeio.find_journals(folder):
            self.fail_notice.show_message("info", "Nothing to undo", f"No interrupted conversion was found in {folder}.")
            return
        if not self.confirm("Undo the interrupted conversion?",
                            f"Every file the interrupted conversion changed in\n{folder}\nis put back exactly as it was "
                            "before. Continue?"):
            return
        self.log(f"recover {folder}")
        self.engine.submit(lambda progress, cancel: batch.recover(folder), self._recovered,
                           lambda e, tb: self.fail_notice.show_message("error", "Could not undo it",
                                                                       service.explain_error(e) or str(e), detail=tb))

    def _recovered(self, found):
        problems = [p for _, r in found for p in r["problems"]]
        restored = [p for _, r in found for p in r["restored"]]
        if problems:
            self.fail_notice.show_message("error", "Some files could not be put back", "\n".join(problems))
        else:
            self.fail_notice.show_message("ok", "The interrupted conversion was undone",
                                          f"{plural(len(restored), 'file')} put back as {'it was' if len(restored) == 1 else 'they were'}.")
        self.log(f"recovered: {restored} problems: {problems}")
        self.schedule_plan()

    def _open_doc(self, name):
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else \
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        path = os.path.join(base, name)
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            self.fail_notice.show_message("info", f"{name} was not found next to the program")

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<h3>{APP_NAME} {__version__}</h3>"
                          "<p>Converts Final Fantasy IX saves between PlayStation memory cards and the PC (Steam) "
                          "version, in both directions, one save or a whole collection at a time, with independent "
                          "verification of every converted save.</p>"
                          "<p>Copyright © 2026 thekojac. Released under the MIT License (LICENSE.txt).</p>"
                          "<p>Uses Qt for Python (PySide6) and Qt under the LGPL-3.0, Python (PSF License) and "
                          "cryptography (Apache-2.0/BSD). Save-format knowledge from Memoria (MIT) and "
                          "ffix-save-editor (MIT). Full texts are in THIRD_PARTY_LICENSES and NOTICES.md.</p>"
                          "<p>Final Fantasy IX is © Square Enix. This program is not affiliated with or endorsed "
                          "by Square Enix. It never changes Steam Cloud saves.</p>")

    def closeEvent(self, e):
        if self.running:
            self.cancel()
            self.engine.wait(30000)              # the transaction undoes or finishes; never leave it half-done
        self.adv.close()
        super().closeEvent(e)


# ---- texts built from a plan ---------------------------------------------------------------------------
def breakable(name):
    """Let a long file name wrap after _ - . (display only)."""
    for c in "_-.":
        name = name.replace(c, c + "\u200b")
    return name


def _seconds(item):
    h, m = item["playtime"].split(":")
    return int(h) * 60 + int(m)


def _sentence(text):
    text = str(text)
    return text[:1].upper() + text[1:] + ("" if text.endswith((".", "!", ")")) else ".")


def placement_text(p):
    if not p.outputs:
        return ""
    if p.direction == "ps1->pc":
        slots = {}
        for a in p.assignments:
            if a.slot is not None:
                slots.setdefault(a.slot + 1, []).append(a.file + 1)
        where = "; ".join(f"slot {s}, file{'s' if len(f) > 1 else ''} {file_ranges(f)}" for s, f in sorted(slots.items()))
        kept = (f" The {plural(p.existing, 'save')} already in the file {'is' if p.existing == 1 else 'are'} kept"
                + (" (except the ones replaced, below)." if p.replacements else ".")) if p.existing else ""
        return f"They go into {where}.{kept}"
    if p.outputs[0].kind == "mcs":
        return f"Each save becomes its own single-save file (.mcs): {plural(len(p.outputs), 'file')}."
    parts = []
    for x in p.outputs:
        files = [a.file for a in p.assignments if a.id in x.saves]
        parts.append(f"{os.path.basename(x.path)} ({ps1_files(files)})")
    if p.destination == "new":
        head = (f"They fill {plural(len(p.outputs), 'new memory card')}: " if len(p.outputs) > 1 else
                "They go on one new memory card: ")
        return head + ", ".join(parts) + "."
    kept = f" The {plural(p.existing, 'save')} already on the card {'is' if p.existing == 1 else 'are'} kept." if p.existing else ""
    return f"They go on the memory card as {ps1_files([a.file for a in p.assignments])}.{kept}"


def summary_text(p):
    n = len(p.assignments)
    if not p.outputs:
        return ""
    if p.destination == "in-place":
        where = f"Your file {p.outputs[0].path} is updated (a backup copy is made first)."
    elif p.destination == "copy":
        where = f"A new copy of your file is created: {p.outputs[0].path}"
    elif len(p.outputs) == 1:
        where = f"New file: {p.outputs[0].path}"
    else:
        where = f"New files in {os.path.dirname(p.outputs[0].path)}"
    to = PLATFORM["pc" if p.direction == "ps1->pc" else "ps1"]
    if p.ok:
        return (f"{plural(n, 'save')} will be converted to {to}. All of them were test-converted and read back "
                f"without differences.\n{soft(where)}")
    return f"{plural(n, 'save')} selected for conversion to {to}.\n{soft(where)}"


# ---- layout check (used by the smoke mode and the tests) --------------------------------------------------
def layout_problems(root):
    """Visible controls that are smaller than they need to be (clipped text) or overlap a sibling."""
    out = []
    kinds = (QAbstractButton, QLineEdit, QComboBox, QLabel, QProgressBar)
    widgets = [w for w in root.findChildren(QWidget) if isinstance(w, kinds) and w.isVisibleTo(root)
               and w.window() is root.window()]
    for w in widgets:
        hint = w.minimumSizeHint()
        name = w.objectName() or w.accessibleName() or (w.text() if hasattr(w, "text") else "") or type(w).__name__
        if isinstance(w, QLabel) and w.wordWrap():
            if w.heightForWidth(w.width()) > w.height() + 1 and w.text():
                out.append(f"label cut off: {name[:50]!r} ({w.width()}x{w.height()}, needs {w.heightForWidth(w.width())})")
        elif w.width() + 1 < hint.width() or w.height() + 1 < hint.height():
            out.append(f"{type(w).__name__} {name[:50]!r} is {w.width()}x{w.height()}, needs {hint.width()}x{hint.height()}")
    by_parent = {}
    for w in widgets:
        by_parent.setdefault(w.parentWidget(), []).append(w)
    for ws in by_parent.values():
        for i, a in enumerate(ws):
            for b in ws[i + 1:]:
                ra, rb = a.geometry(), b.geometry()
                if ra.intersects(rb) and not ra.intersected(rb).isEmpty() and not _nested(a, b):
                    inter = ra.intersected(rb)
                    if inter.width() > 2 and inter.height() > 2:
                        out.append(f"overlap: {a.objectName() or type(a).__name__} and {b.objectName() or type(b).__name__}")
    return out


def settle_layout(app, ms=300):
    """Let deferred layout passes (word-wrapped labels re-flowing after a resize) finish before measuring."""
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def _nested(a, b):
    return a.isAncestorOf(b) or b.isAncestorOf(a)


# ---- start-up ------------------------------------------------------------------------------------------
def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def apply_theme(app, theme):
    """Follow Windows (theme None) or force "light"/"dark". If the platform or style does not switch its palette
    (older styles, test platforms), an explicit palette with the same roles is set instead."""
    from PySide6.QtGui import QColor, QPalette
    if theme not in ("light", "dark"):
        return
    if app.style().name().lower() == "windowsvista":     # the classic style cannot draw dark controls
        app.setStyle("fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if theme == "dark" else Qt.ColorScheme.Light)
    app.processEvents()
    dark = app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    if dark == (theme == "dark"):
        return
    if app.style().name().lower() != "fusion":
        app.setStyle("fusion")
    pal = QPalette()
    if theme == "dark":
        c = {"Window": "#202020", "WindowText": "#ffffff", "Base": "#2b2b2b", "AlternateBase": "#323232",
             "Text": "#ffffff", "Button": "#2d2d2d", "ButtonText": "#ffffff", "Highlight": "#7a5af8",
             "HighlightedText": "#ffffff", "ToolTipBase": "#2b2b2b", "ToolTipText": "#ffffff", "Mid": "#5a5a5a",
             "PlaceholderText": "#b4b4b4", "Light": "#3c3c3c", "Midlight": "#353535", "Dark": "#151515",
             "Accent": "#9b7bff"}
    else:
        c = {"Window": "#f3f3f3", "WindowText": "#1a1a1a", "Base": "#ffffff", "AlternateBase": "#f7f7f7",
             "Text": "#1a1a1a", "Button": "#fbfbfb", "ButtonText": "#1a1a1a", "Highlight": "#7a3fb0",
             "HighlightedText": "#ffffff", "ToolTipBase": "#ffffff", "ToolTipText": "#1a1a1a", "Mid": "#a0a0a0",
             "PlaceholderText": "#5f5f5f", "Light": "#ffffff", "Midlight": "#e5e5e5", "Dark": "#8a8a8a",
             "Accent": "#7a3fb0"}
    for role, col in c.items():
        if hasattr(QPalette.ColorRole, role):
            pal.setColor(getattr(QPalette.ColorRole, role), QColor(col))
    app.setPalette(pal)


def make_app(argv):
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ffix.saveconverter")
        except (AttributeError, OSError):
            pass
    app = QApplication.instance() or QApplication(argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(icon.app_icon())
    theme = _arg(argv, "--theme")
    if theme in ("light", "dark"):
        apply_theme(app, theme)
    elif app.styleHints().colorScheme() == Qt.ColorScheme.Dark and app.style().name().lower() == "windowsvista":
        app.setStyle("fusion")
    return app


def _size(app, argv):
    s = _arg(argv, "--size")
    if s and "x" in s:
        w, h = (int(x) for x in s.lower().split("x"))
        return w, h
    return initial_size(app)


def wait_idle(app, win, timeout_ms=120000):
    """Process events until nothing is loading, planning or converting."""
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < timeout_ms:
        app.processEvents()
        if not (win.loading or win.plan_pending or win.running or win.plan_timer.isActive() or win.engine.busy()):
            app.processEvents()
            if not (win.loading or win.plan_pending or win.running or win.engine.busy()):
                return True
        win.engine.wait(20)
    return False


def automate(argv):
    """Drive the real window from a JSON job: the same widgets a user fills and the same button.

    job: {"source": path, "select": [ids] (optional), "dest": "new"|"existing", "into": path, "out_folder": path,
          "replace": bool, "leave_out_problems": bool, "advanced": {"pc_slot": n, "layout": s, "format": s,
          "lossy": bool, "lenient": bool, "copy_instead": bool}, "cancel": bool, "screenshot": png path,
          "result": path, "settings": ini path}"""
    with open(_arg(argv, "--automate"), encoding="utf-8") as f:
        job = json.load(f)
    app = make_app(argv)
    settings = QSettings(job.get("settings") or os.path.join(os.path.dirname(os.path.abspath(job["result"])),
                                                             "automation.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.resize(*_size(app, argv))
    win.show()
    out = {"ok": False}
    try:
        if job.get("out_folder"):
            win.out_pick.set_path(job["out_folder"])
        win.load_source(job["source"])
        wait_idle(app, win)
        out["source_summary"] = win.src_summary.text()
        if job.get("select") is not None:
            win.some_radio.setChecked(True)
            want = {str(x) for x in job["select"]}
            for i in range(win.save_list.topLevelItemCount()):
                it = win.save_list.topLevelItem(i)
                it.setCheckState(0, Qt.CheckState.Checked if it.data(0, Qt.ItemDataRole.UserRole) in want
                                 else Qt.CheckState.Unchecked)
        adv = job.get("advanced") or {}
        if "pc_slot" in adv:
            win.adv.pc_slot.setCurrentIndex(win.adv.pc_slot.findData(adv["pc_slot"]))
        for key, box in (("layout", win.adv.layout_box), ("format", win.adv.format_box)):
            if key in adv:
                box.setCurrentIndex(box.findData(adv[key]))
        for key, box in (("lossy", win.adv.lossy), ("lenient", win.adv.lenient), ("copy_instead", win.adv.copy_instead)):
            if key in adv:
                box.setChecked(bool(adv[key]))
        if job.get("dest") == "existing":
            win.existing_radio.setChecked(True)
            win.into_pick.set_path(job["into"])
        wait_idle(app, win)
        if job.get("leave_out_problems") and win.plan and not win.plan.ok:
            win.leave_out_problems()
            wait_idle(app, win)
        if job.get("replace") and win.replace_box.isVisible():
            win.replace_box.setChecked(True)
        settle_layout(app)
        p = win.plan
        out.update(placement=win.place_label.text(), summary=win.summary.text(),
                   problems=win.problem_notice.body.text() if win.problem_notice.isVisible() else "",
                   warnings=win.warn_notice.body.text() if win.warn_notice.isVisible() else "",
                   convert_enabled=win.convert_btn.isEnabled(), convert_text=win.convert_btn.text(),
                   plan=None if not p else {"ok": p.ok, "saves": [[a.id, a.dest_label] for a in p.assignments],
                                            "outputs": [x.path for x in p.outputs]},
                   layout_problems=layout_problems(win))
        if job.get("screenshot"):
            win.grab().save(job["screenshot"])
        if win.convert_btn.isEnabled():
            if job.get("cancel"):
                win.engine.submit(lambda progress, cancel: __import__("time").sleep(0.3))   # hold the worker
                win.convert_btn.click()
                win.cancel()
            else:
                win.convert_btn.click()
            wait_idle(app, win)
        out["page"] = "result" if win.stack.currentIndex() == 1 else "form"
        out["result_title"] = win.res_title.text() if out["page"] == "result" else win.fail_notice.title.text()
        out["result_text"] = win.res_body.text() if out["page"] == "result" else win.fail_notice.body.text()
        if win.last_result:
            out.update(ok=True, outputs=[x["path"] for x in win.last_result["outputs"]],
                       backups=[x["backup"] for x in win.last_result["outputs"]],
                       report=win.last_result["report_path"])
            if job.get("screenshot"):
                win.grab().save(os.path.splitext(job["screenshot"])[0] + "-result.png")
    except Exception as e:
        out["exception"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()
    finally:
        win.close()
        app.processEvents()
    with open(job["result"], "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return 0 if out.get("ok") else 1


def smoke(argv):
    """Open the window (optionally with a file), let it settle, capture it and report what it shows."""
    result = _arg(argv, "--smoke")
    app = make_app(argv)
    settings = QSettings(os.path.join(os.path.dirname(os.path.abspath(result)), "smoke.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    win.resize(*_size(app, argv))
    win.show()
    files = [a for a in argv[1:] if not a.startswith("--") and a not in (result, _arg(argv, "--theme"), _arg(argv, "--size"))]
    if files:
        win.load_source(files[0])
    wait_idle(app, win)
    win.list_toggle.setChecked(True)
    settle_layout(app)
    info = {"title": win.windowTitle(), "visible": win.isVisible(), "frozen": bool(getattr(sys, "frozen", False)),
            "dpr": win.devicePixelRatioF(), "style": app.style().name(),
            "color_scheme": str(app.styleHints().colorScheme()), "dark": win.palette().window().color().lightness() < 128,
            "size": [win.width(), win.height()], "summary": win.src_summary.text(),
            "convert_enabled": win.convert_btn.isEnabled(), "convert_text": win.convert_btn.text(),
            "layout_problems": layout_problems(win)}
    win.grab().save(os.path.splitext(result)[0] + ".png")
    win.close()
    with open(result, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    return 0


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if "--automate" in argv:
        return automate(argv)
    if "--smoke" in argv:
        return smoke(argv)
    app = make_app(argv)
    ini = _arg(argv, "--settings")
    win = MainWindow(settings=QSettings(ini, QSettings.Format.IniFormat) if ini else None)
    if _arg(argv, "--out-folder"):
        win.out_pick.set_path(_arg(argv, "--out-folder"), emit=False)
    win.resize(*_size(app, argv))
    win.show()
    skip = {_arg(argv, x) for x in ("--theme", "--size", "--settings", "--out-folder")}
    files = [a for a in argv[1:] if not a.startswith("-") and a not in skip]
    if files:
        win.load_source(files[0])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
