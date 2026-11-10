"""Conversion service: the single code path behind both the command line and the GUI.

Nothing here prints or prompts. Callers pass options (an argparse namespace or ConvertOptions) and get plain
dicts back. Safety rules live here and in safeio, so every front end gets the same checks:
inputs are never modified, outputs are new files unless `force` is given (then a verified backup is made
first), and the output is re-parsed and verified before it is moved into place.
Slots, files and blocks are 1-based, as shown in the game menus.
"""
import dataclasses
import json
import os
import time

from . import __version__, convert, memoria, model, pc_container, ps1_card, ps1_save, ps1_writer, safeio, verify

NAMES = ["Zidane", "Vivi", "Garnet", "Steiner", "Freya", "Quina", "Eiko", "Amarant", "Beatrix"]
PC_ONLY_FIELDS = ["50000_Setting (options, key bindings)", "70000_World camera angle", "60000_Sound",
                  "80000_Achievement / 98000_Achievement (Steam achievement tracking)",
                  "10000_State timeCounter/timerControl/timerDisplay", "20000_Event.gStepCount",
                  "Tetra Master card side/cpoint (constant 0/10)"]

class UserError(Exception):
    pass


# Errors a front end shows to the user as a plain message (nothing was written when one is raised).
USER_ERRORS = (UserError, memoria.MemoriaFormatError, safeio.SafetyError, convert.ConversionError, ps1_writer.PS1WriteError,
               ps1_card.CardError, pc_container.ContainerError, ps1_save.TextEncodeError)


def explain_error(e):
    """A plain one-line message for an error a user can act on, or None for a genuine bug."""
    if isinstance(e, USER_ERRORS):
        return str(e)
    if isinstance(e, PermissionError):
        return f"permission denied: {e.filename or e}"
    if isinstance(e, FileNotFoundError):
        return f"not found: {e.filename or e}"
    if isinstance(e, OSError):
        return str(e)
    if isinstance(e, ValueError):
        return f"invalid value: {e}"
    return None


@dataclasses.dataclass
class ConvertOptions:
    """Every option of `ffix-convert convert`, with the same defaults."""
    input: str
    dst: str = None
    src: str = None
    source: str = None
    out: str = None
    into: str = None
    dest: str = None
    force: bool = False
    in_place: bool = False
    report: str = None
    lenient: bool = False
    block: int = None
    slot: int = 1
    file: int = 1
    overwrite_slot: bool = False
    template: str = None
    template_slot: str = "1/1"
    timestamp: float = None
    pc_slot: str = None
    ps1_file: int = 1
    dest_block: int = None
    overwrite_block: bool = False
    region: str = "NTSC-U"
    disc: int = None
    format: str = "card"
    ps1_base: str = None
    ps1_base_block: int = None
    allow_lossy: bool = False     # Memoria -> PS1: drop/clamp modded values instead of refusing
    create_dir: bool = False      # create the output's folder if it does not exist yet


# ---- reading any save file ---------------------------------------------------------------
def load_any(path):
    """Return ("pc", Container, raw) or ("ps1", (container kind, [ff9 entries], [other entries]), raw)."""
    raw = safeio.read_source(path)
    try:
        return "pc", pc_container.Container(raw), raw
    except pc_container.ContainerError as e:
        pc_err = e
    try:
        kind, entries = ps1_card.parse_file(raw)
    except ps1_card.CardError as e:
        if len(raw) == pc_container.CONTAINER_SIZE:
            raise UserError(f"{path}: looks like a PC save but could not be read: {pc_err}")
        if memoria.looks_like_sidecar(raw):
            raise UserError(f"{os.path.basename(path)} is Memoria's extra data for one save, not a save file. Open "
                            "SavedData_ww.dat from the same folder instead; its Memoria data is used automatically")
        raise UserError(f"{path}: not a recognised FF9 save ({e})")
    ff9 = [e for e in entries if e.data[:2] == b"SC" and ps1_save.REGIONS.get(e.product_code[:12])]
    return "ps1", (kind, ff9, [e for e in entries if e not in ff9]), raw


