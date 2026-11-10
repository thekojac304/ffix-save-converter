"""Safe file handling for conversions.

Rules:
  * sources are only ever opened for reading;
  * outputs are written to a temporary file in the destination folder, validated by
    re-parsing, then moved into place atomically; an existing file is never replaced
    unless the caller passes force=True, and then only after a verified backup and a
    check that the destination did not change since it was read;
  * two paths are "the same file" if they resolve to the same real path (symlinks,
    junctions, ".." and case) or are hard links to the same file (os.path.samefile).
"""
import datetime
import hashlib
import json
import os
import shutil
import tempfile
import uuid


class SafetyError(Exception):
    """A safety rule prevented the operation. Nothing was written."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_source(path):
    """Read a whole input file; clean errors for the usual problems."""
    if not os.path.exists(path):
        raise SafetyError(f"input file not found: {path}")
    if os.path.isdir(path):
        raise SafetyError(f"input is a folder, not a save file: {path}")
    try:
        with open(path, "rb") as f:
            return f.read()
    except PermissionError as e:
        raise SafetyError(f"cannot read {path}: permission denied") from e


def _real(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def same_file(a, b):
    """True if a and b are, or would be, the same file on disk."""
    if _real(a) == _real(b):
        return True
    try:
        return os.path.exists(a) and os.path.exists(b) and os.path.samefile(a, b)
    except OSError:
        return False


def check_distinct(dest, *sources):
    for s in sources:
        if s and same_file(dest, s):
            raise SafetyError(f"destination {dest} is the same file as source {s} "
                              "(directly or through a link); refusing to write")


def backup(path):
    """Copy path to path.bak-<timestamp> and verify the copy byte-for-byte. Returns the backup path."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = f"{path}.bak-{stamp}"
    n = 1
    while os.path.exists(dst):
        dst = f"{path}.bak-{stamp}-{n}"
        n += 1
    shutil.copy2(path, dst)
    with open(path, "rb") as a, open(dst, "rb") as b:
        if sha256(a.read()) != sha256(b.read()):
            raise SafetyError(f"backup verification failed for {dst}")
    return dst


def write_output(dest, data, validate, *, sources=(), force=False, expected_sha256=None, create_dir=False):
    """Write data to dest safely.

    validate(bytes) must raise if the data is not a valid file of the intended type.
    force=False: dest must not exist (atomic no-clobber).
    force=True:  dest may exist; it is backed up (verified) first, and if expected_sha256
                 is given the current dest content must still match it.
    Returns {"path", "sha256", "backup"}.
    """
    check_distinct(dest, *sources)
    validate(data)
    folder = os.path.dirname(os.path.abspath(dest)) or "."
    if create_dir and not os.path.isdir(folder):
        os.makedirs(folder)
    if not os.path.isdir(folder):
        raise SafetyError(f"destination folder does not exist: {folder}")
    exists = os.path.lexists(dest)
    if exists and not force:
        raise SafetyError(f"{dest} already exists; refusing to overwrite (use --force to replace it, "
                          "a verified backup is made first)")
    if exists and os.path.isdir(dest):
        raise SafetyError(f"destination is a folder: {dest}")
    bak = None
    if exists:
        with open(dest, "rb") as f:
            current = f.read()
        if expected_sha256 is not None and sha256(current) != expected_sha256:
            raise SafetyError(f"{dest} changed since it was read (another program wrote to it?); nothing written")
        if not os.access(dest, os.W_OK):
            raise SafetyError(f"{dest} is read-only; nothing written")
        bak = backup(dest)
    tmp = None
    try:
        tmp = _stage(folder, data, validate)
        _place(tmp, dest, exists)
    except PermissionError as e:
        raise SafetyError(f"cannot write {dest}: permission denied") from e
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    return {"path": dest, "sha256": sha256(data), "backup": bak}


def _stage(folder, data, validate):
    """Write data to a new temporary file in folder, read it back and validate it. Returns the temp path."""
    fd, tmp = tempfile.mkstemp(prefix=".ffix-tmp-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, "rb") as f:
            written = f.read()
        if written != data:
            raise SafetyError("written data did not read back identically; nothing replaced")
        validate(written)
    except BaseException:
        os.unlink(tmp)
        raise
    return tmp


def _place(tmp, dest, replace):
    """Move a staged file into place atomically; a new file never overwrites one that appeared meanwhile."""
    if replace:
        os.replace(tmp, dest)
        return
    try:
        os.link(tmp, dest)          # atomic and fails if dest appeared meanwhile
        os.unlink(tmp)
    except FileExistsError as e:
        raise SafetyError(f"{dest} appeared while writing; refusing to overwrite") from e
    except OSError:
        if os.path.lexists(dest):
            raise SafetyError(f"{dest} appeared while writing; refusing to overwrite")
        os.rename(tmp, dest)        # Windows rename never overwrites


def file_sha(path):
    try:
        with open(path, "rb") as f:
            return sha256(f.read())
    except OSError:
        return None


# ---- several files as one operation ------------------------------------------------------------
JOURNAL_PREFIX = ".ffix-journal-"


class Cancelled(Exception):
    """The operation was cancelled; every destination file is as it was before."""


def find_journals(folder):
    """Journals of interrupted transactions left in folder (see Transaction)."""
    try:
        return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                      if n.startswith(JOURNAL_PREFIX) and n.endswith(".json"))
    except OSError:
        return []


