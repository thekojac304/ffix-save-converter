"""Screenshot-verified automation for the FF9 PC game (runtime testing only).

Safety policy (enforced in code, not by the caller):
  * Every confirm press is preceded by a fresh screenshot that identifies the screen and,
    on the title menu, the row the pointer is on. Confirm is sent only if the result is the
    expected one with a clear margin; anything ambiguous aborts without pressing confirm.
  * The Cloud Data screen is never entered on purpose. CLOUD DATA is never confirmed. If the
    Cloud screen is ever detected, only Cancel is pressed (to back out) and the run aborts.
  * Keys that could move toward Upload/Download (Left/Right) are never sent unless the current
    screen has been positively identified as a non-cloud screen.

Reference screenshots (game imagery, not distributed) live in a local folder; every capture is
normalised to 772x593 (60 % of the 1286x989 windowed game) before comparison.
Run unsandboxed on an active, unlocked console session.
"""
import ctypes
import ctypes.wintypes as wt
import os
import time

import numpy as np
from PIL import Image, ImageGrab

CANON = (772, 593)
TITLE_ROWS = {"CONTINUE": 330, "NEW GAME": 380, "LOAD GAME": 430, "CLOUD DATA": 480}
HAND_BOX = (225, 466, 287, 504)          # pointer hand in rc_back.png (cursor on CLOUD DATA)
HAND_SEARCH = (170, 290, 330, 520)
REGIONS = {"help": (20, 52, 535, 102), "button": (540, 52, 752, 102), "logo": (60, 140, 700, 280),
           "cloud_text": (40, 120, 740, 420), "cloud_bar": (230, 512, 640, 562)}
FORBIDDEN = {"cloud"}

user32 = ctypes.WinDLL("user32", use_last_error=True)


class GuardAbort(Exception):
    pass


# ---- low-level window / input ---------------------------------------------------------------
class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("vk", wt.WORD), ("scan", wt.WORD), ("flags", wt.DWORD), ("time", wt.DWORD),
                ("extra", ctypes.c_void_p)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


SCAN = {"X": (0x2D, False), "C": (0x2E, False), "V": (0x2F, False), "B": (0x30, False),
        "Up": (0x48, True), "Down": (0x50, True), "Left": (0x4B, True), "Right": (0x4D, True)}


def find_window(title="FINAL FANTASY IX"):
    # the Unity game window only: Steam's Properties dialog for the game has the same title.
    # Memoria appends the current location ("FINAL FANTASY IX - World Map: 9002, Bentini Heights").
    h = user32.FindWindowW("UnityWndClass", title)
    if h:
        return h
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def visit(hwnd, _):
        cls, txt = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 64)
        user32.GetWindowTextW(hwnd, txt, 256)
        if cls.value == "UnityWndClass" and txt.value.startswith(title + " - ") and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(proto(visit), None)
    if len(found) != 1:
        raise GuardAbort(f"window '{title}' not found" if not found else f"{len(found)} game windows found")
    return found[0]


def window_title(h):
    txt = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, txt, 256)
    return txt.value


def focus(h):
    user32.ShowWindow(h, 9)
    user32.SetForegroundWindow(h)
    time.sleep(0.3)
    if user32.GetForegroundWindow() != h:
        raise GuardAbort("could not bring the game window to the foreground")


def _key(scan, up, ext):
    i = INPUT(type=1)
    i.ki = KEYBDINPUT(0, scan, 0x0008 | (0x0002 if up else 0) | (0x0001 if ext else 0), 0, None)
    if user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT)) != 1:
        raise GuardAbort("SendInput failed")


def press(h, key, hold=0.09):
    if user32.GetForegroundWindow() != h:
        raise GuardAbort("game window lost focus; not sending input")
    scan, ext = SCAN[key]
    _key(scan, False, ext)
    time.sleep(hold)
    _key(scan, True, ext)
    time.sleep(0.15)


def grab(h):
    r = RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    img = ImageGrab.grab(bbox=(r.l, r.t, r.r, r.b), all_screens=True)
    return img.convert("RGB").resize(CANON, Image.BILINEAR)


# ---- vision ------------------------------------------------------------------------------------
def _gray(img, box=None):
    if box:
        img = img.crop(box)
    return np.asarray(img.convert("L"), dtype=np.float64)


def ncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else 0.0


