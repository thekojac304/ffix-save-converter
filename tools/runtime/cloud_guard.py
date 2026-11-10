"""Baseline and verification of everything the PC runtime tests must not disturb.

  python -P tools/runtime/cloud_guard.py baseline <out.json>
  python -P tools/runtime/cloud_guard.py check <baseline.json>

Records SHA-256 (and the SHA-1 Steam uses) of the local FF9 cloud file, Steam's remote-cache
entry for app 377840, the per-app "cloud" settings for 377840 in Steam's local/shared config
(only that small subtree - the config files also hold login tickets and are never copied),
any extra files named in FF9_PROTECTED (os.pathsep-separated, e.g. your emulator memory cards), and the
game's local save folder listing.

Settings (environment): STEAM_DIR (default: the standard Steam folder), STEAM_ACCOUNT_ID (default: the only
userdata account that has app 377840), FF9_PROTECTED.
"""
import hashlib
import json
import os
import re
import sys

STEAM = os.environ.get("STEAM_DIR", r"C:\Program Files (x86)\Steam")
APP = "377840"


def _account():
    if os.environ.get("STEAM_ACCOUNT_ID"):
        return os.environ["STEAM_ACCOUNT_ID"]
    root = os.path.join(STEAM, "userdata")
    ids = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d, APP))] if os.path.isdir(root) else []
    if len(ids) != 1:
        raise SystemExit(f"set STEAM_ACCOUNT_ID: found {len(ids)} Steam accounts with app {APP}")
    return ids[0]


ACCOUNT = _account()
HOME = os.path.expanduser("~")
CLOUD_FILE = os.path.join(HOME, r"Documents\Square Enix\FINAL FANTASY IX\FF9_CloudSaveFile_ww.sav")
REMOTECACHE = os.path.join(STEAM, "userdata", ACCOUNT, APP, "remotecache.vdf")
LOCALCONFIG = os.path.join(STEAM, "userdata", ACCOUNT, "config", "localconfig.vdf")
SHAREDCONFIG = os.path.join(STEAM, "userdata", ACCOUNT, "7", "remote", "sharedconfig.vdf")
PROTECTED = [p for p in os.environ.get("FF9_PROTECTED", "").split(os.pathsep) if p]


def h(path, algo="sha256"):
    with open(path, "rb") as f:
        return hashlib.new(algo, f.read()).hexdigest()


def app_block(path):
    """The '377840' { ... } block(s) under Software/Valve/Steam/apps, as text (no tickets)."""
    if not os.path.exists(path):
        return None
    t = open(path, encoding="utf-8", errors="replace").read()
    i = t.find('"apps"')
    if i < 0:
        return None
    m = re.search(r'"' + APP + r'"\s*\{', t[i:])
    if not m:
        return ""
    start = i + m.start()
    depth, j = 0, i + m.end() - 1
    while j < len(t):
        depth += t[j] == "{"
        depth -= t[j] == "}"
        if depth == 0:
            break
        j += 1
    return re.sub(r"\s+", " ", t[start:j + 1])


def snapshot():
    snap = {
        "cloud_file": {"path": CLOUD_FILE, "sha256": h(CLOUD_FILE), "sha1": h(CLOUD_FILE, "sha1"),
                       "mtime": os.path.getmtime(CLOUD_FILE)},
        "cloud_dir": sorted(os.listdir(os.path.dirname(CLOUD_FILE))),
        "remotecache": open(REMOTECACHE, encoding="utf-8").read() if os.path.exists(REMOTECACHE) else None,
        "localconfig_app": app_block(LOCALCONFIG),
        "sharedconfig_app": app_block(SHAREDCONFIG),
        "protected": {p: h(p) for p in PROTECTED if os.path.exists(p)},
    }
    m = re.search(r'"sha"\s+"([0-9a-f]+)"', snap["remotecache"] or "")
    snap["cloud_file"]["matches_steam_cloud"] = bool(m and m.group(1) == snap["cloud_file"]["sha1"])
    return snap


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    s = snapshot()
    if cmd == "baseline":
        with open(path, "x", encoding="utf-8") as f:
            json.dump(s, f, indent=1)
        print(json.dumps({k: v for k, v in s.items() if k != "remotecache"}, indent=1))
        return 0
    base = json.load(open(path, encoding="utf-8"))
    problems = []
    if s["cloud_file"]["sha256"] != base["cloud_file"]["sha256"]:
        problems.append("LOCAL FF9 CLOUD FILE CHANGED")
    if s["remotecache"] != base["remotecache"]:
        problems.append("Steam remotecache for 377840 changed")
    for p, v in base["protected"].items():
        if s["protected"].get(p) != v:
            problems.append(f"protected file changed: {p}")
    print("cloud file sha256:", s["cloud_file"]["sha256"], "| matches Steam cloud record:", s["cloud_file"]["matches_steam_cloud"])
    print("localconfig 377840:", s["localconfig_app"])
    print("sharedconfig 377840:", s["sharedconfig_app"])
    if s["localconfig_app"] != base["localconfig_app"] or s["sharedconfig_app"] != base["sharedconfig_app"]:
        print("note: per-app Steam settings differ from baseline (expected while cloud is disabled for the test)")
    print("PROBLEMS:" if problems else "OK: protected data unchanged", "; ".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