def ps1_entry(info, block, path):
    kind, ff9, others = info
    if not ff9:
        raise UserError(f"no FF9 save in {path} ({kind}; other saves: {[e.filename for e in others] or 'none'})")
    if block is None:
        if len(ff9) > 1:
            raise UserError("this card holds several FF9 saves; choose one with --source BLOCK. Blocks: "
                            + ", ".join(str(e.block_index) for e in ff9) + "  (see: ffix-convert inspect)")
        return ff9[0]
    try:
        block = int(block)
    except ValueError:
        raise UserError(f"PS1 source must be a block number 1-15, got {block!r}")
    m = [e for e in ff9 if e.block_index == block]
    if not m:
        raise UserError(f"no FF9 save in block {block}; FF9 blocks: {[e.block_index for e in ff9]}")
    return m[0]


def ps1_source(entry):
    """(PS1Save, canonical model, menu location) of one PS1 directory entry."""
    sv = ps1_save.PS1Save(entry.data, entry.product_code, entry.filename)
    return sv, model.from_ps1(sv), sv.preview()["location"]


def pc_source(path, container, slot, file, allow_lossy=False):
    """(model, Reconciliation, location) of one PC slot (0-based), read the way Memoria loads it: the container,
    with the slot's Memoria sidecar applied when Memoria itself would apply it."""
    tree = container.slot_tree(slot, file)
    side = memoria.slot_sidecar(path, slot, file, model.from_pc(tree)["playtime_seconds"])
    m, rec = memoria.reconcile(tree, side, allow_lossy=allow_lossy)
    location = container.preview(slot, file).location
    m["preview"] = {"location": location}
    return m, rec, location


def ps1_file_number(filename):
    """The in-game FILE number (1-15) of a PS1 directory name ending in "-NN" (NN = FILE - 1), else None."""
    if len(filename) > 3 and filename[-3] == "-" and filename[-2:].isdigit() and int(filename[-2:]) <= 14:
        return int(filename[-2:]) + 1
    return None


def parse_slot(text, what):
    try:
        s, f = (int(x) for x in str(text).split("/"))
    except ValueError:
        raise UserError(f"{what} must look like SLOT/FILE (e.g. 2/5), got {text!r}")
    if not (1 <= s <= pc_container.SLOT_COUNT and 1 <= f <= pc_container.SAVE_COUNT):
        raise UserError(f"{what} {text} out of range: slot 1-{pc_container.SLOT_COUNT}, file 1-{pc_container.SAVE_COUNT}")
    return s - 1, f - 1


def pc_slot(c, text, path):
    occ = c.occupied()
    if not occ:
        raise UserError(f"{path} contains no saves")
    if text is None:
        if len(occ) > 1:
            raise UserError("this PC file holds several saves; choose one with --source SLOT/FILE (or --pc-slot). Occupied: "
                            + ", ".join(f"{s + 1}/{f + 1}" for s, f in occ) + "  (see: ffix-convert inspect)")
        return occ[0]
    sl = parse_slot(text, "PC source")
    if sl not in occ:
        raise UserError(f"PC slot {text} is empty. Occupied: " + ", ".join(f"{s + 1}/{f + 1}" for s, f in occ))
    return sl


def describe(m, location):
    party = [f"{m['players'][s]['name']} Lv{m['players'][s]['level']}" for s in m["party"]["slot"] if s not in (9, 255)]
    t = m["playtime_seconds"]
    disc = None
    try:
        disc = ps1_writer.disc_for_scenario(m["event"]["scenario_counter"])
    except ps1_writer.PS1WriteError:
        pass
    location = (location or "").replace("’", "'")          # typographic apostrophe -> ASCII for consoles
    return {"location": location, "scenario_counter": m["event"]["scenario_counter"], "disc": disc,
            "party": party, "gil": m["party"]["gil"], "playtime": f"{int(t // 3600)}:{int(t % 3600 // 60):02d}",
            "map": "world map" if m["state"]["mode"] == 3 else "field"}