def _write_journal(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Transaction:
    """Write several files so that, as far as the user can tell, either all of them change or none does.

    No filesystem replaces several files atomically, so the steps are explicit:
      1. check every destination (new files must not exist, replaced files must still hold what was read);
      2. make a verified backup of every file that will be replaced;
      3. stage every file next to its destination, read it back and validate it;
      4. write a journal, then move the files into place one by one, recording each move;
      5. re-read every destination and compare its SHA-256 with what was staged.
    If anything fails or is cancelled at step 4 or 5, every file already moved is undone (new files removed, replaced
    files restored from their backups, both checked by SHA-256) and the error is raised; nothing is left half-done.
    If the process itself dies during step 4, the journal stays behind and recover() undoes the moves.
    Backups of replaced files are kept after a successful commit."""

    def __init__(self, sources=()):
        self.sources = tuple(s for s in sources if s)
        self.entries = []

    def add(self, dest, data, validate=lambda b: None, *, replace=False, expected_sha256=None, create_dir=False):
        """data may be bytes, or a function backups -> bytes, called after the backups exist ({dest: backup})."""
        self.entries.append({"dest": os.path.abspath(dest), "data": data, "validate": validate, "replace": replace,
                             "expected": expected_sha256, "create_dir": create_dir})

    def commit(self, cancel=None, progress=None):
        cancel = cancel or (lambda: False)
        progress = progress or (lambda done, total, text: None)
        es = self.entries
        if not es:
            raise SafetyError("nothing to write")
        seen = set()
        for e in es:
            key = _real(e["dest"])
            if key in seen:
                raise SafetyError(f"{e['dest']} would be written twice in one operation")
            seen.add(key)
            check_distinct(e["dest"], *self.sources)
            e["existed"] = os.path.lexists(e["dest"])
            if e["existed"] and os.path.isdir(e["dest"]):
                raise SafetyError(f"destination is a folder: {e['dest']}")
            if e["existed"] and not e["replace"]:
                raise SafetyError(f"{e['dest']} already exists; refusing to overwrite it")
            if e["existed"]:
                cur = file_sha(e["dest"])
                if e["expected"] is not None and cur != e["expected"]:
                    raise SafetyError(f"{e['dest']} changed since it was read (another program wrote to it?); "
                                      "nothing written")
                if not os.access(e["dest"], os.W_OK):
                    raise SafetyError(f"{e['dest']} is read-only; nothing written")
                e["old_sha"] = cur
            elif e["expected"] is not None:
                raise SafetyError(f"{e['dest']} disappeared since it was read; nothing written")
            folder = os.path.dirname(e["dest"])
            if not os.path.isdir(folder) and not e["create_dir"]:
                raise SafetyError(f"destination folder does not exist: {folder}")
        if cancel():
            raise Cancelled("cancelled; nothing was written")

        created_dirs, backups, staged = [], {}, []
        journal = None
        total = len(es)

        def abort_before_commit():
            for e in staged:
                if e.get("tmp") and os.path.exists(e["tmp"]):
                    os.unlink(e["tmp"])
            for e in es:                                   # nothing was replaced: the backups are redundant copies
                b = e.get("backup")
                if b and file_sha(b) == e.get("old_sha") and file_sha(e["dest"]) == e.get("old_sha"):
                    os.unlink(b)
            if journal and os.path.exists(journal):
                os.unlink(journal)
            _rmdirs(created_dirs)

        try:
            for e in es:
                folder = os.path.dirname(e["dest"])
                missing = []
                while not os.path.isdir(folder):
                    missing.append(folder)
                    folder = os.path.dirname(folder)
                for d in reversed(missing):
                    os.mkdir(d)
                    created_dirs.append(d)
            for e in es:
                if e["existed"]:
                    e["backup"] = backup(e["dest"])
                    backups[e["dest"]] = e["backup"]
            for i, e in enumerate(es):
                if cancel():
                    raise Cancelled("cancelled")
                progress(i, total, f"checking {os.path.basename(e['dest'])}")
                data = e["data"](dict(backups)) if callable(e["data"]) else e["data"]
                e["validate"](data)
                e["new_sha"] = sha256(data)
                e["tmp"] = _stage(os.path.dirname(e["dest"]), data, e["validate"])
                staged.append(e)
            if cancel():
                raise Cancelled("cancelled")
            journal = os.path.join(os.path.dirname(es[0]["dest"]),
                                   f"{JOURNAL_PREFIX}{datetime.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.json")
            state = {"version": 1, "tool": "ffix-convert", "dirs_created": created_dirs,
                     "entries": [{k: e.get(k) for k in ("dest", "tmp", "existed", "old_sha", "new_sha", "backup")}
                                 | {"committed": False} for e in es]}
            _write_journal(journal, state)
        except PermissionError as ex:
            abort_before_commit()
            raise SafetyError(f"cannot write {getattr(ex, 'filename', '') or 'the destination'}: permission denied; "
                              "nothing was written") from ex
        except BaseException:
            abort_before_commit()
            raise

        # -- commit: from here on, any failure is undone
        done = []
        try:
            for i, e in enumerate(es):
                if cancel():
                    raise Cancelled("cancelled")
                progress(i, total, f"writing {os.path.basename(e['dest'])}")
                if e["existed"] and file_sha(e["dest"]) != e["old_sha"]:
                    raise SafetyError(f"{e['dest']} changed while the conversion ran")
                _place(e["tmp"], e["dest"], e["existed"])
                done.append(e)
                state["entries"][i]["committed"] = True
                _write_journal(journal, state)
            for e in es:
                if file_sha(e["dest"]) != e["new_sha"]:
                    raise SafetyError(f"{e['dest']} did not read back as written")
        except BaseException as ex:
            # a move can complete just before a failure is raised: judge every file by its content, not the list
            moved = [e for e in es if e in done or (not os.path.exists(e["tmp"]) and file_sha(e["dest"]) == e["new_sha"])]
            problems = _undo(es, moved)
            if problems:
                raise SafetyError("writing failed and could NOT be fully undone: " + "; ".join(problems) +
                                  f". The journal {journal} lists every file; your earlier files are in the "
                                  "backups named there") from ex
            os.unlink(journal)
            _rmdirs(created_dirs)
            if isinstance(ex, Cancelled):
                raise Cancelled("cancelled; every file was put back exactly as it was") from None
            if isinstance(ex, (KeyboardInterrupt, SystemExit)):
                raise
            raise SafetyError(f"writing failed ({ex}); every file was put back exactly as it was") from ex
        os.unlink(journal)
        progress(total, total, "done")
        return [{"path": e["dest"], "sha256": e["new_sha"], "backup": e.get("backup")} for e in es]


def _rmdirs(dirs):
    """Remove folders this program created, newest first, if they are empty."""
    for d in reversed(dirs or []):
        try:
            os.rmdir(d)
        except OSError:
            pass


def _undo(entries, done):
    """Undo committed moves (newest first) and remove staged files. Returns a list of problems (empty = clean)."""
    problems = []
    for e in reversed(done):
        problems += _undo_one(e)
    for e in entries:
        if e not in done and e.get("tmp") and os.path.exists(e["tmp"]):
            try:
                os.unlink(e["tmp"])
            except OSError as ex:
                problems.append(f"could not remove the temporary file {e['tmp']} ({ex})")
    if not problems:
        for e in entries:                       # every file is back as it was: its backup is a redundant copy
            b = e.get("backup")
            if b and os.path.exists(b) and file_sha(b) == e.get("old_sha") == file_sha(e["dest"]):
                os.unlink(b)
    return problems


def _undo_one(e):
    dest, cur = e["dest"], file_sha(e["dest"])
    if e["existed"]:
        if cur == e["old_sha"]:
            return []
        if cur != e["new_sha"]:
            return [f"{dest} was changed by another program; left as it is"]
        b = e.get("backup")
        if not b or file_sha(b) != e["old_sha"]:
            return [f"the backup of {dest} is missing or damaged"]
        fd, tmp = tempfile.mkstemp(prefix=".ffix-tmp-", dir=os.path.dirname(dest))
        os.close(fd)
        try:
            shutil.copyfile(b, tmp)
            if file_sha(tmp) != e["old_sha"]:
                return [f"could not copy the backup of {dest}"]
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return [] if file_sha(dest) == e["old_sha"] else [f"{dest} could not be restored"]
    if cur is None:
        return []
    if cur != e["new_sha"]:
        return [f"{dest} was changed by another program; left as it is"]
    os.unlink(dest)
    return []


def recover(journal):
    """Undo an interrupted Transaction from its journal. Returns {"restored": [...], "problems": [...]}.

    Each destination is judged by its SHA-256, not by the journal's flags (the process may have died between a move
    and the journal update): a file holding the new content is undone, one holding the old content is left alone."""
    with open(journal, encoding="utf-8") as f:
        state = json.load(f)
    if state.get("tool") != "ffix-convert" or "entries" not in state:
        raise SafetyError(f"{journal} is not a journal of this program")
    entries = state["entries"]
    done = [e for e in entries if file_sha(e["dest"]) == e.get("new_sha") and e.get("new_sha") != e.get("old_sha")]
    problems = _undo(entries, done)
    if not problems:
        os.unlink(journal)
        _rmdirs(state.get("dirs_created"))
    return {"restored": [e["dest"] for e in done], "problems": problems}
