"""Single-save conversions: v0.2.0-dev baseline (snapshot) vs current source, byte for byte."""
import hashlib, os, shutil, subprocess, sys, tempfile, zipfile
ROOT = r"C:\Dev\FF9 Saves\FFIX-Save-Converter"
base = tempfile.mkdtemp(prefix="v02base-")
zipfile.ZipFile(os.path.join(ROOT, "snapshots", "v0.2.0-dev-source-baseline.zip")).extractall(base)
work = tempfile.mkdtemp(prefix="v02cmp-")
fx = os.path.join(ROOT, "fixtures")
cases = [
    ("ps1", os.path.join(fx, r"ps1\originals\user_retroarch\user_Final_Fantasy_IX.srm"), ["--source", "13", "--timestamp", "1700000000"]),
    ("ps1", os.path.join(fx, r"ps1\originals\user_retroarch\user_Final_Fantasy_IX-01.srm"), ["--source", "1", "--dest", "3/7", "--timestamp", "1700000000"]),
    ("pc", os.path.join(fx, r"pc\originals\steam\steam_cd3thread_SavedData_ww.dat"), ["--source", "2/3"]),
    ("pc", os.path.join(fx, r"pc\originals\steam\steam_cd3thread_SavedData_ww.dat"), ["--source", "4/1", "--format", "mcs", "--dest", "9"]),
    ("mem", os.path.join(fx, r"memoria\runtime_20261106\native_save\SavedData_ww.dat"), ["--source", "1/2"]),
    ("mem", os.path.join(fx, r"memoria\runtime_20261106\sidecar_cases\SavedData_ww.dat"), ["--source", "1/4", "--allow-lossy"]),
]
ok = True
for i, (kind, src, args) in enumerate(cases):
    hashes = []
    for label, srcdir in (("v0.2", os.path.join(base, "src")), ("v0.3", os.path.join(ROOT, "src"))):
        d = os.path.join(work, f"{i}-{label}")
        if kind == "mem":
            shutil.copytree(os.path.dirname(src), d)
            inp = os.path.join(d, "SavedData_ww.dat")
        else:
            os.makedirs(d)
            inp = shutil.copy(src, d)
        out = os.path.join(d, "out" + (".mcs" if "mcs" in args else ".mcr" if kind != "ps1" else ".dat"))
        r = subprocess.run([sys.executable, "-P", "-m", "ffix_conv", "convert", inp, "--out", out, *args],
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": srcdir}, cwd=work)
        if r.returncode:
            print(label, "FAILED", r.stderr)
        hashes.append(hashlib.sha256(open(out, "rb").read()).hexdigest() if os.path.exists(out) else None)
    same = hashes[0] == hashes[1] and hashes[0]
    ok &= bool(same)
    print(f"{'SAME' if same else 'DIFF'}  {kind} {os.path.basename(src)} {' '.join(args)}  {hashes[0][:16] if hashes[0] else None}")
print("ALL IDENTICAL" if ok else "DIFFERENCES FOUND")
