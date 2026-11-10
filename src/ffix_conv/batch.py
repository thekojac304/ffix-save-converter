"""Batch conversion: many saves in one all-or-nothing operation (PS1 card -> PC container, PC container -> PS1 cards).

Two calls, used by both the command line and the GUI:

  plan = prepare(BatchOptions(...))   reads, converts and verifies everything in memory; writes nothing
  result = commit(plan)               writes every output in one safeio.Transaction (all files or none)

prepare() does, in order: parse every selected save (with its Memoria sidecar, judged per save), convert each one,
work out where each goes, look for occupied places and Memoria sidecars that would load over a converted save,
build every output file, then re-parse each output and verify every converted save in it field by field, and
check that every other save in an existing destination is byte-for-byte unchanged. Anything that stops the batch
is listed in plan.problems (whole batch) or in an assignment's `problem` (one save); commit() refuses unless there
are none, and refuses replacing occupied places unless the options approve it (`replace`).

Numbering: PS1 directory blocks (1-15, where a save sits on the card) are not FILE numbers. FF9 names each save
"...-NN" with NN = its in-game FILE number - 1, and the menus show FILE01-FILE15; FILE numbers are what is preserved.
PC places are slot (1-10) / file (1-15). A PS1 card holds 15 one-block FF9 saves, a PC slot holds 15 files, so a
full card maps onto one PC slot and one PC slot onto one card.
"""
import dataclasses
import json
import os
import time

from . import (__version__, convert, memoria, model, pc_container, ps1_card, ps1_save, ps1_writer, safeio, service,
               verify)

CARD_FILES = 15
MANIFEST = "conversion-manifest"


class Cancelled(safeio.Cancelled):
    pass


@dataclasses.dataclass
class BatchOptions:
    input: str
    select: list = None          # save ids as service.list_saves shows them ("3" = PS1 block 3, "2/5" = PC slot 2 file 5)
    into: str = None             # an existing destination: PC SavedData_ww.dat, or a raw 128 KB PS1 card
    in_place: bool = False       # update `into` itself (a verified backup is made first); else a new copy is written
    out: str = None              # PS1->PC: output file. PC->PS1: output folder for new cards, or output card with `into`
    replace: bool = False        # approve replacing the occupied places listed in plan.replacements
    mapping: dict = None         # manual placement {save id: "SLOT/FILE"} (to PC) or {save id: "CARD/FILE"} (to PS1)
    pc_slot: int = None          # to PC: put the saves in this slot (1-10) instead of choosing one
    layout: str = "auto"         # to PS1: "auto" (one PC slot: FILE numbers kept; several: "compact"),
                                 # "by-slot" (one card per PC slot, FILE numbers kept) or "compact" (as few cards as
                                 # possible, FILE01 upwards in source order)
    region: str = "NTSC-U"       # to PS1
    format: str = "card"         # to PS1: "card" (128 KB memory cards) or "mcs" (one single-save .mcs file per save)
    allow_lossy: bool = False    # Memoria -> PS1: drop/clamp modded values instead of refusing
    lenient: bool = False        # PS1 -> PC: accept checksum/region/name problems as warnings
    timestamp: float = None      # PC save time stamps (default: now)
    card_name: str = "FFIX-PS1-Card"


@dataclasses.dataclass
class Assignment:
    id: str                      # source save id
    source_label: str            # "FILE03" / "Slot 2, file 5"
    summary: dict                # service.describe() of the save
    output: int = None           # index into plan.outputs
    dest_label: str = ""         # "Slot 1, file 3" / "Card 01, FILE03"
    slot: int = None             # PC destination, 0-based
    file: int = None             # PC file (0-based) or PS1 FILE number (1-15)
    card: int = None             # PS1 destination card number (1-based)
    replaces: dict = None        # the save that is in the destination place now
    note: str = None             # placement remark (renumbered, shares a slot ...)
    problem: str = None          # why this save cannot be converted (blocks the batch)
    problem_kind: str = None     # checksum, mod-data, memoria-damaged, memoria-overlay, convert, verify, no-room
    memoria: str = "none"        # sidecar status of a PC source save
    warnings: list = dataclasses.field(default_factory=list)
    counts: dict = None
    report: dict = None
    model: dict = dataclasses.field(default=None, repr=False)
    payload: object = dataclasses.field(default=None, repr=False)   # PC slot tree + preview, or PS1 block

    def as_dict(self):
        return {"source": self.id, "source_label": self.source_label, "summary": self.summary,
                "destination": self.dest_label, "replaces": self.replaces, "note": self.note, "problem": self.problem,
                "problem_kind": self.problem_kind,
                "memoria": self.memoria, "warnings": self.warnings, "verification": self.counts,
                "compatibility": (self.report or {}).get("compatibility"), "memoria_details": (self.report or {}).get("memoria")}


