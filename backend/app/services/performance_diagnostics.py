"""Opt-in local evidence. Never an execution, publication or recovery authority."""

import hashlib
import json
import math
import os
import platform
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from time import monotonic, process_time

from loguru import logger

active_trace = ContextVar("performance_trace", default=None)
active_span = ContextVar("performance_span", default=None)
STAGES = frozenset({
    "task.queue_wait", "worker.claim", "raw.read", "data.transform", "factor.compute",
    "candidate.query", "candidate.filter", "quality.check", "candidate.write",
    "publish.prepare", "publish.commit", "task.finalize",
})


def stamp():
    return datetime.now(UTC).isoformat()


def resource_sample():
    from app.services.calculation_memory import process_memory_bytes

    try:
        rss, peak = process_memory_bytes()
    except Exception:
        rss = peak = None
    return dict(cpu_time_ms=process_time() * 1000, rss_bytes=rss,
                process_lifetime_peak_rss_bytes=peak, threads=None,
                network_sent_bytes=None, network_received_bytes=None,
                source="process_time/process_memory_bytes", scope="process")


class Trace:
    def __init__(self, task_id, *, root_id=None, source=None, configuration=None):
        self.trace_id = uuid.uuid4().hex
        self.task_id = str(task_id)
        self.root_id = str(root_id or task_id)
        self.source = source or {}
        self.started_at, self.started = stamp(), monotonic()
        self.initial = resource_sample()
        self.spans, self.warnings = [], set()
        self.status = "incomplete"
        self.context = dict(data_range=None, stock_count=None, raw_rows=None, cache_used=None)
        self.sql = {}
        self.execute_calls = 0
        self.fetch_calls = 0
        self.fetch_rows = 0
        self.fetch_ms = 0.0
        self.overhead_ms = 0.0
        self.config_fingerprint = hashlib.sha256(json.dumps(
            configuration or {}, sort_keys=True).encode()).hexdigest()

    def interval(self, stage, started_at, elapsed, *, rows=None, batches=None,
                 error=None, metrics=None, parent=None):
        if stage not in STAGES or not math.isfinite(elapsed) or elapsed < 0:
            self.warnings.add("INVALID_METRIC")
            return
        if len(self.spans) >= 4096:
            self.warnings.add("SPAN_LIMIT_REACHED")
            return
        self.spans.append(dict(stage=stage, span_id=uuid.uuid4().hex,
            parent_span_id=parent, started_at=started_at, ended_at=stamp(),
            duration_ms=elapsed * 1000, status=("cancelled" if error is not None
                and type(error).__name__ == "JobCancelled" else "error" if error else "success"),
            input_rows=None, output_rows=rows, calls=None, batches=batches,
            metrics=metrics or {}))

    def report(self):
        final = resource_sample()
        wall = max(0, monotonic() - self.started) * 1000
        cpu = max(0, final["cpu_time_ms"] - self.initial["cpu_time_ms"])
        recorded = {s["stage"] for s in self.spans}
        warnings = self.warnings | {
            "NETWORK_BYTES_AND_NATIVE_THREADS_UNAVAILABLE",
            "EXECUTE_INCLUDES_DRIVER_BUFFERING_NOT_SERVER_EXECUTION_ONLY",
            "FETCH_INCLUDES_TRANSPORT_AND_MATERIALIZATION_NOT_NETWORK_ONLY",
            "RESULT_BYTES_UNAVAILABLE", "QUEUE_WAIT_NOT_MEASURED_BY_MONOTONIC",
        }
        if not self.source.get("commit_sha"):
            warnings.add("EXACT_GIT_SHA_UNAVAILABLE")
        return dict(schema_version="biz-perf-03-a.v1", trace_id=self.trace_id,
            task_id=self.task_id, root_id=self.root_id,
            git_sha=self.source.get("commit_sha"), source=self.source,
            config_fingerprint=self.config_fingerprint,
            started_at=self.started_at, ended_at=stamp(), total_wall_ms=wall,
            status=self.status, environment=dict(python=platform.python_version(),
                os=platform.system(), logical_cpu_count=os.cpu_count(),
                database_version=None, database_location="REDACTED"),
            context=dict(self.context),
            stages=list(self.spans), coverage={stage: "RECORDED" if stage in recorded
                else "NOT_INSTRUMENTED" for stage in sorted(STAGES)},
            coverage_reasons={stage: "No safely separated observation on this execution path"
                for stage in sorted(STAGES - recorded)},
            database_summary=dict(execute_calls=self.execute_calls,
                execute_total_ms=sum(x["total_ms"] for x in self.sql.values()),
                fetch_calls=self.fetch_calls, fetch_total_ms=self.fetch_ms
                    if self.fetch_calls else None,
                fetched_rows=self.fetch_rows if self.fetch_calls else None,
                result_bytes=None, sql_fingerprints=list(self.sql.values()),
                statistics_extension="unavailable_not_probed"),
            worker_resources=dict(initial=self.initial, final=final,
                cpu_interval_ms=cpu, cpu_percent_single_core=cpu / wall * 100 if wall else None,
                cpu_interval_wall_ms=wall, sampling="root_boundaries_no_polling"),
            diagnostic_overhead=dict(instrumentation_ms=None,
                flush_ms=None, note="partial self-time; OFF/ON whole-run comparison required"),
            warnings=sorted(warnings))

    def flush(self, directory):
        # Exclusive creation: one report per attempt, no overwrite or business DB writes.
        target = Path(directory) / self.started_at[:10] / (self.trace_id + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.report(), allow_nan=False, indent=2)
        pending = target.with_suffix(".pending-" + uuid.uuid4().hex)
        try:
            with pending.open("x", encoding="utf-8") as handle:
                handle.write(payload)
            os.link(pending, target)  # Atomic, refuses replacing an existing report.
        finally:
            pending.unlink(missing_ok=True)
        return target


