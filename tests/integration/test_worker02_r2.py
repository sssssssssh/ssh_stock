"""R2 real marked PG17 regressions, never incident or cloud data."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.repositories.job_run import touch_job_heartbeat
from app.services.job_execution import Execution
from app.services.worker_observation import SessionRegistry, persist_observation
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from scripts.v14_test_database import isolated_v14_database


@pytest.fixture
def observation(monkeypatch):
    with isolated_v14_database(monkeypatch) as (factory, engine):
        with factory() as db:
            job = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic-r2",
                         execution_token=uuid4(), job_metadata={"first_error": "preserved"})
            db.add(job)
            db.commit()
            registry = SessionRegistry(Execution(job.id, job.worker_id, job.execution_token, engine))
        yield factory, engine, registry


def test_delayed_heartbeat_does_not_regress_lease_or_progress(observation):
    factory, _, registry = observation
    key, owner, token = (registry.execution.job_id, registry.execution.worker_id,
                         registry.execution.token)
    now = datetime.now(UTC)
    newer = dict(updated_at=now.isoformat(), advanced_at=now.isoformat(), completed_rows=20)
    older = dict(updated_at=(now-timedelta(seconds=2)).isoformat(),
                 advanced_at=(now-timedelta(seconds=2)).isoformat(), completed_rows=10)
    with factory() as db:
        assert touch_job_heartbeat(db, key, owner, execution_token=token, now=now,
                                   calculation_progress=newer)
        db.rollback()
        assert touch_job_heartbeat(db, key, owner, execution_token=token,
                                   now=now-timedelta(seconds=2), calculation_progress=older)
        db.rollback()
        job = db.get(JobRun, key)
        assert job.heartbeat_at == now
        assert job.last_progress_at == now
        assert job.job_metadata["calculation_progress"] == newer


@pytest.mark.parametrize("terminal", ["SUCCESS", "FAILED", "CANCELLED", "PARTIAL"])
def test_late_health_only_observation_cannot_rewrite_terminal_metadata(observation, terminal):
    factory, engine, registry = observation
    with factory() as db:
        db.execute(update(JobRun).where(JobRun.id == registry.execution.job_id).values(
            status=terminal, job_metadata={"execution_diagnostics": {"outcome": terminal}}))
        db.commit()
    assert persist_observation(engine, registry, health={"state": "HEARTBEAT_DEGRADED"}) == \
        "CAS_NOT_APPLIED"
    with factory() as db:
        assert db.get(JobRun, registry.execution.job_id).job_metadata == {
            "execution_diagnostics": {"outcome": terminal}}


def test_delayed_health_cannot_overwrite_a_newer_observation(observation):
    factory, engine, registry = observation
    now = datetime.now(UTC)
    newer = dict(state="COMMUNICATION_CONFIRMED", observed_at=now.isoformat())
    older = dict(state="HEARTBEAT_DEGRADED",
                 observed_at=(now-timedelta(seconds=1)).isoformat())
    assert persist_observation(engine, registry, health=newer) == "PERSISTED"
    assert persist_observation(engine, registry, health=older) == "CAS_NOT_APPLIED"
    with factory() as db:
        assert db.get(JobRun, registry.execution.job_id).job_metadata["heartbeat_health"][
            "state"] == "COMMUNICATION_CONFIRMED"


def test_stale_terminal_snapshot_cannot_contradict_actual_terminal(observation):
    factory, engine, registry = observation
    with factory() as db:
        db.execute(update(JobRun).where(JobRun.id == registry.execution.job_id).values(
            status="FAILED"))
        db.commit()
    assert persist_observation(engine, registry, diagnostics={"outcome": "SUCCESS"}) == \
        "CAS_NOT_APPLIED"


def recovery_case(factory, registry):
    from app.services.data_job_reconcile import RecoveryApproval

    e = registry.execution
    with factory() as db:
        db.add(DataPublication(job_id=e.job_id, execution_token=e.token, state="PREPARING",
                               identity={}, row_counts={}))
        db.commit()
    now = datetime.now(UTC)
    return RecoveryApproval(e.job_id, e.worker_id, e.token, "r2-review", "r2-operator", "a"*64,
                            valid_from=now-timedelta(seconds=1),
                            valid_until=now+timedelta(minutes=2))


def test_recovery_rechecks_dynamic_authority_before_commit(observation):
    from app.services.data_job_reconcile import abort_confirmed_writer

    factory, _, registry = observation
    approval = recovery_case(factory, registry)
    calls = []

    def verify(_):
        calls.append(True)
        return len(calls) == 1  # Independent authority revoked after the initial proof.

    with factory() as db, pytest.raises(ValueError, match="EXECUTION_UNCONFIRMED"):
        abort_confirmed_writer(db, approval,
                               authority=SimpleNamespace(verify_exit_and_commits=verify))
    assert len(calls) == 2
    with factory() as db:
        assert db.get(JobRun, approval.job_id).status == "RUNNING"
        assert db.get(DataPublication, approval.job_id).state == "PREPARING"
        assert db.get(JobRun, approval.job_id).job_metadata == {"first_error": "preserved"}


def test_recovery_locks_parent_against_late_child_fk_insert(observation):
    from app.services.data_job_reconcile import abort_confirmed_writer

    factory, _, registry = observation
    approval = recovery_case(factory, registry)
    sqlstates = []

    def verify(_):
        with factory() as newcomer:
            newcomer.execute(text("SET LOCAL lock_timeout='100ms'"))
            newcomer.add(JobRun(job_type="recalculate", status="RUNNING", worker_id="other",
                execution_token=uuid4(), parent_job_id=approval.job_id, job_metadata={}))
            try:
                newcomer.commit()
            except DBAPIError as error:
                sqlstates.append(error.orig.sqlstate)
                newcomer.rollback()
                return False  # New claimant attempt invalidates the external freeze proof.
        return True

    with factory() as db, pytest.raises(ValueError, match="EXECUTION_UNCONFIRMED"):
        abort_confirmed_writer(db, approval,
                               authority=SimpleNamespace(verify_exit_and_commits=verify))
    assert sqlstates == ["55P03"]
    with factory() as db:
        assert db.get(JobRun, approval.job_id).status == "RUNNING"
        assert db.get(DataPublication, approval.job_id).state == "PREPARING"