@dataclasses.dataclass
class Output:
    path: str
    label: str                   # "SavedData_ww.dat" / "Card 01"
    platform: str
    kind: str = "card"           # PS1 outputs: "card" or "mcs"
    based_on: str = None         # existing file this output starts from (None = new)
    replace: bool = False        # the output path exists and is replaced (in-place update)
    expected_sha256: str = None
    base_raw: bytes = dataclasses.field(default=None, repr=False)
    data: bytes = dataclasses.field(default=None, repr=False)
    sha256: str = None
    saves: list = dataclasses.field(default_factory=list)   # assignment ids


@dataclasses.dataclass
class Plan:
    options: BatchOptions
    direction: str               # "ps1->pc" / "pc->ps1"
    source: dict                 # {"path", "platform", "format", "sha256", "count"}
    assignments: list
    outputs: list
    problems: list               # whole-batch problems
    warnings: list
    replacements: list           # plain descriptions of places that would be replaced
    report_path: str = None
    manifest_text_path: str = None
    destination: str = "new"     # "new", "copy" (a new copy of `into`), "in-place"
    existing: int = 0            # saves already in the destination file (they are kept unless replaced)

    @property
    def ok(self):
        return not self.problems and not any(a.problem for a in self.assignments) and bool(self.outputs)

    @property
    def needs_approval(self):
        return bool(self.replacements) and not self.options.replace

    def blocking(self):
        """Every reason the batch cannot be written as it is, in plain words."""
        out = list(self.problems)
        out += [f"{a.source_label}: {a.problem}" for a in self.assignments if a.problem]
        return out

    def manifest(self, results=None):
        res = {r["path"]: r for r in (results or [])}
        o = self.options
        return {
            "tool": f"ffix-convert {__version__}", "kind": "batch", "direction": self.direction,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input": {"file": os.path.abspath(o.input), "sha256": self.source["sha256"], "format": self.source["format"],
                      "saves_selected": len(self.assignments)},
            "destination": self.destination,
            "outputs": [{"file": x.path, "label": x.label, "sha256": x.sha256, "based_on": x.based_on or "new file",
                         "replaced_existing_file": x.replace,
                         "backup_of_replaced_file": (res.get(x.path) or {}).get("backup"), "saves": x.saves}
                        for x in self.outputs],
            "saves": [a.as_dict() for a in self.assignments],
            "warnings": self.warnings,
            "options": {"layout": o.layout, "format": o.format, "region": o.region, "allow_lossy": o.allow_lossy, "lenient": o.lenient,
                        "replace_approved": o.replace, "manual_mapping": o.mapping or None, "pc_slot": o.pc_slot},
        }


# ---- reading the source -------------------------------------------------------------------------
def scan(path):
    """The saves of a file, for listing: (head, items). Each item is a service.list_saves row plus "label"
    (as the game shows it), "file_no" (PS1 FILE number, or PC file 1-15) and "slot" (PC slot 1-10 or None)."""
    head, rows = service.list_saves(path)
    items = []
    for r in rows:
        if head["platform"] == "pc":
            s, f = (int(x) for x in r["id"].split("/"))
            items.append({**r, "label": f"Slot {s}, file {f}", "slot": s, "file_no": f})
        else:
            n = service.ps1_file_number(r.get("file") or "")
            items.append({**r, "label": f"FILE{n:02d}" if n else f"Block {r['id']}", "slot": None, "file_no": n})
    return head, items


def _check_cancel(cancel):
    if cancel and cancel():
        raise Cancelled("cancelled; nothing was written")


def _selected(all_ids, select):
    if select is None:
        return list(all_ids)
    want = [str(x).strip() for x in select]
    unknown = [x for x in want if x not in all_ids]
    if unknown:
        raise service.UserError(f"no save {', '.join(unknown)} in this file; it holds: {', '.join(all_ids) or 'none'}")
    if len(set(want)) != len(want):
        raise service.UserError("a save is selected twice")
    return [x for x in all_ids if x in want]        # source order, whatever order they were given in


def _journal_problem(folder):
    j = safeio.find_journals(folder)
    if j:
        return (f"an earlier conversion into {folder} was interrupted and has not been undone yet ({os.path.basename(j[0])}). "
                "Recover it first (Advanced > Recover, or: ffix-convert recover \"" + folder + "\")")
    return None


