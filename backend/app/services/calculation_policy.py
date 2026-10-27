"""Per-root execution switches/source and bounded, parameter-free cost evidence."""

import hashlib
import json
import re
import shutil
import subprocess
from contextvars import ContextVar
from copy import deepcopy
from time import monotonic

from sqlalchemy import event

from app.core.config import ROOT_DIR, get_settings

FLAGS = (
    "factor_input_reuse_enabled",
    "raw_preflight_batch_enabled",
    "factor_cpu_optimization_enabled",
)
active_policy = ContextVar("calculation_execution_policy", default=None)


def runtime_source():
    files = {}
    for directory, suffixes in (("backend", {".py"}), ("config", {".yaml"})):
        for path in sorted((ROOT_DIR / directory).rglob("*")):
            if path.is_file() and path.suffix in suffixes:
                if path.is_symlink():
                    raise ValueError("CALCULATION_SOURCE_UNTRUSTED")
                files[path.relative_to(ROOT_DIR).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    if not files:
        raise ValueError("CALCULATION_SOURCE_UNAVAILABLE")
    commit, worktree = None, "UNAVAILABLE"
    # Runtime images can omit Git. Never infer a commit from an environment value.
    if shutil.which("git") and (ROOT_DIR / ".git").exists():
        try:
            value = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            ).stdout.strip()
            if re.fullmatch("[0-9a-f]{40}", value):
                commit = value
                dirty = subprocess.run(
                    ["git", "status", "--porcelain", "--untracked-files=all"],
                    cwd=ROOT_DIR, capture_output=True, timeout=2, check=True,
                ).stdout
                worktree = "DIRTY" if dirty.strip() else "CLEAN"
        except (OSError, subprocess.SubprocessError):
            pass  # Explicit UNAVAILABLE commit; source bytes remain mandatory.
    return dict(
        source_sha256=hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        commit_sha=commit,
        worktree=worktree,
    )


def flag_values(settings):
    result = {name: getattr(settings, name) for name in FLAGS}
    if any(type(value) is not bool for value in result.values()):
        raise ValueError("CALCULATION_POLICY_INVALID")
    return result


def request_range(metadata, target=None):
    result = {k: str(metadata[k]) for k in ("start", "end", "mode") if k in (metadata or {})}
    if target is not None:
        result.setdefault("start", str(target))
        result.setdefault("end", str(target))
    return result


class ExecutionPolicy:
    @classmethod
    def freeze(cls, job, settings, *, source=None, parent=None):
        source = runtime_source() if source is None else deepcopy(source)
        flags = flag_values(settings)
        if parent is not None:
            parent.guard(settings)
            if parent.source != source:
                raise ValueError("CALCULATION_POLICY_CHANGED")
        record = dict(
            schema_version="biz-perf-01.execution.v1",
            job_id=str(job.id),
            root_job_id=parent.record["root_job_id"] if parent else str(job.id),
            flags=flags,
            source=source,
            commit_status="LOCAL_HEAD_WITH_ACTUAL_SOURCE_DIGEST"
                if source["commit_sha"] else "UNAVAILABLE",
            request=request_range(job.job_metadata, getattr(job, "target_trade_date", None)),
        )
        old = (job.job_metadata or {}).get("calculation_execution")
        if old is not None and any(
            old.get(k) != record[k]
            for k in ("schema_version", "job_id", "root_job_id", "flags", "source", "request")
        ):
            raise ValueError("CALCULATION_POLICY_CHANGED")
        self = cls()
        self._record, self.source, self.closed = record, source, False
        self.reads, self.driver_reads, self.sql, self.stages = {}, {}, {}, {}
        self.started = monotonic()
        job.job_metadata = {**dict(job.job_metadata or {}), "calculation_execution": self.record}
        return self

    @property
    def record(self):
        return deepcopy(self._record)

    def guard(self, settings=None):
        if self.closed:
            raise ValueError("CALCULATION_POLICY_CLOSED")
        if flag_values(settings or get_settings()) != self._record["flags"]:
            raise ValueError("CALCULATION_POLICY_CHANGED")

    def verify_source(self):
        self.guard()
        if runtime_source() != self.source:
            raise ValueError("CALCULATION_POLICY_CHANGED")

    def observe_fetch(self, name, rows, seconds):
        if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?", name):
            raise ValueError("CALCULATION_METRIC_LABEL_INVALID")
        value = self.reads.setdefault(name, dict(rows=0, fetches=0, seconds=0.0))
        value["rows"] += rows
        value["fetches"] += 1
        value["seconds"] += seconds

    def observe_stage(self, name, kind, seconds, failed):
        if name not in self.stages and len(self.stages) >= 64:
            raise ValueError("CALCULATION_METRIC_BUDGET_EXCEEDED")
        value = self.stages.setdefault(name, dict(kind=kind, calls=0, seconds=0.0, failures=0))
        value["calls"] += 1
        value["seconds"] += seconds
        value["failures"] += int(failed)

    def observe_driver_fetch(self, name, rows, seconds, failed=False):
        value = self.driver_reads.setdefault(name, dict(
            rows=0, calls=0, seconds=0.0, failures=0, incomplete_calls=0,
        ))
        value["calls"] += 1
        value["seconds"] += seconds
        value["failures"] += int(failed)
        value["incomplete_calls"] += int(rows is None)
        if rows is not None:
            value["rows"] += rows

    def snapshot(self, job_id=None, metadata=None, target=None):
        result = self.record
        if job_id is not None:
            result["job_id"] = str(job_id)
        if metadata is not None:
            result["request"] = request_range(metadata, target)
        result.update(
            reads=deepcopy(self.reads),
            driver_reads=deepcopy(self.driver_reads),
            sql=deepcopy(self.sql),
            stages=deepcopy(self.stages),
            elapsed_seconds=monotonic() - self.started,
            fetch_scope="DELIVERED_PARTITIONS_NOT_WIRE_FETCH",
            driver_fetch_scope="SERVER_CURSOR_FETCHMANY_INCLUDING_PRIMING_AND_EOF",
            timings_nested=True,
            counter_scope="ROOT_CUMULATIVE_INCLUDING_CHILDREN",
        )
        return result

    def close(self):
        self.closed = True


