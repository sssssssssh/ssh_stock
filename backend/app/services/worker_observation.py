"""Bounded diagnostic facts, never an executor-death or recovery authority."""

import hashlib
import threading
from copy import deepcopy
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

from sqlalchemy import or_, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

ROLES = {"main": "m", "heartbeat": "h", "diagnostic": "d"}
HEARTBEAT_PHASES = {"session_acquire", "heartbeat", "connection_acquire",
                    "transaction_setup", "lease_update", "lease_commit",
                    "progress_update", "progress_commit", "COMPLETE", "NOT_ATTEMPTED"}


def fingerprint(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]


class SessionRegistry:
    def __init__(self, execution):
        self.execution = execution
        self._lock = threading.Lock()
        self._roles = {}

    def record(self, role, fact):
        with self._lock:
            previous = self._roles.get(role)
            self._roles[role] = {"first": previous["first"] if previous else fact,
                                 "latest": fact}

    def snapshot(self):
        with self._lock:
            return dict(schema="worker.sessions.v1", root_job_id=str(self.execution.job_id),
                        execution_fingerprint=fingerprint(self.execution.token),
                        owner_fingerprint=fingerprint(self.execution.worker_id),
                        roles=deepcopy(self._roles), process_exit_proven=False,
                        status="SERVER_OBSERVED_NOT_EXIT_PROOF" if self._roles
                        else "NOT_REGISTERED")


def bind_session(db, registry, role):
    if role not in ROLES:
        raise ValueError("SESSION_ROLE_INVALID")
    db.info["worker_observation"] = (registry, role)


def observe_session(session, connection):
    registration = session.info.get("worker_observation")
    if registration is None or connection.dialect.name != "postgresql":
        return
    registry, role = registration
    execution = registry.execution
    name = f"space2/{ROLES[role]}/{UUID(str(execution.job_id)).hex}/{fingerprint(execution.token)}"
    if role in {"heartbeat", "diagnostic"}:
        connection.execute(text("SELECT set_config('statement_timeout','3s',true), "
                                "set_config('lock_timeout','1s',true)"))
    # SET LOCAL is cleared by commit/rollback, including pool reuse. The result
    # combines server-returned name and real PID/start/database/instance facts.
    fact = connection.execute(text("""SELECT
        set_config('application_name', :name, true) AS application_name,
        pid, backend_start, datid AS database_oid,
        pg_postmaster_start_time() AS postmaster_start,
        clock_timestamp() AS observed_at
        FROM pg_stat_activity WHERE pid=pg_backend_pid()"""), {"name": name}).mappings().one()
    registry.record(role, {k: v.isoformat() if isinstance(v, datetime) else v
                           for k, v in fact.items()})


class HeartbeatHealth:
    def __init__(self):
        self.failures = 0
        self.started = monotonic()
        self.last_confirmed = None
        self.last_confirmed_clock = self.started
        self.phase = "NOT_ATTEMPTED"
        self.sqlstate = None
        self.failed = False
        self.observed_at = None

    def observe(self, metrics, error=None, *, phase="session_acquire"):
        self.observed_at = datetime.now(UTC).isoformat(timespec="microseconds")
        if (any(x["phase"] == "lease_update" and x.get("rowcount") == 1 for x in metrics)
                and any(x["phase"] == "lease_commit" and x["outcome"] == "OK" for x in metrics)):
            self.last_confirmed = max(self.last_confirmed or "", self.observed_at)
            self.last_confirmed_clock = monotonic()
        self.failed = error is not None
        self.failures = self.failures+1 if self.failed else 0
        self.phase = getattr(error, "heartbeat_phase", phase) if error else "COMPLETE"
        if self.phase not in HEARTBEAT_PHASES:
            self.phase = "UNKNOWN_PHASE"
        code = getattr(getattr(error, "orig", None), "sqlstate", None)
        self.sqlstate = (code if isinstance(code, str) and len(code) == 5 and code.isalnum()
                         else None)

    def snapshot(self):
        return dict(schema="worker.heartbeat.v1",
                    observed_at=self.observed_at,
                    state="HEARTBEAT_DEGRADED" if self.failed else
                    "COMMUNICATION_CONFIRMED" if self.last_confirmed else "NOT_YET_CONFIRMED",
                    last_confirmed_at=self.last_confirmed, consecutive_failures=self.failures,
                    unconfirmed_seconds=max(0.0, monotonic()-self.last_confirmed_clock),
                    phase=self.phase, sqlstate=self.sqlstate, computation_success_proven=False)