# ---- planning -----------------------------------------------------------------------------------
def prepare(o, progress=None, cancel=None):
    """Build and verify the whole batch in memory. Returns a Plan; writes nothing."""
    progress = progress or (lambda done, total, text: None)
    plat, obj, raw_in = service.load_any(o.input)
    src = {"path": os.path.abspath(o.input), "platform": plat, "sha256": safeio.sha256(raw_in)}
    if plat == "pc":
        ids = [f"{s + 1}/{f + 1}" for s, f in obj.occupied()]
        src["format"] = "PC SavedData_ww.dat"
    else:
        kind, ff9, others = obj
        ids = [str(e.block_index) for e in ff9]
        src["format"] = f"PS1 {kind}"
    if not ids:
        raise service.UserError(f"{os.path.basename(o.input)} holds no Final Fantasy IX saves")
    sel = _selected(ids, o.select)
    if not sel:
        raise service.UserError("no saves selected")
    src["count"] = len(ids)
    if o.layout not in ("auto", "by-slot", "compact"):
        raise service.UserError("layout must be auto, by-slot or compact")
    if o.in_place and not o.into:
        raise service.UserError("updating a file in place needs the destination file (--into)")
    if o.into:
        safeio.check_distinct(o.into, o.input)
    if plat == "ps1":
        plan = _prepare_to_pc(o, obj, sel, src, progress, cancel)
    else:
        plan = _prepare_to_ps1(o, obj, sel, src, progress, cancel)
    for x in plan.outputs:
        service.refuse_cloud_target(x.path)
        if os.path.lexists(x.path) and not x.replace:
            plan.problems.append(f"{x.path} already exists; choose a new name or folder (existing files are only "
                                 "changed when you add saves to them)")
        folder = os.path.dirname(x.path)
        jp = _journal_problem(folder) if os.path.isdir(folder) else None
        if jp and jp not in plan.problems:
            plan.problems.append(jp)
    if plan.report_path:
        service.refuse_cloud_target(plan.report_path)
    if not any(a.problem for a in plan.assignments) and not plan.problems:
        _build_outputs(plan, progress, cancel)
    progress(len(plan.assignments), len(plan.assignments), "checked")
    return plan


def _source_models(o, obj, sel, progress, cancel, to_pc):
    """[(id, Assignment)] with the source model of every selected save; a save that cannot be read gets a problem."""
    out = []
    for i, sid in enumerate(sel):
        _check_cancel(cancel)
        if to_pc:
            kind, ff9, _ = obj
            e = next(x for x in ff9 if str(x.block_index) == sid)
            sv, m, location = service.ps1_source(e)
            n = service.ps1_file_number(e.filename)
            a = Assignment(sid, f"FILE{n:02d}" if n else f"Block {sid}", service.describe(m, location), model=m)
            a.file = n
            if not sv.crc_ok and not o.lenient:
                a.problem_kind = "checksum"
                a.problem = ("the save's checksum does not match, so it may be damaged (the PlayStation would show it "
                             "as corrupted). Leave it out, or allow it under Advanced")
        else:
            s, f = (int(x) - 1 for x in sid.split("/"))
            progress(i, len(sel), f"reading slot {s + 1}, file {f + 1}")
            m, rec, location = service.pc_source(o.input, obj, s, f, o.allow_lossy)
            a = Assignment(sid, f"Slot {s + 1}, file {f + 1}", service.describe(m, location), model=m)
            a.slot, a.file, a.memoria = s, f + 1, rec.status
            a.payload = rec
            if rec.blocking:
                a.problem_kind = "memoria-damaged" if rec.status == "corrupt" else "mod-data"
                a.problem = "; ".join(rec.blocking)
        progress(i, len(sel), f"read {a.source_label}")
        out.append(a)
    return out


def _destination(o, platform):
    """(raw bytes or None, Container/card kind) of the `into` file, checked to be the right kind."""
    if not o.into:
        return None
    plat, obj, raw = service.load_any(o.into)
    if plat != platform:
        what = {"pc": "a PC save file (SavedData_ww.dat)", "ps1": "a PS1 memory card"}
        raise service.UserError(f"{os.path.basename(o.into)} is {what[plat]}, but these saves are converted to "
                                f"{what[platform]}")
    if platform == "ps1" and obj[0] != "raw-card":
        raise service.UserError(f"{os.path.basename(o.into)} is a {obj[0]} file; saves can be added only to a raw "
                                "128 KB memory card (.mcr/.mcd/.srm)")
    return raw


def _parse_map(text, what, hi_a, hi_b):
    try:
        a, b = (int(x) for x in str(text).split("/"))
    except ValueError:
        raise service.UserError(f"{what} must look like N/M (e.g. 2/5), got {text!r}")
    if not (1 <= a <= hi_a and 1 <= b <= hi_b):
        raise service.UserError(f"{what} {text} out of range")
    return a, b


