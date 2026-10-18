from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.services.job_guard import (
    ActiveIngestionJobError,
    find_active_ingestion_job,
    recover_stale_ingestion_jobs,
    recover_stale_research_jobs,
    reject_if_active_ingestion_job,
)


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0

    def execute(self, _stmt):
        active = [row for row in self.rows if row.status in {"QUEUED", "RUNNING"}]
        sql = str(_stmt.compile(compile_kwargs={"literal_binds": True}))
        if "RESEARCH_EVAL" in sql:
            active = [row for row in active if row.job_type == "RESEARCH_EVAL"]
        else:
            active = [row for row in active if row.job_type != "RESEARCH_EVAL"]
        return _FakeResult(active)

    def add(self, _row):
        return None

    def commit(self):
        self.commits += 1


def _job(status: str, started_at: datetime):
    return SimpleNamespace(
        id=uuid4(),
        job_type="backfill",
        status=status,
        started_at=started_at,
        finished_at=None,
        error_message=None,
    )


def test_reject_if_active_ingestion_job_raises_for_running_job() -> None:
    now = datetime.now(UTC)
    job = _job("RUNNING", now - timedelta(minutes=5))
    db = _FakeDb([job])

    with pytest.raises(ActiveIngestionJobError):
        reject_if_active_ingestion_job(db)


def test_unconfirmed_running_and_legitimate_queue_never_expire() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    stale_running = _job("RUNNING", now - timedelta(hours=25))
    stale_queued = _job("QUEUED", now - timedelta(hours=26))
    fresh = _job("RUNNING", now - timedelta(hours=1))
    db = _FakeDb([stale_running, stale_queued, fresh])

    recovered = recover_stale_ingestion_jobs(db, stale_job_hours=24, now=now)

    assert recovered == 0
    assert stale_running.status == "RUNNING"
    assert stale_queued.status == "QUEUED"
    assert stale_running.finished_at is None
    assert stale_queued.error_message is None
    assert fresh.status == "RUNNING"
    assert db.commits == 0


def test_unconfirmed_old_writer_still_blocks_lane() -> None:
    now = datetime.now(UTC)
    stale = _job("RUNNING", now - timedelta(hours=25))
    db = _FakeDb([stale])

    active = find_active_ingestion_job(db)

    assert active is stale
    assert stale.status == "RUNNING"


def test_research_stale_recovery_keeps_fresh_running() -> None:
    now = datetime(2026, 9, 22, tzinfo=UTC)
    stale_running = _job("RUNNING", now - timedelta(hours=2))
    stale_running.job_type = "RESEARCH_EVAL"
    stale_running.heartbeat_at = now - timedelta(minutes=30)
    stale_queued = _job("QUEUED", now - timedelta(hours=25))
    stale_queued.job_type = "RESEARCH_EVAL"
    fresh = _job("RUNNING", now - timedelta(hours=1))
    fresh.job_type = "RESEARCH_EVAL"
    fresh.heartbeat_at = now - timedelta(minutes=2)
    db = _FakeDb([stale_running, stale_queued, fresh])

    assert recover_stale_research_jobs(db, now=now) == 1
    assert stale_running.status == "RUNNING"
    assert stale_queued.status == "FAILED"
    assert fresh.status == "RUNNING"
