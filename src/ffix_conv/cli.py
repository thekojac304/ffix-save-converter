"""ffix-convert: Final Fantasy IX save converter (PS1 memory cards <-> PC/Steam 2016).

  ffix-convert inspect <file> [--json]
  ffix-convert convert <file> [--to pc|ps1] [--source N|S/F] [--out FILE] [destination options]
  ffix-convert verify <source file> <converted file> [--source-slot X] [--converted-slot Y]
  ffix-convert batch <file> [--select ID ...] [--out PATH | --into FILE [--in-place --force]] [--replace] [--dry-run]
  ffix-convert recover <folder>

Safety: inputs are never modified; outputs are new files unless --force is given (then a
verified backup is made first); output is re-parsed and verified before it is moved into place.
Slots, files and blocks are 1-based, as shown in the game menus.
Exit codes: 0 success, 1 verification found unexpected differences, 2 error (nothing written).
"""
import argparse
import json
import sys

from . import __version__, batch, service
from .service import PC_ONLY_FIELDS, UserError, describe, list_saves


# ---- commands ------------------------------------------------------------------------------
def cmd_inspect(a):
    head, rows = list_saves(a.file)
    if a.json:
        print(json.dumps({**head, "saves": rows}, indent=1))
        return 0
    if head["platform"] == "pc":
        print(f"PC save file ({head['format']}), {len(rows)} save(s)   sha256 {head['sha256'][:16]}...")
        idname = "slot/file"
    else:
        print(f"PS1 memory card ({head['format']}), {len(rows)} FF9 save(s)   sha256 {head['sha256'][:16]}...")
        if head["other_saves"]:
            print(f"  (also {len(head['other_saves'])} other save(s), not touched)")
        idname = "block"
    for r in rows:
        extra = f" {r['region']}{'' if r['crc_ok'] else ' CRC-MISMATCH'}" if head["platform"] == "ps1" else ""
        disc = f"disc {r['disc']}" if r["disc"] else "disc ?"
        print(f"  {idname} {r['id']:>5}: {r['location'] or '-':28} {disc}, {r['map']}, {r['playtime']}, "
              f"{r['gil']} gil{extra}")
        print(f"               party: {', '.join(r['party']) or '-'}")
    return 0


def cmd_convert(a):
    r = service.convert_file(a)
    m, summary, counts = r["model"], r["summary"], r["counts"]
    c = r["report"]["compatibility"]
    print(f"converted {r['src'].upper()} {r['src_id']} -> {r['dst'].upper()} {r['dest_desc']}")
    print(f"  {summary['location']}: scenario {m['event']['scenario_counter']}, {', '.join(summary['party'])}")
    print(f"  wrote   {r['out']}" + (f"  (backup of previous file: {r['backup']})" if r["backup"] else ""))
    print(f"  report  {r['report_path']}")
    print(f"  verified by re-reading the output: {counts['equal']} fields equal, {counts['normalized']} normalized, "
          f"{counts['unexpected']} unexpected")
    print(f"  compatibility: {len(c['safely_transformed'])} transformed, {len(c['defaulted'])} defaulted, "
          f"{len(c['unsupported_or_lossy'])} lossy/unsupported item(s) - details in the report")
    for w in c["warnings"]:
        print("  warning:", w)
    return 0


def cmd_verify(a):
    r = service.verify_files(a.source, a.converted, a.source_slot, a.converted_slot)
    sp, cp, counts = r["source_platform"], r["converted_platform"], r["counts"]
    print(f"verify {sp.upper()} {r['source']}  vs  {cp.upper()} {r['converted']}")
    for f in r["findings"]:
        if f["status"] != "equal" or a.verbose:
            print(f"  [{f['status']:10}] {f['field']}: {f['source']} -> {f['converted']}  {f['note']}")
    if sp != cp:
        print("  not compared (exist on one platform only): " + ", ".join(PC_ONLY_FIELDS[:5]) +
              ", PS1-only bytes (memory-card icon, unknown regions)")
    print(f"result: {counts['equal']} equal, {counts['normalized']} normalized (documented), {counts['unexpected']} unexpected")
    if a.json:
        with open(a.json, "x", encoding="utf-8") as fh:
            json.dump({"source": r["source"], "converted": r["converted"], "counts": counts, "findings": r["findings"]},
                      fh, indent=1, default=str)
    return 1 if counts["unexpected"] else 0