def list_saves(path):
    plat, obj, raw = load_any(path)
    rows = []
    if plat == "pc":
        sidecars = memoria.sidecars_beside(path)
        for s, f in obj.occupied():
            tree = obj.slot_tree(s, f)
            m = model.from_pc(tree)
            side = memoria.slot_sidecar(path, s, f, m["playtime_seconds"])
            if side["status"] in ("valid", "untimed"):
                m, _ = memoria.reconcile(tree, side, allow_lossy=True)
            rows.append({"id": f"{s + 1}/{f + 1}", **describe(m, obj.preview(s, f).location), "memoria": side["status"]})
        fmt = "SavedData_ww.dat (vanilla 2016, encrypted)"
        if sidecars:
            fmt += f" with {len(sidecars)} Memoria sidecar file(s)"
        head = {"platform": "pc", "format": fmt, "sha256": safeio.sha256(raw), "memoria_sidecars": len(sidecars)}
    else:
        kind, ff9, others = obj
        for e in ff9:
            sv = ps1_save.PS1Save(e.data, e.product_code, e.filename)
            m = model.from_ps1(sv)
            rows.append({"id": str(e.block_index), "file": e.filename, "region": sv.region[0], "crc_ok": sv.crc_ok,
                         **describe(m, sv.preview()["location"])})
        head = {"platform": "ps1", "format": kind, "sha256": safeio.sha256(raw),
                "other_saves": [e.filename for e in others]}
    return head, rows


def destination_slots(path):
    """What an existing destination file already holds, for occupied-slot warnings.

    PC: {"platform": "pc", "occupied": {"S/F": row}}. PS1 raw card: {"platform": "ps1", "occupied": {block: row},
    "other_blocks": {block: filename}, "free_blocks": [...], "ff9_files": {FILEnn number: block}}."""
    plat, obj, raw = load_any(path)
    head, rows = list_saves(path)
    if plat == "pc":
        return {"platform": "pc", "occupied": {r["id"]: r for r in rows}}
    kind, ff9, others = obj
    if kind != "raw-card":
        raise UserError(f"{path} is a {kind} file; a destination card must be a raw 128 KB memory card (.mcr/.mcd/.srm)")
    used = {b: name for b, (state, name) in ps1_card.directory(raw).items() if state not in ps1_card.FREE_STATES}
    files = {}
    for e in ff9:                     # directory names end in "-NN" with NN = in-game FILE number - 1
        n = ps1_file_number(e.filename)
        if n is not None:
            files[n] = e.block_index
    return {"platform": "ps1", "occupied": {int(r["id"]): r for r in rows},
            "other_blocks": {b: n for b, n in used.items() if b not in {e.block_index for e in ff9}},
            "free_blocks": [b for b in range(1, 16) if b not in used], "ff9_files": files}


# ---- conversion ------------------------------------------------------------------------------
def is_cloud_path(path):
    """Steam Cloud copies: the game's cloud file and anything in Steam's per-account userdata folder."""
    p = os.path.normcase(os.path.realpath(os.path.abspath(path))).replace("\\", "/")
    return os.path.basename(p).startswith("ff9_cloudsavefile") or "/steam/userdata/" in p


def refuse_cloud_target(path):
    if is_cloud_path(path):
        raise UserError(f"{path} is a Steam Cloud save; this tool never writes cloud saves. "
                        "Write to the local save folder or a new file instead")


def default_out(a, src, dst):
    stem = os.path.splitext(os.path.basename(a.input))[0]
    folder = os.path.dirname(os.path.abspath(a.input))
    if dst == "pc":
        sub = unique(os.path.join(folder, f"{stem}_converted_pc"))   # created only after verification
        return os.path.join(sub, "SavedData_ww.dat")
    return os.path.join(folder, f"{stem}_converted_ps1{'.mcs' if a.format == 'mcs' else '.mcr'}")


def unique(path):
    if not os.path.lexists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.lexists(f"{base}-{n}{ext}"):
        n += 1
    return f"{base}-{n}{ext}"


