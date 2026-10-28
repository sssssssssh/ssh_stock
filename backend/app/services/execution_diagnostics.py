"""Opt-in bounded timing evidence; no SQL, rows, parameters or connection data."""

import re
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic

active_diagnostics = ContextVar("execution_diagnostics", default=None)
PHASES = frozenset(("query", "fetch", "frame", "compute", "prepare", "store", "commit",
                   "lookup_candidate", "lookup_published", "replace", "materialize"))


class ExecutionDiagnostics:
    def __init__(self):
        self.totals = {}
        self.recent = deque(maxlen=32)

    def record(self, name, phase, seconds, *, rows=0, error=None):
        if (not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?", name)
                or len(name) > 80 or phase not in PHASES):
            raise ValueError("DIAGNOSTIC_LABEL_INVALID")
        key = (name, phase)
        if key not in self.totals and len(self.totals) >= 128:
            raise ValueError("DIAGNOSTIC_CARDINALITY_EXCEEDED")
        code = getattr(getattr(error, "orig", None), "sqlstate", None)
        code = code if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{5}", code) else None
        metric = self.totals.setdefault(key, dict(calls=0, seconds=0.0, rows=0, failures=0))
        metric["calls"] += 1
        metric["seconds"] += seconds
        metric["rows"] += rows
        metric["failures"] += int(error is not None)
        self.recent.append(dict(name=name, phase=phase, seconds=seconds, rows=rows,
                                failed=error is not None, sqlstate=code))

    def snapshot(self):
        from app.services.calculation_memory import available_memory_bytes, process_memory_bytes

        rss, peak = process_memory_bytes()
        return dict(phases=[dict(name=name, phase=phase, **value)
                            for (name, phase), value in self.totals.items()],
                    recent=list(self.recent), rss_bytes=rss, peak_rss_bytes=peak,
                    available_memory_bytes=available_memory_bytes(),
                    memory_kind="POSIX_PEAK_IS_CONSERVATIVE_ON_MACOS")


def record_duration(name, phase, seconds, *, rows=0, error=None):
    observer = active_diagnostics.get()
    if observer is not None:
        observer.record(name, phase, seconds, rows=rows, error=error)


@contextmanager
def operation(name, phase):
    if active_diagnostics.get() is None:
        yield
        return
    started, error = monotonic(), None
    try:
        yield
    except BaseException as exc:
        error = exc
        raise
    finally:
        record_duration(name, phase, monotonic()-started, error=error)