@contextmanager
def span(stage):
    trace = active_trace.get()
    if trace is None:
        yield
        return
    before, began, error = stamp(), monotonic(), None
    identity, parent = uuid.uuid4().hex, active_span.get()
    token = active_span.set(identity)
    try:
        yield
    except BaseException as exc:
        error = exc
        raise
    finally:
        try:
            size = len(trace.spans)
            trace.interval(stage, before, monotonic() - began, error=error, parent=parent)
            if len(trace.spans) > size:
                trace.spans[-1]["span_id"] = identity
        except Exception:
            trace.warnings.add("SPAN_RECORD_FAILED")
        finally:
            active_span.reset(token)


def terminal(status, job_id=None):
    trace = active_trace.get()
    if trace is not None and (job_id is None or str(job_id) == trace.root_id):
        trace.status = {"SUCCESS": "success", "FAILED": "error",
                        "CANCELLED": "cancelled"}.get(status, "incomplete")


def observed(stage):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with span(stage):
                return function(*args, **kwargs)
        return wrapped
    return decorate


def observe_worker(function):
    @wraps(function)
    def wrapped(db, job_id, *args, **kwargs):
        from app.core.config import get_settings

        settings = get_settings()
        if not settings.perf_diagnostics_enabled or active_trace.get() is not None:
            return function(db, job_id, *args, **kwargs)
        trace = observer = token = None
        try:
            from app.services.calculation_policy import worker_source
            from app.services.performance_sql_diagnostics import SQLObserver

            trace = Trace(job_id, source=worker_source.get(), configuration={
                "ab_merge_read": settings.ab_merge_read_enabled,
                "factor_input_reuse": settings.factor_input_reuse_enabled,
            })
            token = active_trace.set(trace)
            observer = SQLObserver(db.get_bind().engine, trace)
            observer.install()
        except Exception:
            logger.warning("PERFORMANCE_DIAGNOSTICS_SETUP_UNAVAILABLE")
        try:
            return function(db, job_id, *args, **kwargs)
        except BaseException as exc:
            if trace is not None:
                trace.status = "cancelled" if type(exc).__name__ == "JobCancelled" else "error"
            raise
        finally:
            try:
                if observer is not None:
                    observer.close()
                if trace is not None:
                    with span("task.finalize"):
                        pass
                    trace.flush(settings.perf_diagnostics_directory)
            except Exception:
                logger.warning("PERFORMANCE_DIAGNOSTICS_FLUSH_UNAVAILABLE")
            finally:
                if token is not None:
                    active_trace.reset(token)
    return wrapped


def measured_interval(stage, seconds, *, rows=None, batches=None):
    trace = active_trace.get()
    if trace is not None:
        try:
            from datetime import timedelta

            began = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()
            trace.interval(stage, began, seconds, rows=rows, batches=batches,
                           parent=active_span.get())
        except Exception:
            trace.warnings.add("INTERVAL_RECORD_FAILED")


def driver_fetch(seconds, rows):
    trace = active_trace.get()
    if trace is not None:
        try:
            trace.fetch_calls += 1
            trace.fetch_ms += seconds * 1000
            if rows is not None:
                trace.fetch_rows += rows
            else:
                trace.warnings.add("FETCH_FAILED_PARTIAL_ROWS_UNKNOWN")
        except Exception:
            trace.warnings.add("FETCH_OBSERVATION_UNAVAILABLE")


def bind_task(job, metadata, settings):
    trace = active_trace.get()
    if trace is None:
        return
    try:
        from datetime import date

        # Whitelist dates, never serialize arbitrary job_metadata/configuration.
        dates = {}
        for key in ("start", "end"):
            raw = metadata.get(key)
            dates[key] = date.fromisoformat(raw).isoformat() if isinstance(raw, str) else None
        trace.context["data_range"] = dates
        trace.context["cache_used"] = settings.factor_input_reuse_enabled
    except Exception:
        trace.warnings.add("TASK_CONTEXT_UNAVAILABLE")