def convert_file(a, dry_run=False):
    """Convert one save. `a` is ConvertOptions or an argparse namespace with the same fields.

    dry_run builds and verifies the output in memory and writes nothing (the GUI's compatibility review).
    Returns a dict: src, dst, src_id, dest_desc, out, backup, report_path, report, counts, summary, model."""
    plat, obj, raw_in = load_any(a.input)
    src = a.src or plat
    if src != plat:
        raise UserError(f"--from {src} given, but {a.input} is a {plat.upper()} save")
    dst = a.dst or ("pc" if src == "ps1" else "ps1")
    if src == dst:
        raise UserError(f"source and target are both {src}; use --to {'pc' if src == 'ps1' else 'ps1'}")
    if a.in_place:
        if not a.into:
            raise UserError("--in-place needs --into FILE (the destination file to update)")
        if not a.force:
            raise UserError("--in-place replaces your destination file; add --force to confirm (a verified backup is made)")
        if a.out and not safeio.same_file(a.out, a.into):
            raise UserError("--in-place writes to --into; do not also give a different --out")
        out = a.into
    else:
        out = a.out or default_out(a, src, dst)
    refuse_cloud_target(out)
    into_raw = safeio.read_source(a.into) if a.into else None
    if a.into:
        safeio.check_distinct(a.into, a.input)
    source_sel = a.source if a.source is not None else (a.block if src == "ps1" else a.pc_slot)

    if src == "ps1":
        entry = ps1_entry(obj, source_sel, a.input)
        _, m, location = ps1_source(entry)
        result, report = _to_pc(a, m, into_raw, location, out)
        src_id = f"block {entry.block_index}"
    else:
        sl, sf = pc_slot(obj, source_sel, a.input)
        m, rec, location = pc_source(a.input, obj, sl, sf, getattr(a, "allow_lossy", False))
        if rec.blocking:
            raise UserError("this Memoria/Moguri save holds data the PlayStation game cannot represent:\n  - "
                            + "\n  - ".join(rec.blocking))
        result, report = _to_ps1(a, m, into_raw)
        _add_memoria(report, rec)
        src_id = f"slot {sl + 1}/{sf + 1}"
    data, dest_desc, find = result

    def validate(blob):
        conv = find(blob)
        f = verify.compare(m, conv)
        bad = [x for x in f if x["status"] == "unexpected"]
        if bad:
            raise safeio.SafetyError("internal verification failed, nothing written: "
                                     + "; ".join(f"{x['field']}: {x['note'] or (x['source'], x['converted'])}" for x in bad[:5]))
        validate.findings = f

    if dry_run:
        if os.path.lexists(out) and not a.force:
            raise UserError(f"{out} already exists; choose a new file name (existing files are never overwritten "
                            "without your confirmation)")
        validate(data)
        res = {"sha256": safeio.sha256(data), "backup": None}
    else:
        expected = safeio.sha256(into_raw) if (a.in_place and into_raw is not None) else None
        res = safeio.write_output(out, data, validate, sources=(a.input,), force=a.force, expected_sha256=expected,
                                  create_dir=getattr(a, "create_dir", False) or (not a.out and not a.in_place))
    counts = verify.summarize(validate.findings)
    summary = describe(m, location)
    report.update({
        "tool": f"ffix-convert {__version__}", "direction": f"{src}->{dst}",
        "input": {"file": os.path.abspath(a.input), "sha256": safeio.sha256(raw_in), "save": src_id,
                  "summary": summary},
        "output": {"file": os.path.abspath(out), "sha256": res["sha256"], "destination": dest_desc,
                   "based_on": os.path.abspath(a.into) if a.into else "new file", "backup_of_replaced_file": res["backup"]},
        "verification": {"counts": counts, "findings": validate.findings},
        "conversion_status": "PS1->PC verified in vanilla Steam FF9" if dst == "pc" else
                             "PC->PS1 beta: verified in DuckStation on several checkpoints",
    })
    mem = report.get("memoria") or {}
    if mem.get("sidecar_status") in ("valid", "untimed") or mem.get("lossy"):
        report["conversion_status"] = ("Memoria/Moguri->PS1 beta: verified in-game for unmodified gameplay (Memoria "
                                       "2025-07-13, Steam build 5378074, DuckStation; one Disc 2 checkpoint). Values "
                                       "from gameplay mods are refused unless lossy conversion was chosen")
    rpath = None
    if not dry_run:
        rpath = a.report or unique(out + ".report.json")
        safeio.write_output(rpath, json.dumps(report, indent=1, default=str).encode("utf-8"), lambda b: json.loads(b),
                            sources=(a.input, out), force=bool(a.report) and a.force)
    return {"src": src, "dst": dst, "src_id": src_id, "dest_desc": dest_desc, "out": out, "backup": res["backup"],
            "report_path": rpath, "report": report, "counts": counts, "summary": summary, "model": m}


