"""Durable schedule evidence using a uniquely owned PostgreSQL 17 database."""

from datetime import UTC, date, datetime, timedelta

import pytest
from app.models.data_schedule import DataScheduleIntent
from app.models.job import JobRun
from app.services.data_schedule import (
    enqueue_scheduled_data,
    intent_key,
    record_schedule_deferral,
    retry_schedule_intents,
    schedule_alerts,
)
from app.services.job_guard import QueueCapacityError, create_queued_ingestion_job
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.integration.m16_6_support import isolated_contract_database

DAY = date(2026, 10, 17)  # Saturday: compensation is not restricted to trading days.
NOW = datetime(2026, 10, 18, tzinfo=UTC)


@pytest.fixture
def schedule_db(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, _):
        with factory() as db:
            yield db


def enqueue(db, *, method=None, now=NOW, kind="sync_basic", day=DAY):
    return enqueue_scheduled_data(
        db,
        kind,
        None if kind == "sync_basic" else day,
        step="schedule test",
        metadata={"schedule_date": day.isoformat(), "source": "scheduler"},
        enqueue=method,
        now=now,
    )


@pytest.mark.parametrize(
    "failure,code",
    [
        (QueueCapacityError("QUEUE_CAPACITY_EXCEEDED"), "QUEUE_CAPACITY_EXCEEDED"),
        (
            OperationalError("private SQL must not be logged", {}, Exception("private")),
            "SCHEDULER_DATABASE_UNAVAILABLE",
        ),
    ],
)
def test_capacity_and_outage_persist_deferred_then_retry_without_storm(schedule_db, failure, code):
    db = schedule_db
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise failure

    assert enqueue(db, method=fail) is None
    key = intent_key("sync_basic", DAY)
    event = db.get(DataScheduleIntent, key)
    assert event.state == "DEFERRED" and event.error_code == code
    assert event.attempts == 1 and event.queue_count == 0
    assert schedule_alerts(db)["pending_count"] == 1
    for _ in range(5):
        assert enqueue(db, method=fail, now=NOW + timedelta(seconds=1)) is None
    assert calls == [1]
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=301)) == 1
    event = db.get(DataScheduleIntent, key)
    assert event.state == "ENQUEUED"
    job = db.get(JobRun, event.job_id)
    assert job.status == "QUEUED" and job.job_type == "sync_basic"
    assert job.job_metadata["schedule_date"] == DAY.isoformat()
    assert enqueue(db, now=NOW + timedelta(seconds=302)).id == job.id
    assert db.scalar(select(func.count()).select_from(JobRun)) == 1


def test_cancelled_schedule_is_not_replayed_even_if_later_error_is_recorded(schedule_db):
    db = schedule_db
    job = enqueue(db)
    job.status = "CANCELLED"
    db.commit()
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=301)) == 0
    record_schedule_deferral(db, "sync_basic", DAY, "SCHEDULER_DATABASE_UNAVAILABLE", {}, now=NOW)
    assert db.get(DataScheduleIntent, intent_key("sync_basic", DAY)).state == "CANCELLED"
    assert enqueue(db, now=NOW + timedelta(days=1)) is None
    assert db.scalar(select(func.count()).select_from(JobRun)) == 1


def test_enqueue_commit_response_loss_still_links_cancelled_plan(schedule_db, monkeypatch):
    db = schedule_db
    original = Session.commit
    lost = []

    def commit(session):
        original(session)
        if not lost:
            lost.append(True)
            raise OperationalError(
                "synthetic", {}, OSError("commit response lost"), connection_invalidated=True
            )

    monkeypatch.setattr(Session, "commit", commit)
    assert enqueue(db) is None
    job = db.scalar(select(JobRun))
    assert job is not None
    event = db.get(DataScheduleIntent, intent_key("sync_basic", DAY))
    assert event.job_id == job.id
    job.status = "CANCELLED"
    db.commit()
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=301)) == 0
    assert db.scalar(select(func.count()).select_from(JobRun)) == 1


