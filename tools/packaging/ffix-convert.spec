# PyInstaller spec for the standalone Windows x64 executable.
# Build:  python -m PyInstaller tools/packaging/ffix-convert.spec --distpath <dist> --workpath <work> --noconfirm --clean
# Requires Windows 10/11 (the Universal C Runtime is part of the OS, so the api-ms-win-* / ucrtbase
# DLLs that PyInstaller may find on PATH are deliberately left out).
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

a = Analysis(
    [os.path.join(ROOT, "tools", "packaging", "ffix_convert_entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    excludes=["tkinter", "pytest", "unittest", "pydoc", "_ssl", "ssl", "email", "http", "urllib", "xml",
              "xmlrpc", "asyncio", "multiprocessing", "sqlite3", "lib2to3"],
    noarchive=False,
)
drop = ("api-ms-win-", "ucrtbase.dll", "libssl-3.dll")
a.binaries = [b for b in a.binaries if not os.path.basename(b[0]).lower().startswith(drop)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="ffix-convert", console=True, upx=False, strip=False, debug=False,
)