def _add_memoria(report, rec):
    report["memoria"] = rec.as_dict()
    c = report["compatibility"]
    c["safely_transformed"] += [f"Memoria: {x}" for x in rec.applied]
    c["unsupported_or_lossy"] += [f"Memoria-only, not on PS1: {x}" for x in rec.dropped]
    c["unsupported_or_lossy"] += [f"LOSSY (you allowed it): {x}" for x in rec.lossy]
    c["warnings"] += [f"Memoria: {x}" for x in rec.notes] + [f"lossy conversion: {x}" for x in rec.lossy]


def _to_pc(a, m, into_raw, location, out):
    template = None
    if a.template:
        tc = pc_container.Container(safeio.read_source(a.template))
        template = tc.slot_tree(*parse_slot(a.template_slot, "--template-slot"))
        if template is None:
            raise UserError("template slot is empty")
    tree, rep = convert.to_pc_tree(m, template, strict=not a.lenient)
    container = pc_container.Container(into_raw) if into_raw is not None else convert.blank_container()
    slot, file = (parse_slot(a.dest, "--dest") if a.dest else (a.slot - 1, a.file - 1))
    if not (0 <= slot < pc_container.SLOT_COUNT and 0 <= file < pc_container.SAVE_COUNT):
        raise UserError(f"PC destination slot/file out of range (slot 1-10, file 1-15)")
    ts = a.timestamp if a.timestamp is not None else time.time()
    convert.insert(container, slot, file, tree, convert.preview_for(tree, m, ts), overwrite=a.overwrite_slot)
    data = container.to_bytes()
    risk = memoria.overlay_risk(out, slot, file, tree["Data"]["95000_Setting"]["00001_time"])
    if risk and risk[0] == "applies":
        raise UserError(f"{risk[1]} (Memoria/Moguri data of the save that was in slot {slot + 1}/{file + 1}) would be "
                        "loaded over the converted save, because its play time matches. Move or rename that file "
                        "first, or choose another slot")

    def find(blob):
        t = pc_container.Container(blob).slot_tree(slot, file)
        if t is None:
            raise safeio.SafetyError("converted slot missing after write")
        return model.from_pc(t)

    rep_d = rep.as_dict()
    lossy = [f"PS1-only region {k} = {v}" for k, v in (m.get("unmapped") or {}).get("ps1_regions", {}).items()]
    compat = verify.compat_report("ps1->pc", rep_d, lossy)
    if risk:
        compat["warnings"].append(f"an old Memoria sidecar ({os.path.basename(risk[1])}) is next to this slot; Memoria "
                                  "ignores it because its play time differs (deleting it is safe)")
    return (data, f"slot {slot + 1} file {file + 1}", find), {**rep_d, "compatibility": compat}