def test_identity_change_requires_manual_review_and_keeps_fifo(schedule_db):
    db = schedule_db
    manual = create_queued_ingestion_job(db, "backfill", DAY, step="manual", metadata={})
    scheduled = enqueue(db)
    assert scheduled.started_at >= manual.started_at
    event = db.get(DataScheduleIntent, intent_key("sync_basic", DAY))
    event.identity = {"analysis": "old-config"}
    db.commit()
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=301)) == 0
    assert db.get(DataScheduleIntent, event.identity_key).state == "IDENTITY_CHANGED"
    assert schedule_alerts(db)["items"][0]["error_code"] == "JOB_CONFIG_CHANGED"
    assert db.scalar(select(func.count()).select_from(JobRun)) == 2


def test_real_capacity_guard_defers_scheduler_without_overtaking_manual_job(
    schedule_db, monkeypatch
):
    from app.services import job_guard

    original = job_guard.scheduler_setting
    monkeypatch.setattr(
        job_guard,
        "scheduler_setting",
        lambda name, default: 1 if name == "data_queue_capacity" else original(name, default),
    )
    db = schedule_db
    manual = create_queued_ingestion_job(db, "backfill", DAY, step="manual", metadata={})
    assert enqueue(db) is None
    assert db.scalar(select(func.count()).select_from(JobRun)) == 1
    event = db.get(DataScheduleIntent, intent_key("sync_basic", DAY))
    assert event.error_code == "QUEUE_CAPACITY_EXCEEDED" and event.queue_count == 1
    manual.status = "CANCELLED"
    db.commit()
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=301)) == 1
    scheduled = db.get(JobRun, event.job_id)
    assert scheduled.status == "QUEUED" and scheduled.started_at > manual.started_at


def test_retry_exhaustion_is_visible_and_requires_manual_action(schedule_db, monkeypatch):
    from app.services import data_schedule

    original = data_schedule.scheduler_setting
    monkeypatch.setattr(
        data_schedule,
        "scheduler_setting",
        lambda name, default: 1 if name == "schedule_max_attempts" else original(name, default),
    )

    def full(*args, **kwargs):
        raise QueueCapacityError("QUEUE_CAPACITY_EXCEEDED")

    assert enqueue(schedule_db, method=full) is None
    assert enqueue(schedule_db, now=NOW + timedelta(seconds=301)) is None
    event = schedule_db.get(DataScheduleIntent, intent_key("sync_basic", DAY))
    assert event.state == "NEEDS_MANUAL" and event.error_code == "SCHEDULER_RETRY_LIMIT"
    assert schedule_alerts(schedule_db)["pending_count"] == 1
    assert schedule_db.scalar(select(func.count()).select_from(JobRun)) == 0


def test_skipped_catchup_cannot_become_complete_just_because_latest_day_is_ready(
    schedule_db, monkeypatch
):
    from app.jobs.scheduler import run_scheduled_catchup

    db = schedule_db
    job = enqueue(db, kind="catchup")
    job.status = "SUCCESS"
    job.job_metadata = {**job.job_metadata, "stage": "success", "skipped": True}
    db.commit()
    monkeypatch.setattr("app.jobs.scheduler.scheduled_output_ready", lambda *_: True)
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=301)) == 0
    key = intent_key("catchup", DAY)
    assert db.get(DataScheduleIntent, key).state == "NEEDS_MANUAL"
    assert run_scheduled_catchup(db, None, DAY, now=NOW + timedelta(seconds=602)) is False
    assert db.get(DataScheduleIntent, key).state == "NEEDS_MANUAL"


def test_deferred_success_is_not_completed_but_genuine_success_is(schedule_db, monkeypatch):
    db = schedule_db
    job = enqueue(db, kind="catchup")
    job.status = "SUCCESS"
    job.job_metadata = {**job.job_metadata, "stage": "eod_deferred"}
    db.commit()
    monkeypatch.setattr("app.jobs.scheduler.scheduled_output_ready", lambda *_: True)
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=301)) == 1
    event = db.get(DataScheduleIntent, intent_key("catchup", DAY))
    assert event.state == "ENQUEUED" and event.job_id != job.id
    retry = db.get(JobRun, event.job_id)
    retry.status = "SUCCESS"
    retry.job_metadata = {**retry.job_metadata, "stage": "complete"}
    db.commit()
    assert retry_schedule_intents(db, now=NOW + timedelta(seconds=602)) == 0
    assert db.get(DataScheduleIntent, event.identity_key).state == "COMPLETE"