class DriverFetchObserver:
    """Observe actual psycopg named FETCH calls without changing transport size.

    The factory is restored before the pinned connection can return to a pool.
    Retain counters only, never rows, SQL text, arguments or driver addresses.
    """

    def __init__(self, db, name, policy):
        self.driver = db.connection().connection.driver_connection
        self.previous = self.driver.server_cursor_factory
        base = getattr(self.previous, "_calculation_base_factory", self.previous)

        class TracedCursor(base):
            _calculation_base_factory = base

            def fetchmany(cursor, *args, **kwargs):
                began = monotonic()
                try:
                    rows = super().fetchmany(*args, **kwargs)
                except BaseException:
                    policy.observe_driver_fetch(name, None, monotonic()-began, failed=True)
                    raise
                policy.observe_driver_fetch(name, len(rows), monotonic()-began)
                return rows

        self.driver.server_cursor_factory = TracedCursor

    def close(self):
        self.driver.server_cursor_factory = self.previous


def effective_flag(settings, name):
    if name not in FLAGS:
        raise ValueError("CALCULATION_POLICY_INVALID")
    policy = active_policy.get()
    if policy is None:
        return getattr(settings, name)
    policy.guard(settings)
    return policy.record["flags"][name]


class QueryObserver:
    """Only operation counts/durations; no SQL, arguments, addresses or row contents."""

    def __init__(self, engine, policy):
        self.engine, self.policy = engine, policy
        self.registered = []

    def before(self, conn, cursor, statement, parameters, context, many):
        if active_policy.get() is self.policy:
            op = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "OTHER"
            op = (
                op
                if op
                in {
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "WITH",
                    "LOCK",
                    "SET",
                    "CREATE",
                    "DROP",
                    "SAVEPOINT",
                    "RELEASE",
                    "ROLLBACK",
                }
                else "OTHER"
            )
            context.calculation_policy_query = (op, monotonic())
            self.policy.sql.setdefault(op, dict(count=0, seconds=0.0, failures=0))["count"] += 1

    def after(self, conn, cursor, statement, parameters, context, many):
        value = getattr(context, "calculation_policy_query", None)
        if value is not None:
            self.policy.sql[value[0]]["seconds"] += monotonic() - value[1]
            context.calculation_policy_query = None

    def failed(self, error):
        context = error.execution_context
        value = getattr(context, "calculation_policy_query", None)
        if value is not None:
            self.policy.sql[value[0]]["failures"] += 1
            self.policy.sql[value[0]]["seconds"] += monotonic() - value[1]
            context.calculation_policy_query = None

    def install(self):
        for name, handler in (
            ("before_cursor_execute", self.before),
            ("after_cursor_execute", self.after),
            ("handle_error", self.failed),
        ):
            event.listen(self.engine, name, handler)
            self.registered.append((name, handler))

    def close(self):
        for name, handler in reversed(self.registered):
            event.remove(self.engine, name, handler)
        self.registered.clear()
