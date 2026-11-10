"""Inspect and safely extract downloaded zip archives (untrusted input).

Usage: python -I tools/safe_extract.py <archive_dir> <extract_root> <report.json>

Each archive is extracted into <extract_root>/<archive stem>/ only if every
entry passes the checks below; otherwise the archive is rejected whole.
"""
import hashlib
import json
import os
import stat
import sys
import zipfile

MAX_ENTRIES = 32
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_RATIO = 200
ALLOWED_EXT = {".mcr", ".mcd", ".srm", ".gme", ".psv", ".mcs", ".mc", ".vmp", ".bin",
               ".dat", ".sav", ".ps1", ".vm1", ".ddf", ".txt", ".nfo", ".mem", ".vgs"}


def check_entry(info):
    name = info.filename
    if name.startswith(("/", "\\")) or ":" in name:
        return "absolute or drive path"
    parts = name.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        return "path traversal"
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return "symlink entry"
    if info.flag_bits & 0x1:
        return "encrypted entry"
    if info.file_size > MAX_ENTRY_BYTES:
        return "entry too large"
    if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
        return "suspicious compression ratio"
    if not name.endswith("/"):
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_EXT:
            return f"unexpected extension {ext!r}"
    return None


def extract(archive, out_root):
    rec = {"archive": os.path.basename(archive), "entries": [], "ok": False}
    with open(archive, "rb") as f:
        rec["archive_sha256"] = hashlib.sha256(f.read()).hexdigest()
    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as e:
        rec["error"] = f"not a zip: {e}"
        return rec
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            rec["error"] = "too many entries"
            return rec
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            rec["error"] = "total uncompressed size too large"
            return rec
        for i in infos:
            problem = check_entry(i)
            rec["entries"].append({"name": i.filename, "size": i.file_size, "problem": problem})
            if problem:
                rec["error"] = f"rejected: {i.filename}: {problem}"
                return rec
        dest = os.path.join(out_root, os.path.splitext(os.path.basename(archive))[0])
        os.makedirs(dest, exist_ok=True)
        for i in infos:
            if i.filename.endswith("/"):
                continue
            # flatten: never trust directory components from the archive
            target = os.path.join(dest, os.path.basename(i.filename.replace("\\", "/")))
            data = zf.read(i)
            if len(data) != i.file_size:
                rec["error"] = "size mismatch after decompression"
                return rec
            if os.path.exists(target):
                with open(target, "rb") as f:
                    if f.read() != data:
                        rec["error"] = f"refusing to overwrite differing {target}"
                        return rec
            else:
                with open(target, "xb") as f:
                    f.write(data)
            for e in rec["entries"]:
                if e["name"] == i.filename:
                    e.update(extracted_to=os.path.relpath(target, out_root).replace("\\", "/"),
                             sha256=hashlib.sha256(data).hexdigest())
    rec["ok"] = True
    return rec


def main(archive_dir, out_root, report_path):
    report = [extract(os.path.join(archive_dir, n), out_root)
              for n in sorted(os.listdir(archive_dir)) if n.lower().endswith(".zip")]
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    bad = [r for r in report if not r["ok"]]
    print(f"{len(report)} archives, {len(bad)} rejected")
    for r in bad:
        print("  REJECTED", r["archive"], r.get("error"))


if __name__ == "__main__":
    main(*sys.argv[1:4])