def _to_ps1(a, m, into_raw):
    base = None
    if a.ps1_base:
        plat, obj, _ = load_any(a.ps1_base)
        if plat != "ps1":
            raise UserError("--ps1-base must be a PS1 save")
        base = ps1_entry(obj, a.ps1_base_block, a.ps1_base).data
    file_no = int(a.dest) if a.dest else a.ps1_file
    filename = ps1_writer.card_filename(file_no, ps1_writer.PRODUCT[a.region])
    block, rep = ps1_writer.build_block(m, base_block=base, file_no=file_no, region=a.region, disc=a.disc)
    if a.format == "mcs":
        if into_raw is not None:
            raise UserError("--into needs --format card")
        data, idx = ps1_card.single_save_file(block, filename), 0
    else:
        card = None
        if into_raw is not None:
            if ps1_card.parse_file(into_raw)[0] != "raw-card":
                raise UserError("--into must be a raw 128 KB memory card (.mcr/.mcd/.srm)")
            card = into_raw
        data, idx = ps1_card.write_save(card or ps1_card.blank_card(), block, filename, a.dest_block, a.overwrite_block)

    def find(blob):
        kind, entries = ps1_card.parse_file(blob)
        e = [x for x in entries if x.filename == filename]
        if len(e) != 1:
            raise safeio.SafetyError("converted save not found exactly once in the output card")
        s = ps1_save.PS1Save(e[0].data, e[0].product_code, e[0].filename)
        if not s.crc_ok:
            raise safeio.SafetyError("converted block has a bad checksum")
        if into_raw is not None and kind == "raw-card":
            _check_other_blocks_untouched(into_raw, blob, e[0].block_index)
        return model.from_ps1(s)

    dest = f"FILE{file_no:02d}" + (f" (card block {idx})" if idx else " (single-save file)")
    return (data, dest, find), {**rep, "pc_only_not_representable": PC_ONLY_FIELDS,
                                "compatibility": verify.compat_report("pc->ps1", rep, PC_ONLY_FIELDS)}


def _check_other_blocks_untouched(before, after, idx):
    for i in range(1, 16):
        if i == idx:
            continue
        if before[i * 0x80:(i + 1) * 0x80] != after[i * 0x80:(i + 1) * 0x80] or \
           before[i * 0x2000:(i + 1) * 0x2000] != after[i * 0x2000:(i + 1) * 0x2000]:
            raise safeio.SafetyError(f"internal check failed: block {i} would change; nothing written")


# ---- independent verification ----------------------------------------------------------------
def verify_files(source, converted, source_slot=None, converted_slot=None):
    """Compare a source save with its converted copy. Returns a dict with ids, platforms, findings, counts."""
    sp, so, _ = load_any(source)
    cp, co, _ = load_any(converted)

    def pc_model(path, obj, s, f):
        tree = obj.slot_tree(s, f)
        side = memoria.slot_sidecar(path, s, f, model.from_pc(tree)["playtime_seconds"])
        return memoria.reconcile(tree, side, allow_lossy=True)[0]   # the state Memoria would load

    def models(plat, obj, path):
        if plat == "pc":
            return [(f"{s + 1}/{f + 1}", pc_model(path, obj, s, f)) for s, f in obj.occupied()]
        return [(str(e.block_index), model.from_ps1(ps1_save.PS1Save(e.data, e.product_code, e.filename)))
                for e in obj[1]]

    def pick(lst, sel, path, role):
        if sel is not None:
            m = [x for x in lst if x[0] == str(sel)]
            if not m:
                raise UserError(f"{role} save {sel} not found in {path}; available: {[x[0] for x in lst]}")
            return m[0]
        if len(lst) == 1:
            return lst[0]
        return None

    src = pick(models(sp, so, source), source_slot, source, "source")
    if src is None:
        raise UserError("source holds several saves; choose one with --source-slot")
    clist = models(cp, co, converted)
    conv = pick(clist, converted_slot, converted, "converted")
    if conv is None:
        same = [x for x in clist if x[1]["event"]["gEventGlobal_b64"] == src[1]["event"]["gEventGlobal_b64"]
                and x[1]["party"]["gil"] == src[1]["party"]["gil"]]
        if len(same) != 1:
            raise UserError("converted file holds several saves; choose one with --converted-slot. Available: "
                            + ", ".join(x[0] for x in clist))
        conv = same[0]
    findings = verify.compare(src[1], conv[1])
    return {"source_platform": sp, "converted_platform": cp, "source": src[0], "converted": conv[0],
            "findings": findings, "counts": verify.summarize(findings)}