# ---- PS1 card -> PC container -------------------------------------------------------------------
def _prepare_to_pc(o, obj, sel, src, progress, cancel):
    items = _source_models(o, obj, sel, progress, cancel, to_pc=True)
    into_raw = _destination(o, "pc")
    problems, warnings, replacements = [], [], []
    if into_raw is None:
        out = o.out or service.default_out(service.ConvertOptions(input=o.input), "ps1", "pc")
        destination, based_on, container = "new", None, convert.blank_container()
    else:
        container = pc_container.Container(into_raw)
        based_on = os.path.abspath(o.into)
        if o.in_place:
            if o.out and not safeio.same_file(o.out, o.into):
                raise service.UserError("an in-place update writes to the destination file itself; do not also give "
                                        "a different output file")
            out, destination = o.into, "in-place"
        else:
            stem = os.path.splitext(os.path.basename(o.into))[0]
            folder = os.path.dirname(os.path.abspath(o.into))
            out = o.out or os.path.join(service.unique(os.path.join(folder, f"{stem}_with_converted_saves")),
                                        "SavedData_ww.dat")
            destination = "copy"
            if memoria.sidecars_beside(o.into):
                warnings.append("the Memoria/Moguri extra data of the saves already in that file stays next to the "
                                "original; the new copy does not have it (update the file directly to keep it)")
    out = os.path.abspath(out)
    occupied = {}
    for s, f in container.occupied():
        pv = container.preview(s, f)
        occupied[(s, f)] = {"place": f"slot {s + 1}, file {f + 1}", "location": pv.location if pv else "",
                            "playtime": f"{int(pv.play_seconds // 3600)}:{int(pv.play_seconds % 3600 // 60):02d}" if pv else ""}

    # FILE numbers to use: the saves' own, unless they are missing or clash (two regions on one card)
    nums = [a.file for a in items]
    if None in nums or len(set(nums)) != len(nums):
        for i, a in enumerate(items):
            a.note = f"placed as file {i + 1} (its FILE number was {'unknown' if a.file is None else 'used twice'})"
            a.file = i + 1
    if o.mapping:
        used = set()
        for a in items:
            if a.id not in o.mapping:
                raise service.UserError(f"manual placement: no place given for {a.source_label}")
            s, f = _parse_map(o.mapping[a.id], f"place of {a.source_label}", pc_container.SLOT_COUNT,
                              pc_container.SAVE_COUNT)
            if (s, f) in used:
                raise service.UserError(f"manual placement: slot {s}, file {f} is given twice")
            used.add((s, f))
            a.slot, a.file = s - 1, f - 1
        extra = set(o.mapping) - {a.id for a in items}
        if extra:
            raise service.UserError(f"manual placement names saves that are not selected: {', '.join(sorted(extra))}")
    else:
        files = [a.file - 1 for a in items]
        if o.pc_slot is not None:
            if not 1 <= o.pc_slot <= pc_container.SLOT_COUNT:
                raise service.UserError(f"PC slot must be 1-{pc_container.SLOT_COUNT}")
            slot = o.pc_slot - 1
        else:
            empty = [s for s in range(pc_container.SLOT_COUNT) if not any(k[0] == s for k in occupied)]
            fits = [s for s in range(pc_container.SLOT_COUNT) if not any((s, f) in occupied for f in files)]
            if empty:
                slot = empty[0]
            elif fits:
                slot = fits[0]
                warnings.append(f"no PC slot is completely empty, so the saves share slot {slot + 1} with saves that "
                                "are already there (those are kept)")
            else:
                slot = None
                problems.append("every PC slot already has saves where these would go. Choose a slot under Advanced "
                                "(and approve replacing the saves there), or use a new file")
        for a, f in zip(items, files):
            a.slot, a.file = slot, f
    for a in items:
        if a.slot is None:
            continue
        a.dest_label = f"Slot {a.slot + 1}, file {a.file + 1}"
        a.output = 0
        if (a.slot, a.file) in occupied:
            a.replaces = occupied[(a.slot, a.file)]
            r = a.replaces
            replacements.append(f"{a.dest_label} now holds {r['location'] or 'a save'} ({r['playtime']}); "
                                f"{a.source_label} would replace it")
        risk = memoria.overlay_risk(out, a.slot, a.file, float(a.model["playtime_seconds"]))
        if risk and risk[0] == "applies":
            a.problem_kind = "memoria-overlay"
            a.problem = (f"{os.path.basename(risk[1])} (Memoria/Moguri data of the save now in {a.dest_label.lower()}) "
                         "would be loaded over the converted save. Move or rename that file, or choose another slot")
        elif risk:
            a.warnings.append(f"an old Memoria file ({os.path.basename(risk[1])}) is next to this slot; Memoria ignores "
                              "it because its play time differs (deleting it is safe)")
    output = Output(out, os.path.basename(out), "pc", based_on=based_on, replace=destination == "in-place",
                    expected_sha256=safeio.sha256(into_raw) if destination == "in-place" else None, base_raw=into_raw)
    output.saves = [a.id for a in items if a.output == 0]
    plan = Plan(o, "ps1->pc", src, items, [output] if not problems else [], problems, warnings, replacements,
                destination=destination)
    plan.report_path = service.unique(out + ".report.json")
    plan.existing = len(occupied)
    plan._container = container
    return plan


