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
            registry = SessionRegistry(Execution(
                job.id, job.worker_id, job.execution_token, engine))
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


@pytest.mark.parametrize("ack", ["committed", "not_committed"])
def test_unknown_recovery_ack_uses_fresh_readonly_receipt_without_reexecution(observation, ack):
    from dataclasses import replace

    from app.services.data_job_reconcile import abort_confirmed_writer, recovery_commit_status
    from sqlalchemy.exc import OperationalError

    factory, _, registry = observation
    approval = recovery_case(factory, registry)
    calls = []

    def verify(_):
        calls.append(True)
        return True  # Isolated authority contract, not production exit proof.

    with factory() as db:
        commit = db.commit

        def lose_ack():
            if ack == "committed":
                commit()
            raise OperationalError("synthetic", {}, RuntimeError("ISOLATED_ACK_UNKNOWN"),
                                   connection_invalidated=True)

        db.commit = lose_ack
        with pytest.raises(OperationalError):
            abort_confirmed_writer(db, approval,
                                   authority=SimpleNamespace(verify_exit_and_commits=verify))
    assert len(calls) == 2
    for _ in range(2):
        with factory() as reader:
            assert recovery_commit_status(reader, approval) == (
                "RECONCILED_ABORTED" if ack == "committed" else "RECOVERY_COMMIT_UNCONFIRMED")
            assert reader.scalar(text("SHOW transaction_read_only")) == "on"
            assert reader.scalar(text("SHOW transaction_isolation")) == "repeatable read"
    with factory() as reader:
        assert recovery_commit_status(reader, replace(approval, operator_id="another")) == \
            "RECOVERY_COMMIT_UNCONFIRMED"
    with factory() as db:
        job = db.get(JobRun, approval.job_id)
        assert job.job_metadata["first_error"] == "preserved"
        assert len(job.job_metadata.get("manual_reconciliations", [])) == (ack == "committed")
    assert len(calls) == 2  # Read-only reconciliation never calls/replays the authority.


@pytest.mark.parametrize("decision", ["approve", "revoke", "unknown_ack"])
def test_recovery_atomic_children_dirty_tombstones_and_public_A(observation, decision):
    from app.models.data_publication import DataPublicationRow, DataPublicationSource
    from app.models.market_data import DataDirtyRange
    from app.services.data_job_reconcile import abort_confirmed_writer, recovery_commit_status
    from sqlalchemy import select
    from sqlalchemy.exc import OperationalError

    from tests.integration.test_business_policy_worker_pg17 import published
    from tests.integration.test_data_publication import DAY, seed_published

    factory, _, registry = observation
    approval = recovery_case(factory, registry)
    seed_published(factory)
    before = published(factory)
    with factory() as db:
        root = db.get(JobRun, approval.job_id)
        root.error_message = "ORIGINAL_ROOT_FAILURE"
        child = JobRun(job_type="recalculate", status="RUNNING", worker_id=approval.worker_id,
            execution_token=approval.token, parent_job_id=root.id,
            error_message="ORIGINAL_CHILD_FAILURE", job_metadata={})
        dirty = DataDirtyRange(dataset="stock_daily", dirty_start_date=DAY, dirty_end_date=DAY,
            source_job_id=root.id, status="PROCESSING", retry_count=2,
            processing_started_at=datetime.now(UTC))
        db.add_all([child, dirty])
        db.flush()
        child_id, dirty_id = child.id, dirty.id
        db.add(DataPublicationSource(publication_id=root.id, source_job_id=child.id,
            role="CANDIDATE", validation={"pending_dirty_ids": [dirty.id]}))
        db.add(DataPublicationRow(publication_id=root.id, table_name="stock_factor_daily",
            row_key=(DAY.isoformat(), "TEST.SZ"), row_data=None, base_row={"close": 10},
            source_id=child.id, is_deleted=True))
        db.commit()
    calls = []

    def verify(_):
        calls.append(True)
        return not (decision == "revoke" and len(calls) == 2)

    with factory() as db:
        if decision == "unknown_ack":
            commit = db.commit

            def lose_ack():
                commit()
                raise OperationalError("synthetic", {}, RuntimeError("ISOLATED_ACK_UNKNOWN"))

            db.commit = lose_ack
        if decision in {"revoke", "unknown_ack"}:
            with pytest.raises(ValueError if decision == "revoke" else OperationalError):
                abort_confirmed_writer(db, approval,
                    authority=SimpleNamespace(verify_exit_and_commits=verify))
        else:
            assert abort_confirmed_writer(db, approval,
                authority=SimpleNamespace(verify_exit_and_commits=verify)) == "RECONCILED_ABORTED"
    with factory() as reader:
        assert recovery_commit_status(reader, approval) == (
            "RECOVERY_COMMIT_UNCONFIRMED" if decision == "revoke" else "RECONCILED_ABORTED")
    with factory() as db:
        root, child = db.get(JobRun, approval.job_id), db.get(JobRun, child_id)
        dirty = db.get(DataDirtyRange, dirty_id)
        assert root.status == child.status == ("RUNNING" if decision == "revoke" else "FAILED")
        assert root.error_message == "ORIGINAL_ROOT_FAILURE"
        assert child.error_message == "ORIGINAL_CHILD_FAILURE"
        assert dirty.status == ("PROCESSING" if decision == "revoke" else "FAILED")
        assert dirty.retry_count == (2 if decision == "revoke" else 3)
        assert db.get(DataPublication, root.id).state == (
            "PREPARING" if decision == "revoke" else "ABORTED")
        rows = list(db.scalars(select(DataPublicationRow).where(
            DataPublicationRow.publication_id == root.id)))
        assert len(rows) == 1 and rows[0].is_deleted and rows[0].row_data is None
        assert len(root.job_metadata.get("manual_reconciliations", [])) == (decision != "revoke")
        assert len(child.job_metadata.get("manual_reconciliations", [])) == (decision != "revoke")
    assert published(factory) == before


