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
    "cancelled",
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

    def failed(self, *, cancelled=False):
        self.finished("cancelled" if cancelled else "failed")

    def finished(self, phase="complete"):
        if phase not in {"complete", "failed", "cancelled"}:
            raise ValueError("CALCULATION_PROGRESS_TERMINAL_INVALID")
        value = self.snapshot()
        if value is None:
            return
        now = datetime.now(UTC)
        value.update(phase=phase, updated_at=now.isoformat(),
                     elapsed_seconds=round((now-datetime.fromisoformat(
                         value["started_at"],
                     )).total_seconds(), 1),
                     operation_elapsed_seconds=round((now-datetime.fromisoformat(
                         value["operation_started_at"],
                     )).total_seconds(), 1))
        value.pop("recent_events", None)
        self.record(value)
        logger.info("calculation batch terminal name={} phase={} batch={}/{} rows={}/{}",
                    value["name"], phase, value["batch_index"], value["batch_count"],
                    value["completed_rows"], value["total_rows"])


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
        from app.services.execution_diagnostics import PHASES as DIAGNOSTIC_PHASES
        from app.services.execution_diagnostics import record_duration

        # These are phase intervals, not SQL-only timings. In particular the
        # existing lookup_candidate interval contains the combined A/B query.
        if ((self.kind != "read" or self.name == "factors.input_frame")
                and self.phase in DIAGNOSTIC_PHASES
                and hasattr(self, "diagnostic_phase_started")):
            record_duration(self.name, self.phase, now-self.diagnostic_phase_started)
        self.diagnostic_phase_started = now
        if (phase not in {"complete", "batch_complete", "failed", "cancelled"}
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
        if phase in {"complete", "failed", "cancelled"} and not getattr(
                self, "policy_recorded", False):
            from app.services.calculation_policy import active_policy

            policy = active_policy.get()
            if policy is not None:
                policy.observe_stage(self.name, self.kind, now-self.started, phase != "complete")
            self.policy_recorded = True
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