def _build_pc(plan, progress, cancel):
    o, items = plan.options, plan.assignments
    container = plan._container
    base_ts = o.timestamp if o.timestamp is not None else time.time()
    # time stamps follow play time, so the save played longest is the newest (the game's Continue picks it)
    order = sorted(items, key=lambda a: (a.model["playtime_seconds"], a.slot, a.file))
    newest = order[-1]
    for i, a in enumerate(items):
        _check_cancel(cancel)
        progress(i, len(items), f"converting {a.source_label}")
        try:
            tree, rep = convert.to_pc_tree(a.model, None, strict=not o.lenient)
        except (convert.ConversionError, ps1_save.TextEncodeError, ValueError) as e:
            a.problem, a.problem_kind = f"cannot be converted: {e}", "convert"
            continue
        ts = base_ts - (len(order) - 1 - order.index(a))
        convert.insert(container, a.slot, a.file, tree, convert.preview_for(tree, a.model, ts),
                       overwrite=a.replaces is not None, set_latest=a is newest)
        rep_d = rep.as_dict()
        lossy = [f"PS1-only region {k} = {v}" for k, v in (a.model.get("unmapped") or {}).get("ps1_regions", {}).items()]
        a.report = {**rep_d, "compatibility": verify.compat_report("ps1->pc", rep_d, lossy)}
        a.report["compatibility"]["warnings"] += a.warnings
    if any(a.problem for a in items):
        return
    data = container.to_bytes()
    out = plan.outputs[0]
    out.data, out.sha256 = data, safeio.sha256(data)


def _verify_pc(plan, out, progress, cancel):
    """Re-parse the PC output: every converted save matches its source, every other place is untouched."""
    c = pc_container.Container(out.data)
    mine = set()
    for i, a in enumerate(plan.assignments):
        _check_cancel(cancel)
        progress(i, len(plan.assignments), f"verifying {a.dest_label}")
        t = c.slot_tree(a.slot, a.file)
        if t is None:
            raise safeio.SafetyError(f"{a.dest_label} is empty after conversion")
        f = verify.compare(a.model, model.from_pc(t))
        a.counts = verify.summarize(f)
        a.report["verification"] = {"counts": a.counts, "findings": f}
        bad = [x for x in f if x["status"] == "unexpected"]
        if bad:
            a.problem_kind = "verify"
            a.problem = "verification found unexpected differences: " + "; ".join(
                f"{x['field']}: {x['note'] or (x['source'], x['converted'])}" for x in bad[:5])
        mine.add((a.slot, a.file))
    if out.base_raw is not None:
        before = out.base_raw
        for s in range(pc_container.SLOT_COUNT):
            for f in range(pc_container.SAVE_COUNT):
                if (s, f) in mine:
                    continue
                for off, size in ((pc_container.block_offset(s, f), pc_container.BLOCK_RESERVED),
                                  (pc_container.preview_offset(s, f), pc_container.PREVIEW_RESERVED)):
                    if before[off:off + size] != out.data[off:off + size]:
                        raise safeio.SafetyError(f"internal check failed: slot {s + 1}, file {f + 1} would change")
        a0 = pc_container.block_offset(pc_container.AUTOSAVE, 0)
        if before[a0:a0 + pc_container.BLOCK_RESERVED] != out.data[a0:a0 + pc_container.BLOCK_RESERVED]:
            raise safeio.SafetyError("internal check failed: the autosave would change")


