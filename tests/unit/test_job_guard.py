from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.services.job_guard import (
    ActiveIngestionJobError,
    find_active_ingestion_job,
    recover_stale_ingestion_jobs,
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
    job = _job("RUNNING", now - timedelta(hours=1))
    db = _FakeDb([job])

    with pytest.raises(ActiveIngestionJobError):
        reject_if_active_ingestion_job(db)


def test_recover_stale_running_and_queued_jobs() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    stale_running = _job("RUNNING", now - timedelta(hours=25))
    stale_queued = _job("QUEUED", now - timedelta(hours=26))
    fresh = _job("RUNNING", now - timedelta(hours=1))
    db = _FakeDb([stale_running, stale_queued, fresh])

    recovered = recover_stale_ingestion_jobs(db, stale_job_hours=24, now=now)

    assert recovered == 2
    assert stale_running.status == "FAILED"
    assert stale_queued.status == "FAILED"
    assert stale_running.finished_at == now
    assert stale_queued.error_message == "stale job recovered after process restart"
    assert fresh.status == "RUNNING"
    assert db.commits == 1


def test_find_active_job_ignores_recovered_stale_jobs() -> None:
    now = datetime.now(UTC)
    stale = _job("RUNNING", now - timedelta(hours=25))
    db = _FakeDb([stale])

    active = find_active_ingestion_job(db)

    assert active is None
    assert stale.status == "FAILED"
