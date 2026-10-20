"""Synthetic PG17 lifecycle/concurrency acceptance; never uses application .env."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Event
from uuid import uuid4

import pytest
from app.api.v1.jobs import cancel_job, data_queue
from app.models.job import JobRun
from app.repositories.job_run import update_job
from app.services.job_execution import Execution, JobOwnershipLost, current_execution
from app.services.job_guard import create_queued_ingestion_job, recover_stale_ingestion_jobs
from app.services.job_worker import claim_next_job
from app.services.job_worker import execute_claimed_job as execute_owned_job
from sqlalchemy import select, text

from tests.integration.m16_6_support import isolated_contract_database


@pytest.fixture
def database(monkeypatch):
    with isolated_contract_database(monkeypatch) as value:
        yield value


def enqueue(factory, n=1, **extra):
    with factory() as db:
        return create_queued_ingestion_job(
            db,
            "backfill",
            date(2026, 9, n),
            step="queued",
            metadata={"start": f"2026-09-{n:02}", "end": f"2026-09-{n:02}", **extra},
        ).id


def execute_claimed_job(db, key):
    row = db.get(JobRun, key)
    return execute_owned_job(
        db, key, expected_worker=row.worker_id, expected_token=row.execution_token
    )


def test_continuous_enqueue_dedup_fifo_and_two_workers(database):
    factory, engine = database
    ids = [enqueue(factory, n) for n in (1, 2, 3)]
    assert enqueue(factory, 2) == ids[1]
    barrier = Barrier(2)

    def claim(name):
        with factory() as db:
            barrier.wait()
            return claim_next_job(db, name)

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(claim, ("worker-a", "worker-b")))
    assert results.count(None) == 1
    assert ids[0] in results
    with factory() as db:
        payload = data_queue(db)["data"]
        assert [x["id"] for x in payload["queued"]] == [str(x) for x in ids[1:]]
        assert [x["queue_position"] for x in payload["queued"]] == [1, 2]
        assert db.get(JobRun, ids[0]).execution_started_at is not None
        assert enqueue(factory, 4) is not None


def test_parallel_duplicates_return_one_job(database):
    factory, _ = database
    barrier = Barrier(2)

    def submit(_):
        barrier.wait()
        return enqueue(factory)

    with ThreadPoolExecutor(2) as pool:
        ids = list(pool.map(submit, (1, 2)))
    assert ids[0] == ids[1]


def test_queued_cancel_never_claimed_and_terminal_immutable(database):
    factory, _ = database
    first, second = enqueue(factory, 1), enqueue(factory, 2)
    with factory() as db:
        response = cancel_job(first, db)
        assert response["meta"]["cancel_completed"]
        assert cancel_job(first, db)["data"]["status"] == "CANCELLED"
        assert claim_next_job(db, "worker") == second
    with factory() as db:
        assert db.get(JobRun, first).status == "CANCELLED"


def test_running_cancel_holds_slot_until_real_exit(database, monkeypatch):
    factory, engine = database
    import app.services.job_worker as worker

    first, second = enqueue(factory, 1), enqueue(factory, 2)
    entered, release = Event(), Event()
    monkeypatch.setattr(worker, "SessionLocal", factory)

    def business(self, *args, job, **kwargs):
        entered.set()
        assert release.wait(10)
        update_job(self.db, job, status="SUCCESS")

    monkeypatch.setattr(worker.BackfillJob, "run", business)
    monkeypatch.setattr(worker, "_provider", lambda db: object())
    with factory() as db:
        assert claim_next_job(db, "worker") == first

    def run():
        with factory() as db:
            execute_claimed_job(db, first)

    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(run)
        assert entered.wait(10)
        with factory() as db:
            reply = cancel_job(first, db)
            assert reply["data"]["status"] == "RUNNING"
            assert reply["meta"] == {"cancel_accepted": True, "cancel_completed": False}
            assert claim_next_job(db, "other") is None
        release.set()
        future.result(timeout=10)
    with factory() as db:
        assert db.get(JobRun, first).status == "CANCELLED"
        assert claim_next_job(db, "other") == second


def test_waiting_and_unconfirmed_running_do_not_expire(database):
    factory, _ = database
    key = enqueue(factory)
    with factory() as db:
        job = db.get(JobRun, key)
        job.started_at = datetime.now(UTC) - timedelta(days=30)
        db.commit()
        assert recover_stale_ingestion_jobs(db) == 0
        assert claim_next_job(db, "worker") == key
        job.heartbeat_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
        assert recover_stale_ingestion_jobs(db) == 0
        assert claim_next_job(db, "other") is None


def test_dependency_failure_and_config_change_fail_closed(database):
    factory, _ = database
    first = enqueue(factory)
    child = enqueue(factory, 2, depends_on_job_id=str(first))
    with factory() as db:
        cancel_job(first, db)
        assert claim_next_job(db, "worker") is None
        assert db.get(JobRun, child).status == "BLOCKED"
    third = enqueue(factory, 3)
    with factory() as db:
        job = db.get(JobRun, third)
        job.job_metadata = {**job.job_metadata, "queue_identity": {"analysis": "old"}}
        db.commit()
        assert claim_next_job(db, "worker") is None
        assert db.get(JobRun, third).error_message == "JOB_CONFIG_CHANGED"


def test_old_worker_cannot_publish_success_after_token_changed(database):
    factory, engine = database
    key = enqueue(factory)
    with factory() as db:
        claim_next_job(db, "old")
        job = db.get(JobRun, key)
        context = current_execution.set(Execution(key, "old", job.execution_token, engine))
        try:
            with factory() as other:
                row = other.get(JobRun, key)
                row.execution_token = uuid4()
                other.commit()
            with pytest.raises(JobOwnershipLost):
                update_job(db, job, status="SUCCESS")
        finally:
            current_execution.reset(context)


def test_data_timeouts_are_transaction_local(database):
    factory, _ = database
    with factory() as db:
        baseline = db.scalar(text("SHOW statement_timeout"))
        db.rollback()
        db.info["data_task_timeouts"] = True
        assert db.scalar(text("SHOW statement_timeout")) == "5min"
        assert db.scalar(text("SHOW lock_timeout")) == "5s"
        db.rollback()
        db.info.clear()
        assert db.scalar(text("SHOW statement_timeout")) == baseline


@pytest.mark.parametrize(
    "kind,first,next_stage",
    [
        ("daily", "sync_trade_calendar", "sync_stock_basic"),
        ("sync_basic", "sync_stock_basic", "sync_sector_metadata"),
    ],
)
def test_real_stage_orchestration_cancels_before_next_stage(
    database,
    monkeypatch,
    kind,
    first,
    next_stage,
):
    import app.jobs.basic_info_job as basic
    import app.jobs.daily_job as daily
    import app.services.job_worker as worker

    factory, _ = database
    calls = []
    with factory() as db:
        key = create_queued_ingestion_job(
            db, kind, date(2026, 9, 1), step="queued", metadata={"trade_date": "2026-09-01"}
        ).id
        assert claim_next_job(db, "worker") == key

    class Ingestion:
        def __init__(self, *args):
            pass

        def __getattr__(self, name):
            def call(*args, **kwargs):
                calls.append(name)
                if name == first:
                    with factory() as cancellation:
                        cancel_job(key, cancellation)
                return 1

            return call

    monkeypatch.setattr(basic, "IngestionService", Ingestion)
    monkeypatch.setattr(daily, "IngestionService", Ingestion)
    monkeypatch.setattr(daily, "trade_calendar_open_status", lambda *args: True)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker, "_provider", lambda db: object())
    with factory() as db:
        execute_claimed_job(db, key)
        assert db.get(JobRun, key).status == "CANCELLED"
    assert calls == [first] and next_stage not in calls


def test_real_monthly_recalculation_preserves_commit_and_reopens_dirty(database, monkeypatch):
    import app.services.job_worker as worker
    import app.services.recalculation as recalc
    from app.models.market_data import DataDirtyRange, DataQualityDaily

    factory, _ = database
    day = date(2026, 9, 1)
    with factory() as db:
        dirty = DataDirtyRange(dataset="synthetic", dirty_start_date=day, dirty_end_date=day)
        db.add(dirty)
        db.commit()
        dirty_id = dirty.id
        key = create_queued_ingestion_job(
            db,
            "recalculate",
            day,
            step="queued",
            metadata={
                "start": day.isoformat(),
                "end": "2026-10-01",
                "dirty_range_ids": [dirty_id],
            },
        ).id
        claim_next_job(db, "worker")
    calls = []

    class TradeStatus:
        def __init__(self, db):
            pass

        def recalc(self, *args, **kwargs):
            return 1

    class Factor:
        def __init__(self, db):
            self.db = db

        def recalc(self, *args, **kwargs):
            calls.append(args)
            from app.repositories.upsert import upsert_rows

            upsert_rows(
                self.db,
                DataQualityDaily,
                [
                    {
                        "trade_date": day,
                        "dataset": "synthetic_complete_chunk",
                        "status": "PASS",
                        "actual_rows": 1,
                        "expected_rows": 1,
                        "job_id": key,
                    }
                ],
                ["trade_date", "dataset"],
            )
            self.db.commit()
            with factory() as cancellation:
                cancel_job(key, cancellation)
            return 1

    monkeypatch.setattr(recalc, "TradeStatusService", TradeStatus)
    monkeypatch.setattr(recalc, "FactorService", Factor)
    monkeypatch.setattr(recalc, "_factor_warmup_start", lambda db, start: start)
    monkeypatch.setattr(recalc, "validate_recalculation_raw_prerequisites", lambda *a, **kw: None)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    with factory() as db:
        from app.models.market_data import TradeCalendar

        # The orchestration fixture must also satisfy the new real calendar
        # boundary, not bypass it or weaken the cancellation assertions.
        current = day
        while current <= date(2026, 10, 1):
            db.merge(TradeCalendar(cal_date=current, is_open=current.weekday()<5))
            current += timedelta(days=1)
        db.commit()
        execute_claimed_job(db, key)
    with factory() as db:
        assert db.get(JobRun, key).status == "CANCELLED"
        dirty = db.get(DataDirtyRange, dirty_id)
        assert dirty.status == "OPEN" and dirty.retry_count == 0
        from app.models.data_publication import DataPublicationRow

        evidence = db.scalar(
            select(DataPublicationRow.row_data).where(
                DataPublicationRow.publication_id == key,
                DataPublicationRow.table_name == "data_quality_daily",
            )
        )
        assert evidence["status"] == "PASS" and evidence["actual_rows"] == 1
        assert evidence["job_id"] == str(key)
        assert (
            db.scalar(select(DataQualityDaily.status).where(DataQualityDaily.job_id == key)) is None
        )
    assert len(calls) == 1


@pytest.mark.parametrize("cancel_child", [False, True])
def test_catchup_links_and_cancels_parent_child_before_releasing_slot(
    database,
    monkeypatch,
    cancel_child,
):
    import app.jobs.catchup_job as catchup
    import app.services.job_worker as worker
    from app.services.job_execution import checkpoint

    factory, _ = database
    day = date(2026, 9, 1)
    with factory() as db:
        key = create_queued_ingestion_job(
            db, "catchup", day, step="queued", metadata={"trade_date": day.isoformat()}
        ).id
        claim_next_job(db, "worker")

    class Ingestion:
        def __init__(self, *args):
            pass

        def sync_trade_calendar(self, *args):
            return 0

        def sync_stock_basic(self):
            return 0

    def calculation(db, child, *args, **kw):
        assert child.parent_job_id == key
        assert child.job_metadata["execution_owner"] == "catchup"
        with factory() as cancellation:
            cancel_job(child.id if cancel_child else key, cancellation)
            assert claim_next_job(cancellation, "other") is None
        checkpoint()
        pytest.fail("parent cancellation must reach the child")

    monkeypatch.setattr(catchup, "IngestionService", Ingestion)
    monkeypatch.setattr(catchup, "_open_trade_dates", lambda *a: [day])
    monkeypatch.setattr(catchup, "classify_catchup_dates", lambda *a, **kw: ([], [day]))
    monkeypatch.setattr(catchup.CatchUpJob, "_theme_repair_dates", lambda *a: [])
    monkeypatch.setattr(catchup, "latest_raw_trade_date", lambda *a: day)
    monkeypatch.setattr(catchup, "run_recalculation", calculation)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker, "_provider", lambda db: object())
    with factory() as db:
        execute_claimed_job(db, key)
    with factory() as db:
        rows = list(db.scalars(select(JobRun).order_by(JobRun.started_at)))
        assert len(rows) == 2 and all(row.status == "CANCELLED" for row in rows)
        assert rows[1].parent_job_id == key


def test_locked_head_does_not_get_overtaken(database, monkeypatch):
    import app.services.job_guard as guard
    from sqlalchemy.exc import OperationalError

    factory, _ = database
    first, second = enqueue(factory), enqueue(factory, 2)
    original = guard.scheduler_setting
    monkeypatch.setattr(
        guard,
        "scheduler_setting",
        lambda name, default: 100 if name == "data_lock_timeout_ms" else original(name, default),
    )
    with factory() as locker:
        locker.execute(select(JobRun).where(JobRun.id == first).with_for_update()).scalar_one()
        with factory() as contender, pytest.raises(OperationalError) as error:
            claim_next_job(contender, "worker")
        assert error.value.orig.sqlstate == "55P03"
    with factory() as db:
        assert db.get(JobRun, second).status == "QUEUED"
        assert claim_next_job(db, "worker") == first


def test_scheduler_queues_behind_manual_work_and_deduplicates(database):
    from app.jobs.scheduler import run_scheduled_basic_info, run_scheduled_catchup

    factory, _ = database
    enqueue(factory)
    with factory() as db:
        claim_next_job(db, "worker")
        assert run_scheduled_catchup(db, None, date(2026, 9, 1))
        assert not run_scheduled_catchup(db, None, date(2026, 9, 1))
        assert run_scheduled_basic_info(db, None)
        assert not run_scheduled_basic_info(db, None)
        assert data_queue(db)["data"]["queued_count"] == 2


def test_claim_cancel_race_has_only_two_legal_outcomes(database):
    factory, _ = database
    key = enqueue(factory)
    barrier = Barrier(2)

    def claim():
        with factory() as db:
            barrier.wait()
            return claim_next_job(db, "worker")

    def cancel():
        with factory() as db:
            barrier.wait()
            return cancel_job(key, db)

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(claim), pool.submit(cancel)
        claimed, cancelled = a.result(timeout=10), b.result(timeout=10)
    with factory() as db:
        row = db.get(JobRun, key)
        assert row.cancel_requested and row.cancel_requested_at is not None
        if claimed is None:
            assert row.status == "CANCELLED" and cancelled["meta"]["cancel_completed"]
        else:
            assert row.status == "RUNNING" and not cancelled["meta"]["cancel_completed"]


def test_legacy_rows_and_nonempty_upgrade_preserve_original_timestamps(database):
    from alembic import command
    from alembic.config import Config

    factory, engine = database
    key, stamp = uuid4(), datetime(2020, 1, 2, tzinfo=UTC)
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0056_suspend_timing_text")
        connection.execute(
            text(
                "INSERT INTO job_run (id, job_type, status, started_at, "
                "row_count, cancel_requested, job_metadata) VALUES "
                "(:id, 'backfill', 'SUCCESS', :stamp, 12, false, "
                "jsonb_build_object('legacy', true))"
            ),
            {"id": key, "stamp": stamp},
        )
        command.upgrade(config, "head")
    with factory() as db:
        job = db.get(JobRun, key)
        assert job.started_at == stamp and job.row_count == 12
        assert job.execution_started_at is job.execution_token is job.last_progress_at is None
        assert job.job_metadata == {"legacy": True}


def test_capacity_is_explicit_and_duplicates_do_not_consume_it(database, monkeypatch):
    import app.services.job_guard as guard

    factory, _ = database
    original = guard.scheduler_setting
    monkeypatch.setattr(
        guard,
        "scheduler_setting",
        lambda name, default: 1 if name == "data_queue_capacity" else original(name, default),
    )
    key = enqueue(factory)
    assert enqueue(factory) == key
    with pytest.raises(guard.QueueCapacityError, match="QUEUE_CAPACITY_EXCEEDED"):
        enqueue(factory, 2)


def test_queue_is_not_truncated_by_recent_history(database):
    from app.api.v1.jobs import list_jobs

    factory, _ = database
    key = enqueue(factory)
    with factory() as db:
        for _ in range(35):
            db.add(JobRun(job_type="backfill", status="SUCCESS", row_count=0, job_metadata={}))
        db.commit()
        assert str(key) not in {row["id"] for row in list_jobs(limit=30, db=db)["data"]}
        assert data_queue(db)["data"]["queued"][0]["id"] == str(key)


def test_cancel_success_race_and_terminal_cas(database):
    from app.repositories.job_run import finish_cancelled
    from app.services.job_execution import JobCancelled, JobOwnershipLost
    from fastapi import HTTPException

    factory, engine = database
    key = enqueue(factory)
    with factory() as db:
        claim_next_job(db, "worker")
        token = db.get(JobRun, key).execution_token
    barrier = Barrier(2)

    def success():
        with factory() as db:
            job = db.get(JobRun, key)
            context = current_execution.set(Execution(key, "worker", token, engine))
            try:
                barrier.wait()
                try:
                    update_job(db, job, status="SUCCESS")
                    return "SUCCESS"
                except JobCancelled:
                    db.rollback()
                    finish_cancelled(db, job)
                    return "CANCELLED"
            finally:
                current_execution.reset(context)

    def cancellation():
        with factory() as db:
            barrier.wait()
            try:
                return cancel_job(key, db)
            except HTTPException as error:
                assert error.status_code == 409
                return None

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(success), pool.submit(cancellation)
        final, reply = a.result(timeout=10), b.result(timeout=10)
    with factory() as db:
        job = db.get(JobRun, key)
        assert job.status == final
        if final == "SUCCESS":
            assert reply is None and not job.cancel_requested
        else:
            assert reply["meta"]["cancel_accepted"] and job.cancel_requested
        context = current_execution.set(Execution(key, "worker", token, engine))
        try:
            with pytest.raises(JobOwnershipLost):
                update_job(db, job, status="FAILED")
        finally:
            current_execution.reset(context)


def test_partial_unique_fingerprint_and_self_dependency_are_database_enforced(database):
    from sqlalchemy.exc import IntegrityError

    factory, _ = database
    key = enqueue(factory)
    with factory() as db:
        original = db.get(JobRun, key)
        with pytest.raises(IntegrityError), db.begin_nested():
            db.add(
                JobRun(
                    job_type="backfill",
                    status="QUEUED",
                    request_fingerprint=original.request_fingerprint,
                )
            )
            db.flush()
        with pytest.raises(IntegrityError), db.begin_nested():
            original.depends_on_job_id = key
            db.flush()
        db.rollback()
    with factory() as db:
        cancel_job(key, db)
    assert enqueue(factory) != key


def test_running_research_is_not_deferred_by_new_data_queue(database):
    import app.jobs.research_job as research
    from app.services.job_guard import research_can_run

    factory, _ = database
    with factory() as db:
        research_job = JobRun(job_type="RESEARCH_EVAL", status="RUNNING", job_metadata={})
        db.add(research_job)
        db.commit()
        research_id = research_job.id
    enqueue(factory)
    with factory() as db:
        assert not research_can_run(db)
        assert research_can_run(db, running_only=True)
        assert claim_next_job(db, "writer") is None
        research.run_research_eval(db, db.get(JobRun, research_id))
        # It reaches identity validation, not a QUEUED deferral caused by waiting work.
        assert db.get(JobRun, research_id).status == "FAILED"
        assert "RESEARCH_IDENTITY_CHANGED" in db.get(JobRun, research_id).error_message


def test_dispatch_must_present_original_claim_not_adopt_current_token(database, monkeypatch):
    import app.services.job_worker as worker

    factory, _ = database
    key = enqueue(factory)
    with factory() as db:
        claim_next_job(db, "owner")
        monkeypatch.setattr(worker, "_provider", lambda db: pytest.fail("not the claimant"))
        execute_owned_job(db, key, expected_worker="old", expected_token=uuid4())
        assert db.get(JobRun, key).status == "RUNNING"


def test_unknown_and_private_paper_jobs_are_not_visible_to_generic_cancel(database):
    from fastapi import HTTPException

    factory, _ = database
    with factory() as db:
        paper = JobRun(job_type="PAPER_DAILY", status="QUEUED")
        db.add(paper)
        db.commit()
        for key in (uuid4(), paper.id):
            with pytest.raises(HTTPException) as error:
                cancel_job(key, db)
            assert error.value.status_code == 404
        assert data_queue(db)["data"]["queued"] == []


def test_real_validation_stops_between_days_preserving_completed_evidence(database, monkeypatch):
    from types import SimpleNamespace

    import app.services.job_worker as worker
    import app.services.quality.history_quality as quality
    from app.models.market_data import DataQualityDaily

    factory, _ = database
    day = date(2026, 9, 1)
    with factory() as db:
        key = create_queued_ingestion_job(
            db,
            "validate_data",
            day,
            step="queued",
            metadata={"start": day.isoformat(), "end": "2026-09-02"},
        ).id
        claim_next_job(db, "worker")
    calls = []

    def validate(self, current, **kwargs):
        calls.append(current)
        self.db.add(
            DataQualityDaily(
                trade_date=current,
                dataset="synthetic_validated",
                status="PASS",
                actual_rows=1,
                expected_rows=1,
                job_id=key,
            )
        )
        self.db.commit()
        with factory() as cancellation:
            cancel_job(key, cancellation)
        return SimpleNamespace(overall_status="PASS", as_metadata=lambda: {})

    monkeypatch.setattr(quality, "ensure_stock_basic_ready", lambda db: None)
    monkeypatch.setattr(
        quality.HistoricalDataQualityService,
        "_open_trade_dates",
        lambda *args: [day, date(2026, 9, 2)],
    )
    monkeypatch.setattr(quality.HistoricalDataQualityService, "validate_trade_date", validate)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    with factory() as db:
        execute_claimed_job(db, key)
    with factory() as db:
        assert db.get(JobRun, key).status == "CANCELLED"
        assert (
            db.scalar(select(DataQualityDaily.status).where(DataQualityDaily.job_id == key))
            == "PASS"
        )
    assert calls == [day]


def test_postgres_statement_timeout_cancels_and_requires_rollback(database, monkeypatch):
    from types import SimpleNamespace

    import app.core.db as core_db
    from sqlalchemy.exc import OperationalError

    factory, _ = database
    monkeypatch.setattr(
        core_db,
        "get_settings",
        lambda: SimpleNamespace(
            app_config={
                "app": {"scheduler": {"data_statement_timeout_ms": 20, "data_lock_timeout_ms": 10}},
            }
        ),
    )
    with factory() as db:
        db.info["data_task_timeouts"] = True
        with pytest.raises(OperationalError) as error:
            db.execute(text("SELECT pg_sleep(0.1)"))
        assert error.value.orig.sqlstate == "57014"
        db.rollback()
        assert db.scalar(text("SELECT 1")) == 1


def test_backfill_calendar_cancel_preserves_committed_calendar_not_next_dataset(
    database, monkeypatch
):
    import app.jobs.backfill_job as backfill
    import app.services.job_worker as worker
    import pandas as pd
    from app.models.market_data import TradeCalendar

    factory, _ = database
    key = enqueue(factory)
    with factory() as db:
        claim_next_job(db, "worker")
    calls = []

    class Provider:
        def get_trade_calendar(self, *args):
            calls.append("calendar")
            with factory() as cancellation:
                cancel_job(key, cancellation)
            return pd.DataFrame()

    monkeypatch.setattr(backfill, "ensure_stock_basic_ready", lambda db: None)
    monkeypatch.setattr(
        backfill,
        "normalize_trade_calendar",
        lambda frame: [
            {"cal_date": date(2026, 9, 1), "is_open": True, "exchange": "SSE"},
        ],
    )
    monkeypatch.setattr(backfill, "validate_trade_calendar_rows", lambda *args: None)
    monkeypatch.setattr(worker, "_provider", lambda db: Provider())
    monkeypatch.setattr(worker, "SessionLocal", factory)
    with factory() as db:
        execute_claimed_job(db, key)
    with factory() as db:
        assert db.get(JobRun, key).status == "CANCELLED"
        assert db.get(TradeCalendar, date(2026, 9, 1)).is_open is True
    assert calls == ["calendar"]


@pytest.mark.parametrize("status", ["RUNNING", "CANCELLED", "FAILED", "PARTIAL"])
def test_retained_staged_factors_are_not_falsely_published_ready(database, status):
    from app.api.v1.system import _counts_by_date
    from app.models.market_data import StockFactorDaily
    from app.services.quality.analysis_readiness import _count_matching

    factory, _ = database
    key = enqueue(factory)
    day = date(2026, 9, 1)
    with factory() as db:
        job = db.get(JobRun, key)
        job.execution_token, job.status = uuid4(), status
        db.add(
            StockFactorDaily(
                trade_date=day,
                ts_code="SYNTH.SZ",
                eligible=True,
                calc_run_id=key,
                calc_version="factor_v1",
                config_hash="a" * 64,
            )
        )
        db.commit()
        assert db.scalar(select(text("count(*)")).select_from(StockFactorDaily)) == 1
        assert _count_matching(db, StockFactorDaily, StockFactorDaily.trade_date == day) == 0
        assert _counts_by_date(db, StockFactorDaily.trade_date, day, day) == {}
        job.status = "SUCCESS"
        db.commit()
        assert _count_matching(db, StockFactorDaily, StockFactorDaily.trade_date == day) == 1


def test_queue_graph_cannot_be_rewritten_or_inserted_cyclically(database):
    from sqlalchemy.exc import IntegrityError

    factory, _ = database
    first = enqueue(factory)
    second = enqueue(factory, 2, depends_on_job_id=str(first))
    with factory() as db:
        with pytest.raises(IntegrityError, match="JOB_QUEUE_LINKS_IMMUTABLE"), db.begin_nested():
            db.get(JobRun, first).depends_on_job_id = second
            db.flush()
        a, b = uuid4(), uuid4()
        with (
            pytest.raises(IntegrityError, match="JOB_QUEUE_LINK_TARGET_INVALID"),
            db.begin_nested(),
        ):
            db.execute(
                JobRun.__table__.insert(),
                [
                    {"id": a, "job_type": "backfill", "status": "QUEUED", "depends_on_job_id": b},
                    {"id": b, "job_type": "backfill", "status": "QUEUED", "depends_on_job_id": a},
                ],
            )


def test_api_creation_reports_deduplication_and_real_queue_positions(database):
    from app.api.v1.jobs import BackfillJobRequest, enqueue_backfill_job

    factory, _ = database
    with factory() as db:
        payload = BackfillJobRequest(start="2026-09-01", end="2026-09-01")
        first = enqueue_backfill_job(payload, db)
        duplicate = enqueue_backfill_job(payload, db)
        second = enqueue_backfill_job(BackfillJobRequest(start="2026-09-02", end="2026-09-02"), db)
        assert first["meta"] == {"accepted": True, "deduplicated": False, "queue_position": 1}
        assert duplicate["data"]["id"] == first["data"]["id"]
        assert duplicate["meta"] == {"accepted": False, "deduplicated": True, "queue_position": 1}
        assert second["meta"]["accepted"] and second["meta"]["queue_position"] == 2


def test_enqueue_timestamp_is_not_an_old_transaction_start(database):
    factory, _ = database
    with factory() as db:
        transaction_start = db.scalar(text("SELECT now()"))
        db.execute(text("SELECT pg_sleep(0.01)"))
        job = create_queued_ingestion_job(
            db,
            "backfill",
            date(2026, 9, 1),
            step="queued",
            metadata={"start": "2026-09-01", "end": "2026-09-01"},
        )
        assert job.started_at > transaction_start


def test_postgresql_plan_uses_fifo_status_time_id_index(database, record_property):
    import json

    factory, _ = database
    with factory() as db:
        db.execute(
            JobRun.__table__.insert(),
            [
                {
                    "id": uuid4(),
                    "job_type": "backfill",
                    "status": "QUEUED",
                    "started_at": datetime(2026, 9, 1, tzinfo=UTC),
                }
                for _ in range(1000)
            ],
        )
        db.commit()
        db.execute(text("ANALYZE job_run"))
        plan = db.scalar(
            text(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                "SELECT id FROM job_run WHERE status='QUEUED' AND parent_job_id IS NULL "
                "ORDER BY started_at, id LIMIT 1"
            )
        )
        assert "idx_job_data_queue" in json.dumps(plan)
        record_property("synthetic_fifo_plan", json.dumps(plan))


def test_unknown_disconnect_holds_execution_slot_instead_of_releasing_writer(database, monkeypatch):
    import app.services.job_worker as worker
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError

    factory, _ = database
    day = date(2026, 9, 1)
    with factory() as db:
        key = create_queued_ingestion_job(
            db,
            "validate_data",
            day,
            step="queued",
            metadata={"start": day.isoformat(), "end": day.isoformat()},
        ).id
        claim_next_job(db, "worker")
    following = enqueue(factory, 2)

    def disconnect(db, *args):
        db.connection().invalidate()
        raise OperationalError(
            "synthetic interrupted SQL", {}, OSError("disconnected"), connection_invalidated=True
        )

    monkeypatch.setattr(worker, "run_validate_data_job", disconnect)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    with factory() as db:
        execute_claimed_job(db, key)
    with factory() as db:
        current = db.get(JobRun, key)
        assert current.status == "RUNNING"
        assert current.job_metadata["execution_unconfirmed"] is True
        assert "OperationalError/OSError" in current.error_message
        assert claim_next_job(db, "other") is None
        assert db.get(JobRun, following).status == "QUEUED"
        with pytest.raises(HTTPException) as error:
            cancel_job(key, db)
        assert error.value.detail["code"] == "JOB_EXECUTION_UNCONFIRMED"


def test_acknowledged_postgresql_timeout_can_finish_and_release_lane(database, monkeypatch):
    import app.services.job_worker as worker

    factory, _ = database
    day = date(2026, 9, 1)
    with factory() as db:
        key = create_queued_ingestion_job(
            db,
            "validate_data",
            day,
            step="queued",
            metadata={"start": day.isoformat(), "end": day.isoformat()},
        ).id
        claim_next_job(db, "worker")
    following = enqueue(factory, 2)

    def timeout(db, *args):
        db.execute(text("SET LOCAL statement_timeout = '20ms'"))
        db.execute(text("SELECT pg_sleep(0.1)"))

    monkeypatch.setattr(worker, "run_validate_data_job", timeout)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    with factory() as db:
        execute_claimed_job(db, key)
    with factory() as db:
        current = db.get(JobRun, key)
        assert current.status == "FAILED"
        assert "SQLSTATE 57014" in current.error_message
        assert claim_next_job(db, "other") == following


def test_legacy_running_without_claim_identity_requires_manual_reconciliation(database):
    from app.api.v1.jobs import _job_payload
    from app.models.market_data import StockFactorDaily
    from app.services.quality.analysis_readiness import _count_matching
    from fastapi import HTTPException

    factory, _ = database
    with factory() as db:
        job = JobRun(job_type="backfill", status="RUNNING", job_metadata={})
        db.add(job)
        db.commit()
        payload = _job_payload(job)
        assert payload["execution_unconfirmed"] and not payload["can_cancel"]
        with pytest.raises(HTTPException) as error:
            cancel_job(job.id, db)
        assert error.value.detail["code"] == "JOB_EXECUTION_UNCONFIRMED"
        db.add(
            StockFactorDaily(
                trade_date=date(2026, 9, 1), ts_code="LEGACY.SZ", eligible=True, calc_run_id=job.id
            )
        )
        db.commit()
        assert _count_matching(db, StockFactorDaily) == 0
        job.status = "SUCCESS"
        db.commit()
        assert _count_matching(db, StockFactorDaily) == 1
