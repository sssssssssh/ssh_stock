import inspect
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import app.api.v1.jobs as jobs_api
import app.services.job_guard as guard_module
import app.services.job_worker as worker_module
from app.repositories.job_run import update_job
from app.services.dirty import recover_stale_processing_ranges
from app.services.job_worker import claim_next_job, execute_claimed_job
from sqlalchemy.dialects import postgresql


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value


def test_worker_claim_uses_skip_locked_and_sets_heartbeat() -> None:
    job = SimpleNamespace(
        id=uuid4(),
        status="QUEUED",
        worker_id=None,
        heartbeat_at=None,
        step=None,
    )

    class FakeDb:
        def __init__(self):
            self.statement = None
            self.commits = 0

        def execute(self, statement):
            self.statement = statement
            return _ScalarResult(job)

        def add(self, row):
            return None

        def commit(self):
            self.commits += 1

    db = FakeDb()

    claimed = claim_next_job(db, "worker-a")

    sql = str(db.statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert claimed == job.id
    assert job.status == "RUNNING"
    assert job.worker_id == "worker-a"
    assert job.heartbeat_at is not None
    assert db.commits == 1


def test_atomic_job_guard_uses_postgresql_advisory_lock() -> None:
    class FakeResult:
        def scalar_one(self):
            return None

    class FakeDb:
        def __init__(self):
            self.statement = None

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement):
            self.statement = statement
            return FakeResult()

    db = FakeDb()

    guard_module._acquire_ingestion_advisory_lock(db)

    sql = str(db.statement.compile(dialect=postgresql.dialect()))
    assert "pg_advisory_xact_lock" in sql


def test_worker_recalculation_does_not_construct_provider(monkeypatch) -> None:
    job_id = uuid4()
    job = SimpleNamespace(
        id=job_id,
        job_type="recalculate",
        status="RUNNING",
        job_metadata={
            "start": "2026-09-01",
            "end": "2026-09-15",
            "evaluate_signals": False,
            "mode": "manual",
        },
    )
    calls = []

    class FakeDb:
        def get(self, model, key):
            return job

        def rollback(self):
            return None

    monkeypatch.setattr(
        worker_module,
        "TushareProvider",
        lambda: (_ for _ in ()).throw(AssertionError("provider must stay lazy")),
    )
    monkeypatch.setattr(worker_module, "_load_dirty_ranges", lambda *args: [])
    monkeypatch.setattr(
        worker_module,
        "run_recalculation",
        lambda db, current, start, end, **kwargs: calls.append((start, end, kwargs)),
    )

    execute_claimed_job(FakeDb(), job_id)

    assert calls[0][0:2] == (date(2026, 9, 1), date(2026, 9, 15))
    assert calls[0][2]["evaluate_signals"] is False


def test_stale_dirty_processing_is_recovered_for_retry(monkeypatch) -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    row = SimpleNamespace(
        status="PROCESSING",
        retry_count=1,
        last_error=None,
        last_failed_at=None,
        processing_started_at=now - timedelta(hours=25),
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [row]

    class FakeDb:
        def __init__(self):
            self.commits = 0

        def execute(self, statement):
            return FakeResult()

        def add(self, value):
            return None

        def commit(self):
            self.commits += 1

    db = FakeDb()

    recovered = recover_stale_processing_ranges(db, stale_hours=24, now=now)

    assert recovered == 1
    assert row.status == "FAILED"
    assert row.retry_count == 2
    assert row.last_error == "stale processing recovered"
    assert row.processing_started_at is None
    assert db.commits == 1


def test_api_enqueue_handlers_no_longer_accept_background_tasks() -> None:
    handlers = [
        jobs_api.enqueue_daily_job,
        jobs_api.enqueue_sync_basic_job,
        jobs_api.enqueue_backfill_job,
        jobs_api.enqueue_recalculate_job,
        jobs_api.enqueue_validate_data_job,
    ]

    assert all(
        "background_tasks" not in inspect.signature(handler).parameters
        for handler in handlers
    )


def test_update_job_refreshes_running_heartbeat() -> None:
    job = SimpleNamespace(
        status="QUEUED",
        finished_at=None,
        heartbeat_at=None,
        step=None,
        row_count=0,
        error_message=None,
        job_metadata={},
    )

    class FakeDb:
        def add(self, row):
            return None

        def commit(self):
            return None

        def refresh(self, row):
            return None

    update_job(FakeDb(), job, status="RUNNING", step="working")

    assert job.heartbeat_at is not None
