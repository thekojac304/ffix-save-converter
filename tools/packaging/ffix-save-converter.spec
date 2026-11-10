# PyInstaller spec for the v0.2 Windows x64 build: the desktop app and the command line, sharing one runtime.
# Build:  python -m PyInstaller tools/packaging/ffix-save-converter.spec --distpath <dist> --workpath <work> --noconfirm --clean
# Output: <dist>/FFIX Save Converter/ with "FFIX Save Converter.exe" (GUI), "ffix-convert.exe" (CLI) and _internal/.
# A folder build, not one file: Qt is LGPL-3.0, and its DLLs stay separate files that a user can replace.
# Requires Windows 10/11 (the Universal C Runtime is part of the OS and is deliberately left out).
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from ffix_conv import __version__  # noqa: E402

# the icon is drawn in code (ffix_conv/gui/icon.py); render it to an .ico for the executables
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QGuiApplication  # noqa: E402
_app = QGuiApplication.instance() or QGuiApplication([])
from ffix_conv.gui import icon  # noqa: E402
ICO = os.path.join(workpath, "ffix-save-converter.ico")
os.makedirs(workpath, exist_ok=True)
icon.write_ico(ICO)

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,  # noqa: E402
                                                VarFileInfo, VarStruct, VSVersionInfo)
nums = tuple(int(x) for x in __version__.split("-")[0].split(".")) + (0,)


def version_info(description, name):
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "thekojac"),
            StringStruct("FileDescription", description),
            StringStruct("FileVersion", __version__),
            StringStruct("InternalName", name),
            StringStruct("LegalCopyright", "Copyright (c) 2026 thekojac. MIT License."),
            StringStruct("OriginalFilename", name + ".exe"),
            StringStruct("ProductName", "FFIX Save Converter"),
            StringStruct("ProductVersion", __version__)])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])


EXCLUDES = ["tkinter", "pytest", "unittest", "pydoc", "_ssl", "ssl", "email", "http", "urllib", "xml", "xmlrpc",
            "asyncio", "multiprocessing", "sqlite3", "lib2to3",
            "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL", "PySide6.QtSvg",
            "PySide6.QtPrintSupport", "PySide6.QtSql", "PySide6.QtDBus", "PySide6.QtConcurrent", "PySide6.QtXml"]

gui = Analysis([os.path.join(ROOT, "tools", "packaging", "ffix_gui_entry.py")], pathex=[os.path.join(ROOT, "src")],
               excludes=EXCLUDES, noarchive=False)
cli = Analysis([os.path.join(ROOT, "tools", "packaging", "ffix_convert_entry.py")], pathex=[os.path.join(ROOT, "src")],
               excludes=EXCLUDES + ["PySide6", "shiboken6"], noarchive=False)

# Trim what a widgets-only, English-only app never loads.
DROP_FILES = ("api-ms-win-", "ucrtbase.dll", "libssl-3.dll", "opengl32sw.dll", "qt6network", "qt6svg", "qt6qml",
              "qt6quick", "qt6opengl", "qt6pdf", "qt6virtualkeyboard", "d3dcompiler")
DROP_DIRS = ("translations", "iconengines", "networkinformation", "tls", "qmltooling", "sqldrivers", "designer",
             "vectorimageformats", "platforminputcontexts", "generic")
KEEP_IMAGEFORMATS = ("qico.dll",)


def keep(entry):
    dest = entry[0].replace("\\", "/").lower()
    base = os.path.basename(dest)
    if base.startswith(DROP_FILES):
        return False
    parts = dest.split("/")
    if "pyside6" in parts and any(d in parts for d in DROP_DIRS):
        return False
    if "imageformats" in parts and base not in KEEP_IMAGEFORMATS:
        return False
    if "platforms" in parts and base != "qwindows.dll":
        return False
    # PyInstaller's dependency scan also copies the Qt DLLs to the top folder; PySide6 loads its own copies
    if len(parts) == 1 and base.startswith("qt6") and base.endswith(".dll"):
        return False
    return True


for a in (gui, cli):
    a.binaries = [b for b in a.binaries if keep(b)]
    a.datas = [d for d in a.datas if keep(d)]

gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="FFIX Save Converter", console=False,
              icon=ICO, version=version_info("FFIX Save Converter", "FFIX Save Converter"), upx=False, strip=False)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="ffix-convert", console=True,
              icon=ICO, version=version_info("FFIX Save Converter (command line)", "ffix-convert"), upx=False,
              strip=False)
coll = COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas, name="FFIX Save Converter",
               upx=False, strip=False)