# ---- PC container -> PS1 cards ------------------------------------------------------------------
def _prepare_to_ps1(o, obj, sel, src, progress, cancel):
    if o.region not in ps1_writer.PRODUCT:
        raise service.UserError(f"region must be one of {', '.join(ps1_writer.PRODUCT)}")
    if o.format not in ("card", "mcs"):
        raise service.UserError("format must be card or mcs")
    if o.format == "mcs" and o.into:
        raise service.UserError("saves can be added to an existing memory card only as card format, not .mcs")
    items = _source_models(o, obj, sel, progress, cancel, to_pc=False)
    into_raw = _destination(o, "ps1")
    problems, warnings, replacements = [], [], []

    if into_raw is None:
        folder = os.path.abspath(o.out or service.unique(os.path.join(
            os.path.dirname(os.path.abspath(o.input)), f"{os.path.splitext(os.path.basename(o.input))[0]}_converted_ps1")))
        destination = "new"
        layout = o.layout
        if layout == "auto":
            layout = "by-slot" if len({a.slot for a in items}) == 1 else "compact"
        if o.mapping:
            cards = {}
            used = set()
            for a in items:
                if a.id not in o.mapping:
                    raise service.UserError(f"manual placement: no place given for {a.source_label}")
                cno, fno = _parse_map(o.mapping[a.id], f"place of {a.source_label}", 99, CARD_FILES)
                if (cno, fno) in used:
                    raise service.UserError(f"manual placement: card {cno}, FILE{fno:02d} is given twice")
                used.add((cno, fno))
                a.card, a.file = cno, fno
        elif layout == "by-slot":
            slots = sorted({a.slot for a in items})
            for a in items:
                a.card = slots.index(a.slot) + 1
        else:
            for i, a in enumerate(items):
                a.card, a.file = i // CARD_FILES + 1, i % CARD_FILES + 1
        outputs = []
        if o.format == "mcs":
            for i, a in enumerate(items):
                name = f"FFIX-PS1-Save-{i + 1:02d}-FILE{a.file:02d}.mcs"
                outputs.append(Output(os.path.join(folder, name), name, "ps1", kind="mcs"))
                a.output, a.card, a.dest_label = i, None, f"{name}, FILE{a.file:02d}"
        else:
            cards = sorted({a.card for a in items})
            for cno in cards:
                path = os.path.join(folder, f"{o.card_name}-{cno:02d}.mcr")
                outputs.append(Output(path, f"Card {cno:02d}", "ps1"))
            for a in items:
                a.output = cards.index(a.card)
                a.dest_label = f"Card {a.card:02d}, FILE{a.file:02d}"
        plan_report = os.path.join(folder, MANIFEST + ".json")
        text_report = os.path.join(folder, MANIFEST + ".txt")
    else:
        destination = "in-place" if o.in_place else "copy"
        if o.in_place:
            if o.out and not safeio.same_file(o.out, o.into):
                raise service.UserError("an in-place update writes to the memory card itself; do not also give a "
                                        "different output file")
            path = os.path.abspath(o.into)
        else:
            stem, ext = os.path.splitext(os.path.basename(o.into))
            path = os.path.abspath(o.out or service.unique(os.path.join(os.path.dirname(os.path.abspath(o.into)),
                                                                         f"{stem}_with_converted_saves{ext or '.mcr'}")))
        info = service.destination_slots(o.into)
        taken = dict(info["ff9_files"])               # FILE number -> block
        free_blocks = list(info["free_blocks"])
        wanted = {}
        if o.mapping:
            for a in items:
                if a.id not in o.mapping:
                    raise service.UserError(f"manual placement: no place given for {a.source_label}")
                cno, fno = _parse_map(o.mapping[a.id], f"place of {a.source_label}", 1, CARD_FILES)
                if fno in wanted.values():
                    raise service.UserError(f"manual placement: FILE{fno:02d} is given twice")
                wanted[a.id] = fno
        elif o.layout == "compact" or (o.layout == "auto" and len({a.slot for a in items}) > 1):
            wanted = {a.id: i + 1 for i, a in enumerate(items)}
        else:
            wanted = {a.id: a.file for a in items}
        used = set()
        need_blocks = 0
        room = min(len(free_blocks), CARD_FILES - len(taken))
        if not o.mapping and len(items) > room:
            problems.append(f"the memory card has room for {room} more save(s), but {len(items)} are selected. "
                            "Choose fewer saves, or create new memory cards instead")
            items_to_place = []
        else:
            items_to_place = items
        for a in items_to_place:
            fno = wanted[a.id]
            if not o.mapping and (fno in taken or fno in used):
                free = [n for n in range(1, CARD_FILES + 1) if n not in taken and n not in used]
                if not free:
                    a.problem, a.problem_kind = "no FILE number is free on this memory card", "no-room"
                    continue
                a.note = f"FILE{fno:02d} is already used on this card, so it becomes FILE{free[0]:02d}"
                fno = free[0]
            a.file = fno
            used.add(fno)
            a.card, a.output = 1, 0
            a.dest_label = f"FILE{fno:02d}"
            if fno in taken:
                blk = taken[fno]
                r = info["occupied"].get(blk, {})
                a.replaces = {"place": f"FILE{fno:02d} (block {blk})", "location": r.get("location", ""),
                              "playtime": r.get("playtime", "")}
                replacements.append(f"FILE{fno:02d} on the card now holds {r.get('location') or 'a save'} "
                                    f"({r.get('playtime', '?')}); {a.source_label} would replace it")
            else:
                need_blocks += 1
        if need_blocks > len(free_blocks):
            problems.append(f"the memory card has room for {len(free_blocks)} more save(s), but {need_blocks} need "
                            "a new place. Choose fewer saves, or create new memory cards instead")
        outputs = [Output(path, os.path.basename(path), "ps1", based_on=os.path.abspath(o.into),
                          replace=destination == "in-place",
                          expected_sha256=safeio.sha256(into_raw) if destination == "in-place" else None,
                          base_raw=into_raw)]
        plan_report = service.unique(path + ".report.json")
        text_report = None
    for x in outputs:
        x.saves = [a.id for a in items if a.output is not None and outputs[a.output] is x]
    plan = Plan(o, "pc->ps1", src, items, outputs if not problems else [], problems, warnings, replacements,
                report_path=plan_report, manifest_text_path=text_report, destination=destination)
    if into_raw is not None:
        plan.existing = len(info["occupied"])
    return plan


