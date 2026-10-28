"""Per-root execution switches/source and bounded, parameter-free cost evidence."""

import hashlib
import json
import re
import shutil
import subprocess
from contextvars import ContextVar
from copy import deepcopy
from enum import StrEnum
from time import monotonic

from sqlalchemy import event

from app.core.config import ROOT_DIR, get_settings

FLAGS = (
    "factor_input_reuse_enabled",
    "raw_preflight_batch_enabled",
    "factor_cpu_optimization_enabled",
)
active_policy = ContextVar("calculation_execution_policy", default=None)
worker_source = ContextVar("calculation_worker_source", default=None)


class PolicyChangeReason(StrEnum):
    BUSINESS_SOURCE_CHANGED = "BUSINESS_SOURCE_CHANGED"
    OPTIMIZATION_FLAGS_CHANGED = "OPTIMIZATION_FLAGS_CHANGED"
    JOB_FROZEN_IDENTITY_MISMATCH = "JOB_FROZEN_IDENTITY_MISMATCH"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class PolicyChanged(ValueError):
    """Keep the public code stable; diagnostics contain only hashes/enums."""

    def __init__(self, reason, frozen=None, observed=None):
        super().__init__("CALCULATION_POLICY_CHANGED")
        self.reason = PolicyChangeReason(reason).value
        self.diagnostics = dict(
            policy_change_reason=self.reason,
            frozen_source=source_audit(frozen),
            observed_source=source_audit(observed),
        )

    @property
    def display_message(self):
        return f"CALCULATION_POLICY_CHANGED [reason={self.reason}]"


def source_audit(source):
    source = source if isinstance(source, dict) else {}
    digest, commit = source.get("source_sha256"), source.get("commit_sha")
    return dict(
        source_sha256=digest if isinstance(digest, str) and
            re.fullmatch(r"[0-9a-f]{64}", digest) else None,
        commit_sha=commit if isinstance(commit, str) and
            re.fullmatch(r"[0-9a-f]{40}", commit) else None,
        worktree=source.get("worktree") if source.get("worktree") in
            ("CLEAN", "DIRTY", "UNAVAILABLE") else "UNAVAILABLE",
    )


def calculation_source_identity(source):
    if (not isinstance(source, dict)
            or not set(source) <= {"source_sha256", "commit_sha", "worktree"}
            or not isinstance(source.get("source_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", source["source_sha256"]) is None
            or (source.get("commit_sha") is not None and (
                not isinstance(source["commit_sha"], str)
                or re.fullmatch(r"[0-9a-f]{40}", source["commit_sha"]) is None))
            or ("worktree" in source and source["worktree"] not in
                ("CLEAN", "DIRTY", "UNAVAILABLE"))):
        raise ValueError("CALCULATION_SOURCE_UNAVAILABLE")
    return source["source_sha256"]


def _source(source=None):
    try:
        result = runtime_source() if source is None else deepcopy(source)
        calculation_source_identity(result)
        return result
    except (OSError, ValueError):
        raise PolicyChanged("SOURCE_UNAVAILABLE") from None


def runtime_source():
    files = {}
    for directory, suffixes in (("backend", {".py"}), ("config", {".yaml"})):
        if (ROOT_DIR / directory).is_symlink():
            raise ValueError("CALCULATION_SOURCE_UNTRUSTED")
        if not (ROOT_DIR / directory).is_dir():
            raise ValueError("CALCULATION_SOURCE_UNAVAILABLE")
        before = len(files)
        for path in sorted((ROOT_DIR / directory).rglob("*")):
            if path.is_symlink():
                raise ValueError("CALCULATION_SOURCE_UNTRUSTED")
            if path.is_file() and path.suffix in suffixes:
                files[path.relative_to(ROOT_DIR).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        if len(files) == before:
            raise ValueError("CALCULATION_SOURCE_UNAVAILABLE")
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
        observed = _source(source)
        source = observed
        resident = worker_source.get()
        if (resident is not None
                and calculation_source_identity(observed) !=
                calculation_source_identity(_source(resident))):
            # A resident Worker cannot relabel already imported Python modules
            # with a later on-disk release while accepting the next Job.
            raise PolicyChanged("BUSINESS_SOURCE_CHANGED", resident, observed)
        if resident is not None:
            source = deepcopy(resident)
        flags = flag_values(settings)
        if parent is not None:
            parent.guard(settings)
            if calculation_source_identity(parent.source) != calculation_source_identity(observed):
                raise PolicyChanged("JOB_FROZEN_IDENTITY_MISMATCH", parent.source, observed)
            source = deepcopy(parent.source)
        record = dict(
            schema_version="biz-perf-01.execution.v1",
            job_id=str(job.id),
            root_job_id=parent.record["root_job_id"] if parent else str(job.id),
            flags=flags,
            source=source,
            commit_status="LOCAL_HEAD_WITH_ACTUAL_SOURCE_DIGEST"
                if source.get("commit_sha") else "UNAVAILABLE",
            request=request_range(job.job_metadata, getattr(job, "target_trade_date", None)),
        )
        old = (job.job_metadata or {}).get("calculation_execution")
        if "calculation_execution" in (job.job_metadata or {}):
            try:
                valid = (isinstance(old, dict)
                    and all(old.get(k) == record[k] for k in (
                        "schema_version", "job_id", "root_job_id", "flags", "request"))
                    and isinstance(old.get("flags"), dict)
                    and all(type(v) is bool for v in old["flags"].values())
                    and calculation_source_identity(old.get("source")) ==
                        calculation_source_identity(observed))
            except ValueError:
                valid = False
            if not valid:
                raise PolicyChanged("JOB_FROZEN_IDENTITY_MISMATCH",
                                    old.get("source") if isinstance(old, dict) else None, observed)
            # A revalidation is not permission to rewrite the original evidence.
            record, source = deepcopy(old), deepcopy(old["source"])
        self = cls()
        self._record, self.source, self.closed = record, source, False
        self.failure = None
        self.source_diagnostics = dict(
            worker_source=source_audit(resident), observed_source=source_audit(observed),
            git_metadata_changed=source_audit(source) != source_audit(observed),
        )
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
        if self.failure is not None:
            raise self.failure
        try:
            flags = flag_values(settings or get_settings())
        except ValueError:
            self._reject("OPTIMIZATION_FLAGS_CHANGED", self.source)
        if flags != self._record["flags"]:
            self._reject("OPTIMIZATION_FLAGS_CHANGED", self.source)

    def _reject(self, reason, observed):
        error = PolicyChanged(reason, self.source, observed)
        if self.failure is None:
            self.failure = error
        raise error

    def verify_source(self):
        self.guard()
        try:
            observed = _source()
        except PolicyChanged:
            self._reject("SOURCE_UNAVAILABLE", None)
        if calculation_source_identity(observed) != calculation_source_identity(self.source):
            self._reject("BUSINESS_SOURCE_CHANGED", observed)
        self.source_diagnostics.update(
            observed_source=source_audit(observed),
            git_metadata_changed=source_audit(self.source) != source_audit(observed),
        )

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
            source_diagnostics=deepcopy(self.source_diagnostics),
            **({"policy_change": deepcopy(self.failure.diagnostics)} if self.failure else {}),
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
