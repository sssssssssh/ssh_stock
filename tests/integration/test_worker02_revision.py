"""Real marked PG17 Worker lifecycle; never business/G1 connections."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services.recalculation import create_recalculation_job
from sqlalchemy import text

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_policy_worker_pg17 import run_until_idle
from tests.integration.test_business_recalc_performance import seed


@pytest.mark.parametrize("outcome", ["SUCCESS", "FAILED", "CANCELLED"])
def test_opt_in_actual_worker_persists_scoped_diagnostics_and_resets(monkeypatch, outcome):
    from app.services.execution_diagnostics import active_diagnostics
    from app.services.factors.service import FactorService
    from app.services.job_execution import JobCancelled

    settings = get_settings()
    # Works against the old code too: exposes the missing runtime installation,
    # rather than failing merely because the new setting is not yet declared.
    monkeypatch.setitem(settings.__dict__, "worker_diagnostics_enabled", True)
    with isolated_v14_database(monkeypatch) as (factory, _):
        days = seed(factory, include_closed=False, history_days=420)
        with factory() as db:
            key = create_recalculation_job(db, start=days[-2], end=days[-1],
                evaluate_signals=False, mode="manual").id
        if outcome != "SUCCESS":
            original = FactorService.recalc

            def stop(service, *args, **kwargs):
                original(service, *args, **kwargs)
                if outcome == "CANCELLED":
                    raise JobCancelled("JOB_CANCEL_REQUESTED")
                raise ValueError("ISOLATED_FAILURE")

            monkeypatch.setattr(FactorService, "recalc", stop)
        run_until_idle(factory, monkeypatch)
        assert active_diagnostics.get() is None
        with factory() as db:
            job = db.get(JobRun, key)
            assert job.status == outcome
            report = job.job_metadata["execution_diagnostics"]
            assert report["outcome"] == outcome
            assert report["root_job_id"] == str(key)
            assert report["execution_fingerprint"]
            assert len(report["phases"]) <= 128 and len(report["recent"]) <= 32
            metrics = {(x["name"], x["phase"]) for x in report["phases"]}
            assert ("trade_status.stock_daily", "fetch") in metrics
            assert ("trade_status.compute", "compute") in metrics
            assert ("trade_status.rows", "materialize") in metrics
            assert ("stock_trade_status_daily", "store") in metrics
            assert ("recalculation.raw_prerequisites", "query") in metrics
            assert ("factors.compute", "compute") in metrics
            if outcome == "SUCCESS":
                assert any(name.startswith("publication.") for name, _ in metrics)
            else:
                assert db.get(DataPublication, key).state == "ABORTED"
            assert str(job.execution_token) not in json.dumps(report)


@pytest.mark.parametrize("failed_phase", ["lease_commit", "progress_commit"])
def test_heartbeat_commit_ack_unknown_keeps_writer_and_reusable_connection(
    monkeypatch, failed_phase,
):
    from app.repositories.job_run import touch_job_heartbeat
    from sqlalchemy.exc import OperationalError

    with isolated_v14_database(monkeypatch) as (factory, _):
        with factory() as db:
            row = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic",
                         execution_token=uuid4(), heartbeat_at=datetime.now(UTC)-timedelta(hours=2),
                         job_metadata={"first_error": "preserved"})
            db.add(row)
            db.commit()
            key, token = row.id, row.execution_token
        with factory() as db:
            commit = db.commit
            committed = []

            def lose_ack():
                commit()
                committed.append(True)
                if len(committed) == (1 if failed_phase == "lease_commit" else 2):
                    raise OperationalError("synthetic", {}, RuntimeError("PRIVATE"),
                                           connection_invalidated=True)

            monkeypatch.setattr(db, "commit", lose_ack)
            with pytest.raises(OperationalError) as caught:
                touch_job_heartbeat(db, key, "synthetic", execution_token=token,
                    calculation_progress={"updated_at": datetime.now(UTC).isoformat()})
            assert caught.value.heartbeat_phase == failed_phase
            db.rollback()
            assert db.scalar(text("SELECT 1")) == 1
        with factory() as db:
            job = db.get(JobRun, key)
            assert job.status == "RUNNING" and job.job_metadata["first_error"] == "preserved"
            assert datetime.now(UTC)-job.heartbeat_at < timedelta(seconds=10)


def test_real_registered_backend_and_forged_name_have_different_evidence(monkeypatch):
    from app.services.data_job_reconcile import reconcile_data_job
    from app.services.job_execution import Execution
    from app.services.worker_observation import SessionRegistry, bind_session, persist_observation

    with isolated_v14_database(monkeypatch) as (factory, engine):
        with factory() as db:
            job = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic",
                         execution_token=uuid4(), job_metadata={})
            db.add(job)
            db.commit()
            key, token = job.id, job.execution_token
        registry = SessionRegistry(Execution(key, "synthetic", token, engine))
        with factory() as writer, engine.connect() as forged:
            bind_session(writer, registry, "main")
            actual_pid = writer.scalar(text("SELECT pg_backend_pid()"))
            fact = registry.snapshot()["roles"]["main"]["latest"]
            assert len(fact["application_name"].encode("ascii")) < 64
            forged.execute(text("SELECT set_config('application_name', :name, true)"),
                           {"name": fact["application_name"]})
            forged_pid = forged.scalar(text("SELECT pg_backend_pid()"))
            assert persist_observation(engine, registry) == "PERSISTED"
            with factory() as reader:
                report = reconcile_data_job(reader, key)
                found = {x["pid"]: x["identity_evidence"] for x in
                         report["matching_database_backends"]}
                assert found[actual_pid] == "REGISTERED_BACKEND_FACT_MATCH"
                assert found[forged_pid] == "NAME_ONLY_UNVERIFIED"
                assert not report["release_allowed"] and not report["process_exit_proven"]
            writer.rollback()
            forged.rollback()
        with factory() as reader:
            assert reader.scalar(text("SHOW application_name")) == ""
            report = reconcile_data_job(reader, key)
            assert not report["matching_database_backends"]
            assert report["decision"] == "EXECUTION_UNCONFIRMED"


@pytest.mark.parametrize("kind", ["expired", "future", "revoked", "unbounded", "child_identity",
                                  "queued_child"])
def test_invalid_approval_or_child_identity_has_no_recovery_writes(monkeypatch, kind):
    from app.services.data_job_reconcile import RecoveryApproval, abort_confirmed_writer

    with isolated_v14_database(monkeypatch) as (factory, _):
        now = datetime.now(UTC)
        with factory() as db:
            row = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic",
                         execution_token=uuid4(), job_metadata={})
            db.add(row)
            db.flush()
            key, token = row.id, row.execution_token
            db.add(DataPublication(job_id=key, execution_token=token, state="PREPARING",
                                   identity={}, row_counts={}))
            if kind in {"child_identity", "queued_child"}:
                db.add(JobRun(job_type="recalculate", status="QUEUED" if kind == "queued_child"
                    else "RUNNING", worker_id="other",
                    execution_token=uuid4(), parent_job_id=key, job_metadata={}))
            db.commit()
        approval = RecoveryApproval(key, "synthetic", token, "review", "operator", "a"*64,
            valid_from=now-timedelta(minutes=10) if kind == "expired" else now+timedelta(
                minutes=1) if kind == "future" else now-timedelta(seconds=1),
            valid_until=now-timedelta(minutes=9) if kind == "expired" else now+timedelta(
                hours=1) if kind == "unbounded" else now+timedelta(minutes=2),
            revoked_at=now if kind == "revoked" else None)
        from types import SimpleNamespace

        authority = SimpleNamespace(verify_exit_and_commits=lambda _: True)
        with factory() as db, pytest.raises(ValueError, match="RECOVERY_"):
            abort_confirmed_writer(db, approval, authority=authority)
        with factory() as db:
            assert db.get(JobRun, key).status == "RUNNING"
            assert db.get(JobRun, key).job_metadata == {}
            assert db.get(DataPublication, key).state == "PREPARING"


def test_observation_cas_preserves_cancel_and_refuses_reused_execution(monkeypatch):
    from app.services.job_execution import Execution
    from app.services.worker_observation import SessionRegistry, persist_observation
    from sqlalchemy import update

    with isolated_v14_database(monkeypatch) as (factory, engine):
        with factory() as db:
            job = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic",
                execution_token=uuid4(), cancel_requested=True,
                job_metadata={"publication": {"state": "PREPARING"}, "first_error": "preserved"})
            db.add(job)
            db.commit()
            key, token = job.id, job.execution_token
        registry = SessionRegistry(Execution(key, "synthetic", token, engine))
        assert persist_observation(engine, registry, diagnostics={"outcome": "UNCONFIRMED"}) == \
            "PERSISTED"
        # An in-flight heartbeat must not overwrite a final unconfirmed receipt.
        assert persist_observation(engine, registry,
            diagnostics={"outcome": "RUNNING_OBSERVATION"}) == "CAS_NOT_APPLIED"
        with factory() as db:
            job = db.get(JobRun, key)
            assert job.cancel_requested and job.job_metadata["first_error"] == "preserved"
            before = dict(job.job_metadata)
            db.execute(update(JobRun).where(JobRun.id == key).values(execution_token=uuid4()))
            db.commit()
        assert persist_observation(engine, registry) == "CAS_NOT_APPLIED"
        with factory() as db:
            assert db.get(JobRun, key).job_metadata == before


@pytest.mark.parametrize("snapshot_failure", [False, True])
def test_live_heartbeat_persists_diagnostics_and_survives_observer_failure(
    monkeypatch, snapshot_failure,
):
    from app.services import job_worker
    from app.services.execution_diagnostics import ExecutionDiagnostics
    from app.services.job_execution import Execution
    from app.services.worker_observation import SessionRegistry

    class Stop:
        calls = 0

        def wait(self, _):
            self.calls += 1
            return self.calls > 2

    with isolated_v14_database(monkeypatch) as (factory, engine):
        with factory() as db:
            job = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic",
                         execution_token=uuid4(), job_metadata={})
            db.add(job)
            db.commit()
            key, token = job.id, job.execution_token
        registry = SessionRegistry(Execution(key, "synthetic", token, engine))
        recorder = ExecutionDiagnostics()
        recorder.record("trade_status.compute", "compute", 0.2)
        if snapshot_failure:
            def unavailable():
                raise RuntimeError("PRIVATE_DIAGNOSTIC_FAILURE")
            monkeypatch.setattr(recorder, "snapshot", unavailable)
        monkeypatch.setattr(job_worker, "SessionLocal", factory)
        job_worker._run_heartbeat_loop(key, "synthetic", Stop(), interval_seconds=0.01,
            execution_token=token, registry=registry, diagnostics=recorder)
        with factory() as db:
            job = db.get(JobRun, key)
            assert job.status == "RUNNING"
            assert job.job_metadata["heartbeat_health"]["state"] == "COMMUNICATION_CONFIRMED"
            assert set(job.job_metadata["database_sessions"]["roles"]) == {
                "heartbeat", "diagnostic"}
            if snapshot_failure:
                assert "execution_diagnostics" not in job.job_metadata
            else:
                assert job.job_metadata["execution_diagnostics"]["phases"][0]["seconds"] == 0.2


def test_real_worker_on_off_financial_frames_dtypes_and_hashes_are_identical(monkeypatch):
    import hashlib

    import pandas as pd
    from app.models.market_data import StockFactorDaily, StockTradeStatusDaily
    from sqlalchemy import select

    with isolated_v14_database(monkeypatch) as (factory, _):
        days = seed(factory, include_closed=False, history_days=420)
        results, reports = [], []
        for enabled in (False, True):
            monkeypatch.setattr(get_settings(), "worker_diagnostics_enabled", enabled)
            with factory() as db:
                key = create_recalculation_job(db, start=days[-2], end=days[-1],
                    evaluate_signals=False, mode="manual").id
            run_until_idle(factory, monkeypatch)
            with factory() as db:
                job = db.get(JobRun, key)
                assert job.status == "SUCCESS"
                reports.append(job.job_metadata.get("execution_diagnostics"))
                frames = []
                for model in (StockFactorDaily, StockTradeStatusDaily):
                    columns = [c for c in model.__table__.columns
                               if c.name not in {"calc_run_id", "calculated_at"}]
                    frame = pd.DataFrame(db.execute(select(*columns).order_by(
                        model.trade_date, model.ts_code)).mappings().all())
                    assert not frame.empty
                    frames.append(frame)
                results.append(frames)
        assert reports[0] is None and reports[1]["outcome"] == "SUCCESS"
        for before, after in zip(*results, strict=True):
            pd.testing.assert_frame_equal(before, after, check_exact=True)
            assert hashlib.sha256(pd.util.hash_pandas_object(before).values.tobytes()).digest() == \
                hashlib.sha256(pd.util.hash_pandas_object(after).values.tobytes()).digest()


def test_snapshot_context_resets_even_when_workspace_cleanup_raises(monkeypatch):
    from app.services import job_worker
    from app.services.calculation_policy import active_policy
    from app.services.calculation_progress import current_progress
    from app.services.data_publication import PublicationWorkspace
    from app.services.execution_diagnostics import active_diagnostics
    from app.services.job_execution import current_execution

    with isolated_v14_database(monkeypatch) as (factory, _):
        monkeypatch.setattr(get_settings(), "worker_diagnostics_enabled", True)
        days = seed(factory, include_closed=False, history_days=420)
        with factory() as db:
            key = create_recalculation_job(db, start=days[-2], end=days[-1],
                evaluate_signals=False, mode="manual").id
        original = PublicationWorkspace.close

        def fail_close(workspace):
            original(workspace)
            raise RuntimeError("ISOLATED_CLEANUP_FAILURE")

        monkeypatch.setattr(PublicationWorkspace, "close", fail_close)
        with pytest.raises(RuntimeError, match="ISOLATED_CLEANUP_FAILURE"):
            run_until_idle(factory, monkeypatch)
        assert active_diagnostics.get() is current_execution.get() is current_progress.get() is None
        # Existing observer/policy cleanup must also run before propagating a
        # workspace cleanup fault, rather than leaking into the next claimed Job.
        assert active_policy.get() is None
        assert job_worker.current_execution.get() is None
        with factory() as db:
            assert db.get(JobRun, key).job_metadata["execution_diagnostics"]["outcome"] == "SUCCESS"


def test_observation_never_joins_or_rolls_back_pinned_computation_transaction(monkeypatch):
    from app.services.job_execution import Execution
    from app.services.worker_observation import SessionRegistry, persist_observation
    from sqlalchemy import update

    with isolated_v14_database(monkeypatch) as (factory, engine):
        with factory() as db:
            job = JobRun(job_type="recalculate", status="RUNNING", worker_id="synthetic",
                         execution_token=uuid4(), job_metadata={})
            db.add(job)
            db.commit()
            key, token = job.id, job.execution_token
        with engine.connect() as pinned:
            transaction = pinned.begin()
            pinned.execute(update(JobRun).where(JobRun.id == key).values(step="uncommitted"))
            registry = SessionRegistry(Execution(key, "synthetic", token, pinned))
            assert persist_observation(pinned, registry) == "DIAGNOSTIC_PERSIST_UNCONFIRMED"
            assert transaction.is_active
            assert pinned.scalar(text("SELECT step FROM job_run WHERE id=:id"),
                                 {"id": key}) == "uncommitted"
            transaction.rollback()
        with factory() as db:
            assert db.get(JobRun, key).step is None
            assert db.get(JobRun, key).job_metadata == {}