def _print_plan(plan):
    print(f"{plan.direction.upper().replace('->', ' -> ')}: {len(plan.assignments)} of {plan.source['count']} save(s) "
          f"from {plan.source['path']}")
    width = max([len(a.source_label) for a in plan.assignments] + [4])
    for x in plan.outputs:
        how = {"new": "new file", "copy": f"new copy of {x.based_on}", "in-place": "update in place (backup first)"}
        print(f"  {x.path}   ({how[plan.destination]})")
        for a in plan.assignments:
            if a.id in x.saves:
                s = a.summary
                c = a.counts or {}
                ver = f"verified {c['equal'] + c['normalized']} fields, {c['unexpected']} unexpected" if c else "not built"
                print(f"    {a.source_label:{width}} -> {a.dest_label:22} {s['location'] or '-'}, {s['playtime']}"
                      f"   [{ver}]")
                if a.note:
                    print(f"    {'':{width}}    note: {a.note}")
                for w in a.warnings:
                    print(f"    {'':{width}}    warning: {w}")
    for w in plan.warnings:
        print("  warning:", w)
    for r in plan.replacements:
        print("  replaces:", r)
    for p in plan.blocking():
        print("  PROBLEM:", p)


def cmd_batch(a):
    if a.in_place and not a.force:
        raise UserError("--in-place replaces your destination file; add --force to confirm (a verified backup is made)")
    mapping = None
    if a.map:
        mapping = {}
        for m in a.map:
            k, sep, v = m.partition("=")
            if not sep:
                raise UserError(f"--map takes SAVE=PLACE (e.g. 3=2/3 or 1/4=1/4), got {m!r}")
            mapping[k.strip()] = v.strip()
    o = batch.BatchOptions(input=a.input, select=a.select, into=a.into, in_place=a.in_place, out=a.out,
                           replace=a.replace, mapping=mapping, pc_slot=a.slot, layout=a.layout, region=a.region,
                           format=a.format, allow_lossy=a.allow_lossy, lenient=a.lenient, timestamp=a.timestamp)
    plan = batch.prepare(o)
    if a.json:
        print(json.dumps(plan.manifest(), indent=1, default=str))
    else:
        _print_plan(plan)
    if not plan.ok:
        print("error: nothing written; the problems above must be solved first (leave those saves out with --select)",
              file=sys.stderr)
        return 2
    if a.dry_run:
        print("dry run: everything converted and verified in memory; nothing written")
        return 0
    r = batch.commit(plan)
    for x in r["outputs"]:
        print(f"wrote {x['path']}" + (f"  (backup of the previous file: {x['backup']})" if x["backup"] else ""))
    print(f"report {r['report_path']}")
    if r["manifest_text_path"]:
        print(f"list   {r['manifest_text_path']}")
    return 0


def cmd_recover(a):
    found = batch.recover(a.folder)
    if not found:
        print(f"no interrupted conversion in {a.folder}")
        return 0
    bad = 0
    for j, res in found:
        print(f"{j}: undid {len(res['restored'])} file(s)" + "".join(f"\n  restored {p}" for p in res["restored"]))
        for p in res["problems"]:
            print(f"  PROBLEM: {p}")
            bad += 1
    return 2 if bad else 0