def persist_observation(bind, registry, *, diagnostics=None, health=None):
    """One independent bounded CAS; never commit/rollback the computation Session.

    Failure (including lost COMMIT ACK) is not retried here. It does not release
    a Writer or turn unavailable observations into zero-valued success evidence.
    """
    from app.models.job import JobRun

    execution = registry.execution
    payload = {}
    if diagnostics is not None:
        payload["execution_diagnostics"] = diagnostics
    if health is not None:
        # Normalize ordering evidence; never derive a confirmed lease from this
        # timestamp. Legacy direct callers get a capture stamp, not lease proof.
        stamp = health.get("observed_at")
        if stamp is None:
            stamp = datetime.now(UTC).isoformat(timespec="microseconds")
        try:
            observed = datetime.fromisoformat(stamp)
            if observed.tzinfo is None:
                return "DIAGNOSTIC_PERSIST_UNCONFIRMED"
            stamp = observed.astimezone(UTC).isoformat(timespec="microseconds")
        except (TypeError, ValueError):
            return "DIAGNOSTIC_PERSIST_UNCONFIRMED"
        payload["heartbeat_health"] = {**health,
            "observed_at": stamp, "execution_fingerprint": fingerprint(execution.token)}
    outcome = diagnostics.get("outcome") if diagnostics is not None else None
    live = health is not None or outcome == "RUNNING_OBSERVATION"
    conditions = []
    if live or outcome == "UNCONFIRMED":
        conditions.extend((JobRun.status == "RUNNING",
            JobRun.job_metadata["execution_diagnostics"]["outcome"].as_string()
                .is_distinct_from("UNCONFIRMED")))
    elif outcome in {"SUCCESS", "PARTIAL", "FAILED", "CANCELLED"}:
        conditions.append(JobRun.status == outcome)
    if health is not None:
        prior = JobRun.job_metadata["heartbeat_health"]
        conditions.append(or_(
            prior["execution_fingerprint"].as_string().is_distinct_from(
                fingerprint(execution.token)),
            prior["observed_at"].as_string().is_(None),
            prior["observed_at"].as_string() < stamp))
    try:
        # A caller may itself be bound to a pinned Connection. Never join that
        # external transaction for telemetry or roll it back on observation failure.
        with Session(bind=bind.engine) as db:
            bind_session(db, registry, "diagnostic")
            db.execute(text("SELECT set_config('lock_timeout','1s',true), "
                            "set_config('statement_timeout','3s',true)"))
            payload["database_sessions"] = registry.snapshot()
            result = db.execute(update(JobRun).where(
                JobRun.id == execution.job_id, JobRun.worker_id == execution.worker_id,
                JobRun.execution_token == execution.token,
                JobRun.status.in_(("RUNNING", "SUCCESS", "PARTIAL", "FAILED", "CANCELLED")),
                *conditions,
            ).values(job_metadata=JobRun.job_metadata.op("||")(payload))
              .execution_options(synchronize_session=False))
            db.commit()
            return "PERSISTED" if result.rowcount == 1 else "CAS_NOT_APPLIED"
    except SQLAlchemyError:
        # No exception text, SQL, parameters, Raw or credentials.
        return "DIAGNOSTIC_PERSIST_UNCONFIRMED"


def heartbeat_health_payload(job, stale):
    """Read-only API projection. Even fresh communication is not computation proof."""
    value = dict(job.job_metadata or {}).get("heartbeat_health") or {}
    if not isinstance(value, dict) or value.get("execution_fingerprint") != fingerprint(
            getattr(job, "execution_token", None)):
        value = {}
    stamp = job.heartbeat_at
    if stamp is not None and stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    count = value.get("consecutive_failures")
    return dict(state="HEARTBEAT_DEGRADED" if job.status == "RUNNING" and (
        stale or value.get("state") == "HEARTBEAT_DEGRADED") else "NOT_CURRENTLY_RUNNING"
        if job.status != "RUNNING" else value.get("state")
        if value.get("state") in {"COMMUNICATION_CONFIRMED", "NOT_YET_CONFIRMED"}
        else "NOT_OBSERVED",
        last_confirmed_at=stamp.isoformat() if stamp else None,
        consecutive_failures=count if type(count) is int and 0 <= count <= 2**31-1 else None,
        phase=value.get("phase") if value.get("phase") in HEARTBEAT_PHASES else None,
        unconfirmed_seconds=max(0, (datetime.now(UTC)-stamp).total_seconds()) if stamp else None,
        computation_success_proven=False)


def finish_worker_observation(registry, recorder):
    execution = registry.execution
    try:
        snapshot = None
        if recorder is not None:
            snapshot = recorder.snapshot()
            snapshot.update(root_job_id=str(execution.job_id),
                            execution_fingerprint=fingerprint(execution.token),
                            outcome="UNCONFIRMED")
            with Session(bind=execution.bind.engine) as reader:
                reader.execute(text("SET TRANSACTION READ ONLY"))
                reader.execute(text("SET LOCAL statement_timeout='3s'"))
                reader.execute(text("SET LOCAL lock_timeout='1s'"))
                observed = reader.execute(text("SELECT status FROM job_run WHERE id=:id "
                    "AND worker_id=:owner AND execution_token=:token"),
                    {"id": execution.job_id, "owner": execution.worker_id,
                     "token": execution.token}).scalar_one_or_none()
            snapshot["outcome"] = observed if observed in {
                "SUCCESS", "PARTIAL", "FAILED", "CANCELLED"} else "UNCONFIRMED"
        return persist_observation(execution.bind, registry, diagnostics=snapshot)
    except Exception:
        return "DIAGNOSTIC_PERSIST_UNCONFIRMED"