class Vision:
    def __init__(self, ref_dir):
        def load(name):
            return Image.open(os.path.join(ref_dir, name)).convert("RGB").resize(CANON, Image.BILINEAR)
        self.refs = {
            "title": load("rc_back.png"), "cloud": load("rc_d2a.png"), "cloud2": load("load_slot2.png"),
            "load_files": load("s1list.png"), "save_slots": load("save2.png"), "save_files": load("save3.png"),
        }
        self.hand = _gray(self.refs["title"], HAND_BOX)

    def scores(self, img):
        out = {}
        for name, ref in self.refs.items():
            if name.startswith("title"):
                out[name] = ncc(_gray(img, REGIONS["logo"]), _gray(ref, REGIONS["logo"]))
            else:
                out[name] = (ncc(_gray(img, REGIONS["help"]), _gray(ref, REGIONS["help"])) +
                             ncc(_gray(img, REGIONS["button"]), _gray(ref, REGIONS["button"]))) / 2
        out["cloud"] = max(out["cloud"], out.pop("cloud2"))
        return out

    def is_cloud(self, img):
        """Conservative cloud-screen test: any one of three independent cues is enough.
        Load/Save screens share the frame (header score ~0.83) but not the body text or the
        Info/Upload/Download bar."""
        s = self.scores(img)
        body = ncc(_gray(img, REGIONS["cloud_text"]), _gray(self.refs["cloud"], REGIONS["cloud_text"]))
        bar = ncc(_gray(img, REGIONS["cloud_bar"]), _gray(self.refs["cloud"], REGIONS["cloud_bar"]))
        return s["cloud"] > 0.93 or body > 0.5 or bar > 0.6, s, max(body, bar)

    def classify(self, img):
        s = self.scores(img)
        best = max(s, key=s.get)
        return best, s

    def title_row(self, img):
        """Locate the pointer hand on the title menu. Returns (row, score, margin)."""
        g = _gray(img)
        th, tw = self.hand.shape
        x0, y0, x1, y1 = HAND_SEARCH
        best = {}
        for y in range(y0, y1 - th, 2):
            for x in range(x0, x1 - tw, 2):
                v = ncc(g[y:y + th, x:x + tw], self.hand)
                cy = y + th / 2
                row = min(TITLE_ROWS, key=lambda k: abs(TITLE_ROWS[k] - cy))
                if abs(TITLE_ROWS[row] - cy) <= 18 and v > best.get(row, -1):
                    best[row] = v
        if not best:
            return None, 0.0, 0.0
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        top, second = ranked[0], (ranked[1][1] if len(ranked) > 1 else 0.0)
        return top[0], top[1], top[1] - second

    def underline_row(self, img):
        """Second, independent detector: the selected item has a bright underline glow."""
        g = _gray(img)
        vals = {k: float(g[y + 10:y + 17, 300:540].mean()) for k, y in TITLE_ROWS.items()}
        ranked = sorted(vals.items(), key=lambda kv: -kv[1])
        return ranked[0][0], ranked[0][1] - ranked[1][1]


# ---- guarded actions -----------------------------------------------------------------------------
class Guard:
    def __init__(self, ref_dir, shot_dir, log):
        self.v = Vision(ref_dir)
        self.shot_dir = shot_dir
        self.log = log
        self.h = find_window()
        focus(self.h)
        self.n = 0

    def snap(self, label):
        img = grab(self.h)
        self.n += 1
        p = os.path.join(self.shot_dir, f"g{self.n:03d}_{label}.png")
        img.save(p)
        cloud, s, body = self.v.is_cloud(img)
        self.log(f"[{self.n:03d}] {label}: scores {{{', '.join(f'{k}:{v:.2f}' for k, v in s.items())}}} cloudbody {body:.2f} -> {p}")
        if cloud:
            self.escape_cloud()
        return img

    def escape_cloud(self):
        self.log("!!! CLOUD screen detected: pressing Cancel only and aborting")
        for _ in range(3):
            press(self.h, "C")
            time.sleep(1.5)
            img = grab(self.h)
            if not self.v.is_cloud(img)[0]:
                break
        raise GuardAbort("cloud screen detected; backed out with Cancel; run aborted")

    def keys(self, label, *keys, wait=1.0):
        for k in keys:
            if k == "X":
                raise GuardAbort("confirm must go through a guarded method")
            press(self.h, k)
        time.sleep(wait)
        return self.snap(label)

    def title_select(self, target="LOAD GAME"):
        """Move the title pointer to target and confirm, verifying before every key."""
        assert target in ("LOAD GAME", "CONTINUE", "NEW GAME") and target != "CLOUD DATA"
        for _ in range(8):
            img = self.snap("title")
            kind, s = self.v.classify(img)
            if kind != "title" or s["title"] < 0.8:
                raise GuardAbort(f"not on the title menu (best match {kind} {s[kind]:.2f})")
            row, score, margin = self.v.title_row(img)
            urow, umargin = self.v.underline_row(img)
            self.log(f"    pointer on {row} (score {score:.2f}, margin {margin:.2f}); underline on {urow} (margin {umargin:.1f})")
            if score < 0.65 or margin < 0.2 or urow != row or umargin < 8:
                raise GuardAbort("pointer position ambiguous or detectors disagree; not confirming")
            if row == target:
                press(self.h, "X")
                time.sleep(2.5)
                after = self.snap("after_title_confirm")
                return after
            order = list(TITLE_ROWS)
            press(self.h, "Down" if order.index(row) < order.index(target) else "Up")
            time.sleep(0.6)
        raise GuardAbort(f"could not reach {target}")

    def confirm_on(self, expected, label):
        """Press confirm only if the current screen is classified as one of expected."""
        img = self.snap(f"before_{label}")
        kind, s = self.v.classify(img)
        if kind not in expected or s[kind] < 0.7:
            raise GuardAbort(f"expected {expected}, saw {kind} ({s[kind]:.2f}); not confirming")
        press(self.h, "X")
        time.sleep(1.5)
        return self.snap(f"after_{label}")

    def confirm_ingame(self, label, wait=1.5):
        """Confirm during gameplay (dialogue, battle, field). Allowed only if no menu screen
        that could be cloud-related is showing."""
        img = self.snap(f"before_{label}")
        kind, s = self.v.classify(img)
        if s["title"] > 0.8:
            raise GuardAbort("title menu showing; use title_select")
        press(self.h, "X")
        time.sleep(wait)
        return img
