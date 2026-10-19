"""Bounded diagnostic snapshots, independent of business transaction commits."""

import re
import threading
from collections import deque
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, datetime
from time import monotonic

from loguru import logger

current_progress: ContextVar["CalculationProgress | None"] = ContextVar(
    "calculation_progress", default=None,
)
PHASES = {
    "started", "query", "fetch", "frame", "compute", "prepare",
    "lookup_candidate", "lookup_published", "store", "batch_complete", "complete", "failed",
}


class CalculationProgress:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest = None
        self._events = deque(maxlen=12)
        self._advanced_at = None

    def record(self, value, *, advanced=False):
        with self._lock:
            if advanced:
                self._advanced_at = value["updated_at"]
            self._latest = {**value, "advanced_at": self._advanced_at}
            self._events.append({key: value[key] for key in (
                "name", "kind", "phase", "batch_index", "batch_count", "completed_rows",
                "total_rows", "updated_at",
            )})

    def snapshot(self):
        with self._lock:
            if self._latest is None:
                return None
            return deepcopy({**self._latest, "recent_events": list(self._events)})

    def failed(self):
        value = self.snapshot()
        if value is None:
            return
        now = datetime.now(UTC)
        value.update(phase="failed", updated_at=now.isoformat(),
                     elapsed_seconds=round((now-datetime.fromisoformat(
                         value["started_at"],
                     )).total_seconds(), 1),
                     operation_elapsed_seconds=round((now-datetime.fromisoformat(
                         value["operation_started_at"],
                     )).total_seconds(), 1))
        value.pop("recent_events", None)
        self.record(value)


class ProgressStep:
    def __init__(self, name, kind, *, total_rows=None, batch_count=None):
        if (len(name) > 80 or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?", name)
                or kind not in {
                    "read", "compute", "reconcile", "candidate", "validate", "publish",
                }):
            raise ValueError("CALCULATION_PROGRESS_LABEL_INVALID")
        self.name, self.kind = name, kind
        self.total_rows, self.batch_count = total_rows, batch_count
        self.started = self.operation_started = monotonic()
        self.started_at = self.operation_started_at = datetime.now(UTC).isoformat()
        self.phase = None
        self.batch_index = 0
        self.last_log = self.started
        self.report("started", log=True)

    def report(self, phase, *, completed_rows=0, batch_index=0, advanced=False, log=False):
        if phase not in PHASES:
            raise ValueError("CALCULATION_PROGRESS_PHASE_INVALID")
        now, stamp = monotonic(), datetime.now(UTC).isoformat()
        if (phase not in {"complete", "batch_complete", "failed"}
                and (phase != self.phase or batch_index != self.batch_index)):
            self.phase, self.operation_started = phase, now
            self.operation_started_at = stamp
        self.phase, self.batch_index = phase, batch_index
        value = dict(
            name=self.name, kind=self.kind, phase=phase, batch_index=batch_index,
            batch_count=self.batch_count, completed_rows=completed_rows, total_rows=self.total_rows,
            started_at=self.started_at, operation_started_at=self.operation_started_at,
            updated_at=stamp, elapsed_seconds=round(now-self.started, 1),
            operation_elapsed_seconds=round(now-self.operation_started, 1),
        )
        recorder = current_progress.get()
        if recorder is not None:
            recorder.record(value, advanced=advanced)
        if log or now-self.last_log >= 30:
            logger.info(
                "calculation batch name={} kind={} phase={} batch={}/{} "
                "rows={}/{} elapsed_seconds={}",
                self.name, self.kind, phase, batch_index, self.batch_count,
                completed_rows, self.total_rows, value["elapsed_seconds"],
            )
            self.last_log = now


def run_calculation(name, calculate, *args, **kwargs):
    step = ProgressStep(name, "compute")
    step.report("compute", log=True)
    try:
        result = calculate(*args, **kwargs)
    except BaseException:
        step.report("failed", log=True)
        raise
    step.report("complete", completed_rows=len(result), advanced=True, log=True)
    return result