def test_real_progress_timeout_then_recovery_preserves_monotonic_observations(observation,
                                                                          record_property):
    import json

    from app.services.worker_observation import HeartbeatHealth

    factory, engine, registry = observation
    e = registry.execution
    health, stamps = HeartbeatHealth(), []
    with engine.begin() as db:
        db.execute(text("""CREATE FUNCTION r2_progress_delay() RETURNS trigger LANGUAGE plpgsql
            AS $$ BEGIN IF NEW.job_metadata->'calculation_progress'->>'completed_rows' = '99'
            THEN PERFORM pg_sleep(4); END IF; RETURN NEW; END $$"""))
        db.execute(text("""CREATE TRIGGER r2_progress_delay BEFORE UPDATE ON job_run
            FOR EACH ROW EXECUTE FUNCTION r2_progress_delay()"""))
    for rows in (1, 99, 2):
        stamp = datetime.now(UTC)
        progress = dict(updated_at=stamp.isoformat(), advanced_at=stamp.isoformat(),
                        completed_rows=rows)
        with factory() as db:
            error = None
            try:
                assert touch_job_heartbeat(db, e.job_id, e.worker_id, execution_token=e.token,
                                           calculation_progress=progress)
            except DBAPIError as caught:
                assert rows == 99 and caught.orig.sqlstate == "57014"
                error = caught
                db.rollback()
            health.observe(db.info["heartbeat_diagnostics"], error)
        assert persist_observation(engine, registry, health=health.snapshot()) == "PERSISTED"
        with factory() as reader:
            job = reader.get(JobRun, e.job_id)
            state = job.job_metadata["heartbeat_health"]
            assert state["last_confirmed_at"] and state["computation_success_proven"] is False
            assert state["consecutive_failures"] == (1 if rows == 99 else 0)
            assert state["state"] == (
                "HEARTBEAT_DEGRADED" if rows == 99 else "COMMUNICATION_CONFIRMED")
            if rows == 99:
                assert state["phase"] == "progress_update" and state["sqlstate"] == "57014"
                assert job.job_metadata["calculation_progress"]["completed_rows"] == 1
            assert job.status == "RUNNING" and job.job_metadata["first_error"] == "preserved"
            stamps.append((job.heartbeat_at, job.last_progress_at))
    assert stamps == sorted(stamps)
    record_property("r2_heartbeat_observations", json.dumps(health.snapshot()))
