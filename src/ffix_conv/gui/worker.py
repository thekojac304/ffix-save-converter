"""Background execution for the window.

Every service call runs on ONE worker thread (a QThreadPool limited to one thread): the window stays responsive,
calls never run at the same time, and a second conversion cannot start while one runs. Results, failures and
progress come back as Qt signals, delivered on the GUI thread. Each job gets its own cancel token; the service checks
it between saves and the transaction undoes anything already moved if it is set while writing.
"""
import threading
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class JobSignals(QObject):
    progress = Signal(int, int, str)     # done, total, what
    done = Signal(object)
    failed = Signal(object, str)         # exception, formatted traceback (for the log only)


class Job(QRunnable):
    def __init__(self, fn, skippable=False):
        super().__init__()
        self.fn, self.skippable = fn, skippable
        self.signals = JobSignals()
        self.cancel = threading.Event()
        self.setAutoDelete(True)

    def run(self):
        if self.skippable and self.cancel.is_set():
            self.signals.failed.emit(_Skipped(), "")
            return
        try:
            res = self.fn(self.signals.progress.emit, self.cancel.is_set)
        except Exception as e:       # every failure is reported to the window; nothing escapes the thread
            self.signals.failed.emit(e, traceback.format_exc())
            return
        self.signals.done.emit(res)


class _Skipped(Exception):
    """A job cancelled before it started (superseded by newer choices)."""


class Engine(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._live = set()

    def submit(self, fn, on_done=None, on_failed=None, on_progress=None, skippable=False):
        """fn(progress, cancel) runs on the worker thread. Returns the Job (job.cancel.set() to cancel it).
        A skippable job cancelled before it starts is not run at all (a superseded check); any other job is run
        and sees the cancel itself (a conversion then writes nothing)."""
        job = Job(fn, skippable)
        sig = job.signals
        self._live.add(sig)                       # keep the signal object alive until delivery
        if on_progress:
            sig.progress.connect(on_progress)
        if on_done:
            sig.done.connect(on_done)
        if on_failed:
            sig.failed.connect(on_failed)
        sig.done.connect(lambda *_: self._live.discard(sig))
        sig.failed.connect(lambda *_: self._live.discard(sig))
        self.pool.start(job)
        return job

    def busy(self):
        return self.pool.activeThreadCount() > 0 or bool(self._live)

    def wait(self, ms=-1):
        return self.pool.waitForDone(ms)


def skipped(e):
    return isinstance(e, _Skipped)