def _build_ps1(plan, progress, cancel):
    o, items = plan.options, plan.assignments
    cards = {}
    for x in plan.outputs:
        cards[x.path] = bytearray(x.base_raw) if x.base_raw is not None else None
    blocks_of = {x.path: {} for x in plan.outputs}
    for i, a in enumerate(items):
        _check_cancel(cancel)
        progress(i, len(items), f"converting {a.source_label}")
        x = plan.outputs[a.output]
        rec = a.payload
        try:
            block, rep = ps1_writer.build_block(a.model, file_no=a.file, region=o.region)
        except (ps1_writer.PS1WriteError, ps1_save.TextEncodeError, ValueError) as e:
            a.problem, a.problem_kind = f"cannot be converted: {e}", "convert"
            continue
        filename = ps1_writer.card_filename(a.file, ps1_writer.PRODUCT[o.region])
        report = {**rep, "pc_only_not_representable": service.PC_ONLY_FIELDS,
                  "compatibility": verify.compat_report("pc->ps1", rep, service.PC_ONLY_FIELDS)}
        service._add_memoria(report, rec)
        report["compatibility"]["warnings"] += a.warnings
        a.report = report
        if x.kind == "mcs":
            cards[x.path] = bytearray(ps1_card.single_save_file(block, filename))
            blocks_of[x.path][a.id] = (filename, 0)
            continue
        card = bytes(cards[x.path]) if cards[x.path] is not None else ps1_card.blank_card()
        dest_block = None
        if a.replaces is not None:
            dest_block = _ff9_files(card).get(a.file)
        try:
            card, idx = ps1_card.write_save(card, block, filename, dest_block, replace=a.replaces is not None)
        except ps1_card.CardError as e:
            a.problem, a.problem_kind = f"cannot be placed on the card: {e}", "no-room"
            continue
        cards[x.path] = bytearray(card)
        blocks_of[x.path][a.id] = (filename, idx)
        a.dest_label += f" (block {idx})" if x.base_raw is not None else ""
    if any(a.problem for a in items):
        return
    for x in plan.outputs:
        x.data = bytes(cards[x.path])
        x.sha256 = safeio.sha256(x.data)
    plan._blocks = blocks_of


def _ff9_files(card):
    """{FILE number: block} of the FF9 saves on a raw card."""
    out = {}
    for e in ps1_card.parse_raw_card(card):
        n = service.ps1_file_number(e.filename)
        if e.data[:2] == b"SC" and ps1_save.REGIONS.get(e.product_code[:12]) and n is not None:
            out[n] = e.block_index
    return out


def _verify_ps1(plan, x, progress, cancel):
    kind, entries = ps1_card.parse_file(x.data)
    if kind != {"card": "raw-card", "mcs": "mcs-single"}[x.kind]:
        raise safeio.SafetyError(f"{x.label} did not re-read as a {'memory card' if x.kind == 'card' else '.mcs file'}")
    mine = plan._blocks[x.path]
    names = [e.filename for e in entries]
    for i, a in enumerate(a for a in plan.assignments if a.id in mine):
        _check_cancel(cancel)
        progress(i, len(mine), f"verifying {a.dest_label}")
        filename, idx = mine[a.id]
        if names.count(filename) != 1:
            raise safeio.SafetyError(f"{a.dest_label}: the converted save is not on the card exactly once")
        e = next(e for e in entries if e.filename == filename)
        s = ps1_save.PS1Save(e.data, e.product_code, e.filename)
        if not s.crc_ok:
            raise safeio.SafetyError(f"{a.dest_label}: the converted save has a bad checksum")
        f = verify.compare(a.model, model.from_ps1(s))
        a.counts = verify.summarize(f)
        a.report["verification"] = {"counts": a.counts, "findings": f}
        bad = [y for y in f if y["status"] == "unexpected"]
        if bad:
            a.problem_kind = "verify"
            a.problem = "verification found unexpected differences: " + "; ".join(
                f"{y['field']}: {y['note'] or (y['source'], y['converted'])}" for y in bad[:5])
    if x.base_raw is not None:
        changed = {idx for _, idx in mine.values()}
        for i in range(1, 16):
            if i in changed:
                continue
            if x.base_raw[i * 0x80:(i + 1) * 0x80] != x.data[i * 0x80:(i + 1) * 0x80] or \
               x.base_raw[i * 0x2000:(i + 1) * 0x2000] != x.data[i * 0x2000:(i + 1) * 0x2000]:
                raise safeio.SafetyError(f"internal check failed: card block {i} would change")
    if len([e for e in entries if e.data[:2] == b"SC"]) > CARD_FILES:
        raise safeio.SafetyError(f"{x.label} would hold more than {CARD_FILES} saves")


