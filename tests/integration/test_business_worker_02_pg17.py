"""Real isolated PG17 heartbeat, never an incident database or G1 probe."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.models.job import JobRun
from app.repositories.job_run import touch_job_heartbeat
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from scripts.v14_test_database import isolated_v14_database


@pytest.fixture
def database(monkeypatch):
    with isolated_v14_database(monkeypatch) as value:
        factory, engine = value
        with factory() as db:
            job = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic-worker",
                         execution_token=uuid4(), heartbeat_at=datetime.now(UTC)-timedelta(hours=2),
                         job_metadata={"unrelated": "preserved"})
            db.add(job)
            db.commit()
            identity = job.id, job.worker_id, job.execution_token
        yield factory, engine, identity


def snapshot(stamp=None):
    return dict(updated_at=(stamp or datetime.now(UTC)).isoformat(), advanced_at=None,
                phase="fetch", completed_rows=785000)


def test_heartbeat_lease_survives_real_progress_statement_timeout(database, record_property):
    import json

    factory, engine, (job_id, owner, token) = database

    # A real server-side UPDATE trigger incurs progress-only work under the
    # unchanged production timeout, rather than fabricating an ORM exception.
    with engine.begin() as db:
        db.execute(text("""CREATE FUNCTION isolated_progress_delay() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.job_metadata IS DISTINCT FROM OLD.job_metadata THEN PERFORM pg_sleep(4);
            END IF; RETURN NEW; END $$"""))
        db.execute(text("""CREATE TRIGGER isolated_progress_delay BEFORE UPDATE ON job_run
            FOR EACH ROW EXECUTE FUNCTION isolated_progress_delay()"""))
    with factory() as db, pytest.raises(DBAPIError) as caught:
        touch_job_heartbeat(db, job_id, owner, execution_token=token,
                            calculation_progress=snapshot())
    assert caught.value.orig.sqlstate == "57014"
    record_property("heartbeat_timings", json.dumps(db.info["heartbeat_diagnostics"]))
    with factory() as db:
        job = db.get(JobRun, job_id)
        assert datetime.now(UTC)-job.heartbeat_at < timedelta(seconds=10)
        assert job.job_metadata == {"unrelated": "preserved"}
        assert job.status == "RUNNING" and job.execution_token == token
    assert caught.value.heartbeat_phase == "progress_update"


def test_real_lock_timeout_is_not_statement_timeout_or_executor_death(database, record_property):
    import json
    import time
    from concurrent.futures import ThreadPoolExecutor
    from queue import Queue

    factory, _, (job_id, owner, token) = database
    pids = Queue()

    def heartbeat():
        with factory() as writer:
            pids.put(writer.scalar(text("SELECT pg_backend_pid()")))
            try:
                touch_job_heartbeat(writer, job_id, owner, execution_token=token,
                                    calculation_progress=snapshot())
            except DBAPIError as exc:
                return exc, writer.info["heartbeat_diagnostics"]
        pytest.fail("Real held row lock must reach the unchanged lock timeout")

    with factory() as blocker, factory() as observer, ThreadPoolExecutor(1) as executor:
        blocker.execute(update(JobRun).where(JobRun.id == job_id).values(step="held"))
        pending = executor.submit(heartbeat)
        pid = pids.get(timeout=3)
        observed = None
        deadline = time.monotonic()+0.8
        while time.monotonic() < deadline:
            observed = observer.execute(text("SELECT wait_event_type, wait_event, "
                "pg_blocking_pids(pid) AS blockers FROM pg_stat_activity WHERE pid=:pid"),
                {"pid": pid}).mappings().one()
            # New snapshots each time, rather than PG's transaction-cached stats.
            observer.rollback()
            if observed["wait_event_type"] == "Lock" and observed["blockers"]:
                break
            time.sleep(0.01)
        error, metrics = pending.result(timeout=5)
        record_property("wait_evidence", json.dumps(dict(observed)))
        record_property("heartbeat_timings", json.dumps(metrics))
        assert observed["wait_event_type"] == "Lock" and observed["blockers"]
        assert error.orig.sqlstate == "55P03"
        assert error.heartbeat_phase == "lease_update"
        assert observer.get(JobRun, job_id).status == "RUNNING"
        blocker.rollback()


def test_no_wait_monotonic_progress_cancel_and_owner_cas(database, record_property):
    import json

    factory, _, (job_id, owner, token) = database
    stamp = datetime.now(UTC)
    with factory() as db:
        assert touch_job_heartbeat(db, job_id, owner, execution_token=token,
                                   calculation_progress=snapshot(stamp))
        assert {r["phase"] for r in db.info["heartbeat_diagnostics"]} >= {
            "lease_update", "lease_commit", "progress_update", "progress_commit"}
        record_property("heartbeat_timings", json.dumps(db.info["heartbeat_diagnostics"]))
        db.execute(update(JobRun).where(JobRun.id == job_id).values(cancel_requested=True))
        db.commit()
        assert touch_job_heartbeat(db, job_id, owner, execution_token=token,
                                   calculation_progress=snapshot(stamp-timedelta(seconds=1)))
        db.expire_all()
        job = db.get(JobRun, job_id)
        assert job.cancel_requested and job.job_metadata["calculation_progress"] == snapshot(stamp)
        before = job.heartbeat_at
        assert not touch_job_heartbeat(db, job_id, owner, execution_token=uuid4())
        db.expire_all()
        assert db.scalar(select(JobRun.heartbeat_at).where(JobRun.id == job_id)) == before


def test_readonly_reconcile_never_infers_exit_or_releases_writer(database):
    from app.services.data_job_reconcile import reconcile_data_job

    factory, _, (job_id, _, _) = database
    with factory() as db:
        report = reconcile_data_job(db, job_id)
        assert report["decision"] == "EXECUTION_UNCONFIRMED"
        assert report["release_allowed"] is False and report["dry_run"] is True
        assert "synthetic-worker" not in str(report)
        assert db.scalar(text("SHOW transaction_read_only")) == "on"
    with factory() as db:
        assert db.get(JobRun, job_id).status == "RUNNING"


def preparing(factory, identity):
    from app.models.data_publication import DataPublication

    with factory() as db:
        db.add(DataPublication(job_id=identity[0], execution_token=identity[2],
                               state="PREPARING", identity={}, row_counts={}))
        db.commit()


@pytest.mark.parametrize("case", ["no_authority", "alive", "pending_commit", "publishing"])
def test_unconfirmed_writer_keeps_lane_and_no_audit_is_fabricated(database, case):
    from types import SimpleNamespace

    from app.models.data_publication import DataPublication
    from app.services.data_job_reconcile import RecoveryApproval, abort_confirmed_writer

    factory, _, identity = database
    preparing(factory, identity)
    approval = RecoveryApproval(*identity, "isolated-review", "isolated-operator", "a" * 64)
    authority = None if case == "no_authority" else SimpleNamespace(
        verify_exit_and_commits=lambda _: case == "publishing")
    if case == "publishing":
        with factory() as db:
            ledger = db.get(DataPublication, identity[0])
            ledger.publish_started_at = datetime.now(UTC)
            db.commit()
    with factory() as db, pytest.raises(ValueError, match="UNCONFIRMED"):
        abort_confirmed_writer(db, approval, authority=authority)
    with factory() as db:
        assert db.get(JobRun, identity[0]).status == "RUNNING"
        assert db.get(DataPublication, identity[0]).state == "PREPARING"
        assert "manual_reconciliations" not in db.get(JobRun, identity[0]).job_metadata


@pytest.mark.parametrize("lost_ack", [False, True])
def test_operator_abort_after_owned_child_exit_is_atomic_and_idempotent(database, lost_ack):
    import subprocess
    import sys

    from app.models.data_publication import DataPublication, DataPublicationRow
    from app.services.data_job_reconcile import RecoveryApproval, abort_confirmed_writer
    from sqlalchemy.exc import OperationalError

    factory, _, identity = database
    preparing(factory, identity)
    with factory() as db:
        db.add(DataPublicationRow(publication_id=identity[0], table_name="stock_factor_daily",
                                 row_key=("2024-01-02", "SYNTHETIC"), row_data={"value": 9},
                                 source_id=identity[0], is_deleted=False))
        job = db.get(JobRun, identity[0])
        job.error_message = "ORIGINAL_FAILURE"
        child = JobRun(job_type="recalculate", status="RUNNING", worker_id=identity[1],
                       execution_token=identity[2], parent_job_id=identity[0], job_metadata={})
        db.add(child)
        db.commit()
        child_id = child.id
    # The only test executor is a real bounded owned child. This confirms local
    # test exit only, never all production hosts or containers.
    process = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.DEVNULL)
    process.wait(timeout=10)

    class LocalTestAuthority:
        def verify_exit_and_commits(self, received):
            return received == approval and process.poll() == 0

    approval = RecoveryApproval(*identity, "isolated-review", "isolated-operator", "b" * 64)
    with factory() as db:
        if lost_ack:
            original_commit = db.commit

            def ack_loss():
                original_commit()
                raise OperationalError("synthetic", {}, RuntimeError("PRIVATE_ACK"),
                                       connection_invalidated=True)

            db.commit = ack_loss
            with pytest.raises(OperationalError):
                abort_confirmed_writer(db, approval, authority=LocalTestAuthority())
        else:
            assert abort_confirmed_writer(db, approval, authority=LocalTestAuthority()) == \
                "RECONCILED_ABORTED"
    with factory() as db:
        assert abort_confirmed_writer(db, approval, authority=LocalTestAuthority()) == \
            "ALREADY_RECONCILED"
    with factory() as db:
        root = db.get(JobRun, identity[0])
        assert root.status == db.get(JobRun, child_id).status == "FAILED"
        assert root.error_message == "ORIGINAL_FAILURE"
        assert db.get(DataPublication, identity[0]).state == "ABORTED"
        assert len(root.job_metadata["manual_reconciliations"]) == 1
        assert db.get(DataPublicationRow, (identity[0], "stock_factor_daily",
                                         ("2024-01-02", "SYNTHETIC"))) is not None


def test_real_connection_termination_does_not_release_or_replay(database):
    from sqlalchemy import event

    factory, engine, (job_id, owner, token) = database
    killed = []

    def disconnect(connection, cursor, statement, parameters, context, many):
        if "UPDATE job_run" in statement and not killed:
            pid = cursor.connection.info.backend_pid
            killed.append(pid)
            with engine.connect() as killer:
                assert killer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

    event.listen(engine, "before_cursor_execute", disconnect)
    try:
        with factory() as db, pytest.raises(DBAPIError) as caught:
            touch_job_heartbeat(db, job_id, owner, execution_token=token)
        assert caught.value.connection_invalidated
        assert caught.value.heartbeat_phase == "lease_update"
    finally:
        event.remove(engine, "before_cursor_execute", disconnect)
    with factory() as db:
        job = db.get(JobRun, job_id)
        assert job.status == "RUNNING" and job.execution_token == token
        assert datetime.now(UTC)-job.heartbeat_at > timedelta(hours=1)
