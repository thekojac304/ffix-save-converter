"""One guarded action per call (so a human or agent inspects every screenshot in between).

  ff9_step.py <shots dir> title_load
  ff9_step.py <shots dir> keys Down Down [--wait 1.5]          (never X; Left/Right blocked on title)
  ff9_step.py <shots dir> confirm <screen>[,<screen>...]        (load_files, save_slots, save_files)
  ff9_step.py <shots dir> play <n> [--wait s]                    (n in-game confirms: dialogue/battle)
  ff9_step.py <shots dir> snap <label>
Exit 3 = guard abort (cloud screen / ambiguous / unexpected screen); nothing unsafe was pressed.
"""
import datetime
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import ff9_gui as g  # noqa: E402

# Reference screenshots of your own game (title menu, load screens) for the screen classifier. They are game
# imagery, so they are captured locally and never committed.
REFS = os.environ.get("FF9_REFS") or sys.exit("set FF9_REFS to your folder of reference screenshots")


def main(argv):
    shots, cmd, rest = argv[0], argv[1], argv[2:]
    os.makedirs(shots, exist_ok=True)
    logf = open(os.path.join(shots, "guard_log.txt"), "a", encoding="utf-8")

    def log(m):
        line = f"{datetime.datetime.now():%H:%M:%S} {m}"
        print(line)
        logf.write(line + "\n")
        logf.flush()

    wait = 1.0
    if "--wait" in rest:
        i = rest.index("--wait")
        wait = float(rest[i + 1])
        rest = rest[:i] + rest[i + 2:]
    guard = g.Guard(REFS, shots, log)
    guard.n = len([f for f in os.listdir(shots) if f.startswith("g")])
    log(f"== {cmd} {' '.join(rest)}")
    try:
        if cmd == "wait_title":
            # bring up the title menu: only Down is pressed (never confirm) until the guard
            # positively recognises the title menu
            for _ in range(int(rest[0]) if rest else 12):
                img = guard.snap("wait_title")
                if guard.v.classify(img)[1]["title"] > 0.9:
                    break
                g.press(guard.h, "Down")
                time.sleep(2.5)
            else:
                raise g.GuardAbort("title menu did not appear")
        elif cmd == "title_load":
            guard.title_select("LOAD GAME")
        elif cmd == "keys":
            img = guard.snap("before_keys")
            kind, s = guard.v.classify(img)
            if s["title"] > 0.8 and any(k in ("Left", "Right") for k in rest):
                raise g.GuardAbort("Left/Right are not allowed on the title menu")
            guard.keys("after_keys", *rest, wait=wait)
        elif cmd == "confirm":
            guard.confirm_on(set(rest[0].split(",")), "confirm")
        elif cmd == "play":
            for i in range(int(rest[0])):
                guard.confirm_ingame(f"play{i}", wait=wait)
            guard.snap("after_play")
        elif cmd == "snap":
            guard.snap(rest[0] if rest else "snap")
        else:
            raise SystemExit(f"unknown command {cmd}")
    except g.GuardAbort as e:
        log(f"GUARD ABORT: {e}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