# ---- argument parsing --------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(prog="ffix-convert", description="Final Fantasy IX save converter: PS1 memory cards <-> PC (Steam 2016).",
                                 epilog="Slots/files/blocks are 1-based as in the game. Inputs are never modified.")
    ap.add_argument("--version", action="version", version=f"ffix-convert {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect", help="list the FF9 saves in a file")
    p.add_argument("file")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(fn=cmd_inspect)

    p = sub.add_parser("convert", help="convert one save to the other platform")
    p.add_argument("input")
    p.add_argument("--to", dest="dst", choices=["ps1", "pc"], help="target platform (default: the other one)")
    p.add_argument("--from", dest="src", choices=["ps1", "pc"], help="source platform (default: detected)")
    p.add_argument("--source", help="which save to convert: PS1 block number, or PC SLOT/FILE")
    p.add_argument("--out", help="output file (default: next to the input, a new name)")
    p.add_argument("--into", help="existing destination file to add the save to (it is copied, not changed)")
    p.add_argument("--dest", help="destination: PC SLOT/FILE, or PS1 FILE number 1-15")
    p.add_argument("--force", action="store_true", help="allow replacing an existing output file (verified backup first)")
    p.add_argument("--in-place", action="store_true", help="write into the --into file itself (needs --force)")
    p.add_argument("--report", help="report file (default: <output>.report.json)")
    p.add_argument("--lenient", action="store_true", help="downgrade CRC/region/name problems to warnings")
    g = p.add_argument_group("PS1 -> PC options")
    g.add_argument("--block", type=int, help="(same as --source) PS1 block")
    g.add_argument("--slot", type=int, default=1, help="PC destination slot 1-10 (default 1)")
    g.add_argument("--file", type=int, default=1, help="PC destination file 1-15 (default 1)")
    g.add_argument("--overwrite-slot", action="store_true", help="replace an occupied PC slot in the output")
    g.add_argument("--template", help="PC save to copy options/key bindings from")
    g.add_argument("--template-slot", default="1/1")
    g.add_argument("--timestamp", type=float, help=argparse.SUPPRESS)
    g = p.add_argument_group("PC -> PS1 options")
    g.add_argument("--pc-slot", help="(same as --source) PC SLOT/FILE")
    g.add_argument("--ps1-file", type=int, default=1, help="PS1 in-game file number FILEnn, 1-15 (default 1)")
    g.add_argument("--dest-block", type=int, help="memory-card block 1-15 (default: first free)")
    g.add_argument("--overwrite-block", action="store_true", help="replace an occupied single-block FF9 save")
    g.add_argument("--region", default="NTSC-U", choices=["NTSC-U", "PAL"])
    g.add_argument("--disc", type=int, help="override the disc derived from the story position")
    g.add_argument("--format", default="card", choices=["card", "mcs"], help="card (.mcr) or single-save .mcs")
    g.add_argument("--ps1-base", help="PS1 save of the SAME playthrough to take PS1-only bytes from")
    g.add_argument("--ps1-base-block", type=int)
    g = p.add_argument_group("Memoria / Moguri options")
    g.add_argument("--allow-lossy", action="store_true",
                   help="Memoria -> PS1 only: drop or clamp modded values (mod items, raised limits, mod script "
                        "storage) instead of refusing; every change is listed in the report")
    p.set_defaults(fn=cmd_convert)

    p = sub.add_parser("verify", help="independently compare a source save with its converted copy")
    p.add_argument("source")
    p.add_argument("converted")
    p.add_argument("--source-slot", help="PS1 block or PC SLOT/FILE in the source")
    p.add_argument("--converted-slot", help="PS1 block or PC SLOT/FILE in the converted file")
    p.add_argument("--verbose", "-v", action="store_true", help="also list equal fields")
    p.add_argument("--json", help="write findings to this new JSON file")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("batch", help="convert many saves at once (a whole memory card or PC file), all or nothing",
                       description="Converts every selected save, verifies all of them, and writes the result as one "
                                   "operation: either every output file is written or none is.")
    p.add_argument("input")
    p.add_argument("--select", nargs="+", metavar="ID", help="saves to convert (PS1 block numbers or PC SLOT/FILE, "
                                                             "as `inspect` lists them); default: all")
    p.add_argument("--out", help="PS1 -> PC: the new SavedData_ww.dat; PC -> PS1: a new folder for the cards "
                                 "(default: next to the input)")
    p.add_argument("--into", help="existing destination file (PC SavedData_ww.dat or raw PS1 card); a new copy with "
                                  "the saves added is written unless --in-place")
    p.add_argument("--in-place", action="store_true", help="update the --into file itself (needs --force)")
    p.add_argument("--force", action="store_true", help="confirm --in-place (a verified backup is made first)")
    p.add_argument("--replace", action="store_true", help="approve replacing occupied destination places")
    p.add_argument("--slot", type=int, help="PS1 -> PC: put the saves in this PC slot 1-10 (default: first empty)")
    p.add_argument("--map", nargs="+", metavar="SAVE=PLACE",
                   help="manual placement for every selected save: PLACE is SLOT/FILE (to PC) or CARD/FILE (to PS1)")
    p.add_argument("--layout", default="auto", choices=["auto", "by-slot", "compact"],
                   help="PC -> PS1: one card per PC slot keeping FILE numbers, or as few cards as possible (default: "
                        "keep numbers when all saves come from one slot)")
    p.add_argument("--region", default="NTSC-U", choices=["NTSC-U", "PAL"])
    p.add_argument("--format", default="card", choices=["card", "mcs"],
                   help="PC -> PS1: memory cards (.mcr), or one single-save .mcs file per save")
    p.add_argument("--allow-lossy", action="store_true", help="Memoria -> PS1: drop or clamp modded values")
    p.add_argument("--lenient", action="store_true", help="PS1 -> PC: accept saves with checksum/region/name problems")
    p.add_argument("--dry-run", action="store_true", help="convert and verify in memory, write nothing")
    p.add_argument("--json", action="store_true", help="print the plan as JSON")
    p.add_argument("--timestamp", type=float, help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_batch)

    p = sub.add_parser("recover", help="undo a batch conversion that was interrupted (power loss, crash)")
    p.add_argument("folder", help="the destination folder of the interrupted conversion")
    p.set_defaults(fn=cmd_recover)
    return ap


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except service.USER_ERRORS as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except PermissionError as e:
        print(f"error: permission denied: {e.filename or e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: not found: {e.filename or e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: invalid value: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