# ---- shared -------------------------------------------------------------------------------------
def _build_outputs(plan, progress, cancel):
    if plan.direction == "ps1->pc":
        _build_pc(plan, progress, cancel)
    else:
        _build_ps1(plan, progress, cancel)
    if any(a.problem for a in plan.assignments):
        return
    for x in plan.outputs:
        try:
            if x.platform == "pc":
                _verify_pc(plan, x, progress, cancel)
            else:
                _verify_ps1(plan, x, progress, cancel)
        except safeio.SafetyError as e:
            plan.problems.append(f"{x.label}: {e}; nothing will be written")


def manifest_text(plan, results=None):
    """A plain-text list of where every save went (written next to new PS1 cards)."""
    res = {r["path"]: r for r in (results or [])}
    lines = [f"FFIX Save Converter {__version__} - {plan.direction.upper().replace('->', ' to ')}",
             f"Source: {plan.source['path']}", f"Converted: {time.strftime('%Y-%m-%d %H:%M')}", ""]
    for x in plan.outputs:
        lines.append(f"{os.path.basename(x.path)}" + (f"   (backup of the previous file: {res[x.path]['backup']})"
                                                       if res.get(x.path, {}).get("backup") else ""))
        for a in plan.assignments:
            if a.id in x.saves:
                s = a.summary
                lines.append(f"  {a.dest_label:24} <- {a.source_label:18} {s['location'] or '-'}, disc {s['disc'] or '?'}, "
                             f"{s['playtime']}, {', '.join(s['party'])}")
                if a.note:
                    lines.append(f"  {'':24}    {a.note}")
        lines.append("")
    if plan.warnings:
        lines += ["Notes:"] + [f"  - {w}" for w in plan.warnings]
    return "\n".join(lines) + "\n"


def commit(plan, cancel=None, progress=None):
    """Write the verified plan as one transaction. Returns {"outputs": [...], "report_path", "manifest_text_path"}."""
    if not plan.ok:
        raise service.UserError("the batch cannot be converted as it is:\n  - " + "\n  - ".join(plan.blocking()
                                or ["nothing to write"]))
    if plan.needs_approval:
        raise service.UserError("these saves would replace saves that are already there; approve replacing them "
                                "(--replace) or choose other places:\n  - " + "\n  - ".join(plan.replacements))
    tx = safeio.Transaction(sources=(plan.options.input,))
    validators = {"pc": lambda b: pc_container.Container(b), "card": lambda b: ps1_card.parse_raw_card(b),
                  "mcs": lambda b: ps1_card.parse_file(b)}
    for x in plan.outputs:
        tx.add(x.path, x.data, validators["pc" if x.platform == "pc" else x.kind], replace=x.replace,
               expected_sha256=x.expected_sha256, create_dir=True)
    paths = [x.path for x in plan.outputs]

    def report_bytes(backups):
        res = [{"path": p, "backup": backups.get(os.path.abspath(p))} for p in paths]
        return json.dumps(plan.manifest(res), indent=1, default=str).encode("utf-8")
    tx.add(plan.report_path, report_bytes, lambda b: json.loads(b), create_dir=True)
    if plan.manifest_text_path:
        tx.add(plan.manifest_text_path,
               lambda backups: manifest_text(plan, [{"path": p, "backup": backups.get(p)} for p in paths]).encode("utf-8"),
               create_dir=True)
    try:
        results = tx.commit(cancel=cancel, progress=progress)
    except safeio.Cancelled as e:
        raise Cancelled(str(e)) from None
    by_path = {r["path"]: r for r in results}
    return {"outputs": [by_path[os.path.abspath(p)] for p in paths], "report_path": plan.report_path,
            "manifest_text_path": plan.manifest_text_path, "plan": plan}


def run(o, progress=None, cancel=None):
    """prepare() + commit(): the command line's batch conversion."""
    return commit(prepare(o, progress, cancel), cancel, progress)


def recover(folder):
    """Undo every interrupted batch whose journal is in folder. Returns [(journal, result)]."""
    return [(j, safeio.recover(j)) for j in safeio.find_journals(folder)]
