"""Advanced: everything a normal conversion does not need.

  Placement   choose where each save goes (PC slot/file or memory card/FILE), PC slot, card layout, format, region
  Options     lossy Memoria conversion, damaged PS1 saves, write a copy instead of updating an existing file
  Details     what was checked for every save: verification, platform differences, Memoria data, file formats
  Log         what the window did, with times (copy it when reporting a problem)
  Recovery    undo a conversion that was interrupted (power cut, crash)
"""
import datetime
import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from .messages import MEMORIA, PROBLEM
from .widgets import label

SECTIONS = [("warnings", "Warnings"), ("conversion_blocking", "Blocking"), ("unsupported_or_lossy", "Not carried over"),
            ("defaulted", "Defaulted"), ("safely_transformed", "Transformed"), ("fully_preserved", "Preserved")]


class AdvancedDialog(QDialog):
    changed = Signal()                  # an option that changes the conversion was changed
    recover_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced")
        self.resize(720, 520)
        self.target = None
        self._filling = False
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Advanced sections")
        lay.addWidget(self.tabs)
        self.tabs.addTab(self._placement(), "&Placement")
        self.tabs.addTab(self._options(), "&Options")
        self.details = QTextBrowser()
        self.details.setAccessibleName("Details of the conversion")
        self.details.setOpenExternalLinks(False)
        self.tabs.addTab(self.details, "&Details")
        self.tabs.addTab(self._log(), "&Log")
        self.tabs.addTab(self._recovery(), "&Recovery")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.hide)
        lay.addWidget(bb)

    # -- tabs
    def _placement(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.manual = QCheckBox("Choose &myself where each save goes")
        self.manual.toggled.connect(self._manual_toggled)
        lay.addWidget(self.manual)
        self.map_hint = label(muted=True)
        lay.addWidget(self.map_hint)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Save", "What it is", "Goes to"])
        self.table.setAccessibleName("Where each save goes")
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._cell_changed)
        lay.addWidget(self.table, 1)
        form = QFormLayout()
        self.pc_slot = QComboBox()
        self.pc_slot.addItem("Automatic (first empty slot)", None)
        for s in range(1, 11):
            self.pc_slot.addItem(f"Slot {s}", s)
        self.pc_slot.setAccessibleName("PC slot for the saves")
        self.layout_box = QComboBox()
        self.layout_box.addItem("Automatic", "auto")
        self.layout_box.addItem("One memory card per PC slot, keep file numbers", "by-slot")
        self.layout_box.addItem("As few memory cards as possible", "compact")
        self.layout_box.setAccessibleName("How saves are put on memory cards")
        self.format_box = QComboBox()
        self.format_box.addItem("Memory cards (.mcr)", "card")
        self.format_box.addItem("One single-save file per save (.mcs)", "mcs")
        self.format_box.setAccessibleName("PlayStation file format")
        self.region = QComboBox()
        self.region.addItem("North America (NTSC-U)", "NTSC-U")
        self.region.addItem("Europe (PAL)", "PAL")
        self.region.setAccessibleName("PlayStation region")
        self.lab_slot = label("PC &slot:", wrap=False)
        self.lab_layout = label("&Memory cards:", wrap=False)
        self.lab_format = label("&File format:", wrap=False)
        self.lab_region = label("Re&gion:", wrap=False)
        for lab, box in ((self.lab_slot, self.pc_slot), (self.lab_layout, self.layout_box),
                         (self.lab_format, self.format_box), (self.lab_region, self.region)):
            lab.setBuddy(box)
            form.addRow(lab, box)
            box.currentIndexChanged.connect(lambda *_: self._emit())
        lay.addLayout(form)
        return w

    def _options(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.lossy = QCheckBox("Allow &lossy conversion of Memoria/Moguri saves")
        self.lossy.setAccessibleDescription("Off: a save with mod data the PlayStation cannot hold is refused.")
        lay.addWidget(self.lossy)
        lay.addWidget(label("Drops or clamps what the PlayStation version cannot hold (mod items, raised limits, mod "
                            "story data) instead of refusing the save. Every change is listed in the report. Also "
                            "converts a save whose Memoria data file is damaged, without that file.", muted=True))
        self.lenient = QCheckBox("Convert PlayStation saves even if they look &damaged")
        lay.addWidget(self.lenient)
        lay.addWidget(label("For saves whose checksum does not match, or with names the converter cannot read "
                            "completely. Keep this off unless you know the save works on the PlayStation.", muted=True))
        self.copy_instead = QCheckBox("When adding to an existing file, write a &new copy instead of updating it")
        lay.addWidget(self.copy_instead)
        lay.addWidget(label("The existing file is then not changed at all; the copy is created next to it.",
                            muted=True))
        for c in (self.lossy, self.lenient, self.copy_instead):
            c.toggled.connect(lambda *_: self._emit())
        lay.addStretch(1)
        return w

    def _log(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setAccessibleName("Log")
        lay.addWidget(self.log_view)
        b = QPushButton("&Copy log")
        b.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.log_view.toPlainText()))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(b)
        lay.addLayout(row)
        return w

    def _recovery(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(label("If the computer lost power or the program was closed while it was writing, the "
                            "destination folder holds a small record (.ffix-journal-…json) of the interrupted "
                            "conversion. Choose that folder to put every file back exactly as it was before. The "
                            "converter also tells you when it finds such a record."))
        self.recover_btn = QPushButton("&Undo an interrupted conversion…")
        self.recover_btn.clicked.connect(self.recover_requested.emit)
        row = QHBoxLayout()
        row.addWidget(self.recover_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    # -- behaviour
    def _emit(self):
        if not self._filling:
            self.changed.emit()

    def show_tab(self, name):
        names = ["placement", "options", "details", "log", "recovery"]
        self.tabs.setCurrentIndex(names.index(name))
        self.show()
        self.raise_()
        self.activateWindow()

    def log(self, text):
        self.log_view.appendPlainText(f"{datetime.datetime.now():%H:%M:%S}  {text}")

    def set_target(self, target):
        self.target = target
        pc, ps1 = target == "pc", target == "ps1"
        for w in (self.pc_slot, self.lab_slot):
            w.setVisible(pc)
        for w in (self.layout_box, self.lab_layout, self.format_box, self.lab_format, self.region, self.lab_region):
            w.setVisible(ps1)
        self.lossy.setEnabled(ps1)
        self.lenient.setEnabled(pc)
        self.map_hint.setText("Type SLOT/FILE for each save, for example 2/5 for slot 2, file 5." if pc else
                              "Type CARD/FILE for each save, for example 1/3 for card 1, FILE03. With an existing "
                              "memory card, the card is always 1." if ps1 else "")

    def reset(self):
        self._filling = True
        try:
            self.manual.setChecked(False)
            self.table.setRowCount(0)
            self.pc_slot.setCurrentIndex(0)
            self.layout_box.setCurrentIndex(0)
            self.format_box.setCurrentIndex(0)
            self.lossy.setChecked(False)
            self.lenient.setChecked(False)
        finally:
            self._filling = False

    def _manual_toggled(self, on):
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers if on else
                                   QAbstractItemView.EditTrigger.NoEditTriggers)
        self._emit()

    def _cell_changed(self, item):
        if item.column() == 2 and self.manual.isChecked():
            self._emit()

    def mapping(self):
        if not self.manual.isChecked():
            return None
        out = {}
        for r in range(self.table.rowCount()):
            sid = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            out[sid] = self.table.item(r, 2).text().strip()
        return out

    def apply(self, o):
        """Copy the advanced choices into BatchOptions o."""
        o.mapping = self.mapping()
        if self.target == "pc":
            o.pc_slot = self.pc_slot.currentData()
            o.lenient = self.lenient.isChecked()
        else:
            o.layout = self.layout_box.currentData()
            o.format = self.format_box.currentData()
            o.region = self.region.currentData()
            o.allow_lossy = self.lossy.isChecked()
        if o.into and self.copy_instead.isChecked():
            o.in_place = False
        return o

    def set_plan(self, plan, head):
        """Show where the current plan puts every save (and keep the user's own entries while they edit)."""
        self._filling = True
        try:
            keep = self.mapping() or {}
            self.table.setRowCount(len(plan.assignments) if plan else 0)
            for r, a in enumerate(plan.assignments if plan else []):
                s = a.summary
                it = QTableWidgetItem(a.source_label)
                it.setData(Qt.ItemDataRole.UserRole, a.id)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                what = QTableWidgetItem(f"{s['location'] or '—'}, {s['playtime']}")
                what.setFlags(what.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, 0, it)
                self.table.setItem(r, 1, what)
                self.table.setItem(r, 2, QTableWidgetItem(keep.get(a.id) or _place_text(a, plan)))
            self.table.resizeColumnToContents(0)
        finally:
            self._filling = False
        self.details.setHtml(details_html(plan, head))


def _place_text(a, plan):
    if a.slot is not None and plan.direction == "ps1->pc":
        return f"{a.slot + 1}/{a.file + 1}"
    if plan.direction == "pc->ps1" and a.file:
        return f"{a.card or 1}/{a.file}"
    return ""


def details_html(plan, head):
    e = lambda x: html.escape(str(x))
    if plan is None:
        return "<p>Choose saves to see the details of their conversion.</p>"
    p = [f"<h3>{e(plan.direction.upper().replace('->', ' → '))}: {len(plan.assignments)} save(s)</h3>",
         f"<p><b>Source</b> {e(plan.source['path'])}<br>Format: {e((head or {}).get('format', plan.source['format']))}"
         f"<br><small>SHA-256 {e(plan.source['sha256'])}</small></p>"]
    if (head or {}).get("other_saves"):
        p.append(f"<p>Other games on this card (never touched): {e(', '.join(head['other_saves']))}</p>")
    for x in plan.outputs:
        p.append(f"<p><b>Output</b> {e(x.path)}<br>{'updates the existing file (verified backup first)' if x.replace else 'new file'}"
                 + (f", based on {e(x.based_on)}" if x.based_on and not x.replace else "")
                 + (f"<br><small>SHA-256 {e(x.sha256)}</small>" if x.sha256 else "") + "</p>")
    for w in plan.warnings + plan.replacements:
        p.append(f"<p>⚠ {e(w)}</p>")
    for b in plan.problems:
        p.append(f"<p><b>✖ {e(b)}</b></p>")
    for a in plan.assignments:
        c = a.counts
        p.append(f"<h4>{e(a.source_label)} → {e(a.dest_label or '?')}</h4><p>{e(a.summary['location'])}, disc "
                 f"{e(a.summary['disc'] or '?')}, {e(a.summary['playtime'])}, {e(', '.join(a.summary['party']))}")
        if c:
            p.append(f"<br>Checked by reading the converted copy back: {c['equal']} fields equal, {c['normalized']} "
                     f"documented platform differences, <b>{c['unexpected']} unexpected</b>")
        if a.memoria != "none":
            p.append(f"<br>Memoria data: {e(MEMORIA.get(a.memoria) or a.memoria)}")
        if a.note:
            p.append(f"<br>Note: {e(a.note)}")
        if a.problem:
            p.append(f"<br><b>✖ {e(PROBLEM.get(a.problem_kind, PROBLEM[None])[0])}:</b> {e(a.problem)}")
        p.append("</p>")
        mem = (a.report or {}).get("memoria") or {}
        for key, title in (("taken_from_sidecar", "Taken from the Memoria data"), ("dropped_memoria_only", "Memoria-only, not carried over"),
                           ("lossy", "Changed by lossy conversion"), ("notes", "Memoria notes")):
            if mem.get(key):
                p.append(f"<p><i>{e(title)}</i></p><ul>" + "".join(f"<li>{e(i)}</li>" for i in mem[key]) + "</ul>")
        comp = (a.report or {}).get("compatibility") or {}
        for key, title in SECTIONS:
            items = comp.get(key) or []
            if items and key != "fully_preserved":
                p.append(f"<p><i>{e(title)} ({len(items)})</i></p><ul>" + "".join(f"<li>{e(i)}</li>" for i in items)
                         + "</ul>")
        diff = [f for f in ((a.report or {}).get("verification") or {}).get("findings", []) if f["status"] != "equal"]
        if diff:
            p.append("<table border='1' cellspacing='0' cellpadding='3'><tr><th>Field</th><th>Status</th><th>Source</th>"
                     "<th>Converted</th><th>Note</th></tr>" + "".join(
                         f"<tr><td>{e(f['field'])}</td><td>{e(f['status'])}</td><td>{e(f['source'])}</td>"
                         f"<td>{e(f['converted'])}</td><td>{e(f.get('note') or '')}</td></tr>" for f in diff) + "</table>")
    return "".join(p)
