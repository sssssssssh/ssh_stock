"""Durable schedule intentions, not a second execution queue. All work enters JobRun."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from functools import wraps

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.clock import business_today
from app.models.data_schedule import DataScheduleIntent
from app.models.job import JobRun
from app.services.job_guard import (
    INGESTION_JOB_TYPES,
    QueueCapacityError,
    create_queued_ingestion_job,
    data_queue_identity,
    scheduler_setting,
)


def intent_key(kind, day):
    identity = data_queue_identity()
    return hashlib.sha256(
        json.dumps([kind, day.isoformat(), identity], sort_keys=True).encode()
    ).hexdigest()


def _due(value, now):
    return (value if value.tzinfo else value.replace(tzinfo=UTC)) <= now


def safe_schedule(kind):
    def decorate(method):
        @wraps(method)
        def guarded(db, *args, **kwargs):
            try:
                return method(db, *args, **kwargs)
            except SQLAlchemyError:
                db.rollback()
                day = kwargs.get("target_date") or (args[-1] if args else business_today())
                if not hasattr(day, "isoformat"):
                    day = business_today()
                metadata = {"schedule_date": day.isoformat()}
                record_schedule_deferral(db, kind, day, "SCHEDULER_DATABASE_UNAVAILABLE", metadata)
                return False

        return guarded

    return decorate


def enqueue_scheduled_data(db, kind, target, *, step, metadata, enqueue=None, now=None):
    now = now or datetime.now(UTC)
    day = target if target is not None else datetime.fromisoformat(metadata["schedule_date"]).date()
    key = intent_key(kind, day)
    retry_at = now + timedelta(seconds=int(scheduler_setting("schedule_retry_seconds", 300)))
    try:
        # A unique intention serializes scheduler replicas. Enqueue commits it
        # together with JobRun; a crash before acknowledgement is safe to dedup.
        statement = insert(DataScheduleIntent).values(
            identity_key=key,
            kind=kind,
            target_date=day,
            identity=data_queue_identity(),
            state="DEFERRED",
            attempts=0,
            next_attempt_at=now,
            updated_at=now,
        )
        db.execute(statement.on_conflict_do_nothing())
        event = db.scalar(
            select(DataScheduleIntent)
            .where(DataScheduleIntent.identity_key == key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if event.state in {"CANCELLED", "NEEDS_MANUAL", "IDENTITY_CHANGED"}:
            db.commit()
            return None
        existing = db.get(JobRun, event.job_id) if event.job_id else None
        if kind == "sync_basic" and existing and existing.status == "SUCCESS":
            event.state, event.error_code = "COMPLETE", None
            db.commit()
            existing._queue_deduplicated = True
            return existing
        if existing and existing.status in {"QUEUED", "RUNNING"}:
            db.commit()
            existing._queue_deduplicated = True
            return existing
        if existing and existing.status == "CANCELLED":
            event.state, event.error_code = "CANCELLED", "SCHEDULER_PLAN_CANCELLED"
            db.commit()
            return None
        if event.state in {"DEFERRED", "ENQUEUED"} and not _due(event.next_attempt_at, now):
            db.commit()
            return None
        if event.attempts >= int(scheduler_setting("schedule_max_attempts", 12)):
            event.state, event.error_code = "NEEDS_MANUAL", "SCHEDULER_RETRY_LIMIT"
            db.commit()
            return None

        def link(queued):
            # Persist the plan/Job link in the enqueue's transaction, including
            # dedup. A lost COMMIT response must not lose a cancellation identity.
            intention = db.get(DataScheduleIntent, key)
            if intention is None:  # Guard's unique-conflict rollback path.
                intention = DataScheduleIntent(
                    identity_key=key,
                    kind=kind,
                    target_date=day,
                    identity=data_queue_identity(),
                    attempts=0,
                )
            intention.state, intention.job_id = "ENQUEUED", queued.id
            intention.attempts = int(intention.attempts or 0) + 1
            intention.error_code, intention.queue_count = None, None
            intention.next_attempt_at, intention.updated_at = retry_at, now
            db.add(intention)

        job = (enqueue or create_queued_ingestion_job)(
            db, kind, target, step=step, metadata=metadata, _before_commit=link
        )
        return job
    except (QueueCapacityError, SQLAlchemyError) as error:
        db.rollback()
        code = (
            "QUEUE_CAPACITY_EXCEEDED"
            if isinstance(error, QueueCapacityError)
            else "SCHEDULER_DATABASE_UNAVAILABLE"
        )
        record_schedule_deferral(db, kind, day, code, metadata, now=now)
        return None


_unpersisted_log_at = {}


def record_schedule_deferral(db, kind, day, code, metadata, *, now=None):
    now = now or datetime.now(UTC)
    key = intent_key(kind, day)
    retry_at = now + timedelta(seconds=int(scheduler_setting("schedule_retry_seconds", 300)))
    try:
        old = db.get(DataScheduleIntent, key)
        changed = old is None or old.error_code != code
        count = db.scalar(
            select(func.count())
            .select_from(JobRun)
            .where(
                JobRun.job_type.in_(INGESTION_JOB_TYPES),
                JobRun.status == "QUEUED",
                JobRun.parent_job_id.is_(None),
            )
        )
        stmt = insert(DataScheduleIntent).values(
            identity_key=key,
            kind=kind,
            target_date=day,
            identity=data_queue_identity(),
            state="DEFERRED",
            attempts=1,
            error_code=code,
            queue_count=count,
            next_attempt_at=retry_at,
            updated_at=now,
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["identity_key"],
                set_={
                    "state": "DEFERRED",
                    "error_code": code,
                    "queue_count": count,
                    "attempts": DataScheduleIntent.attempts + 1,
                    "next_attempt_at": retry_at,
                    "updated_at": now,
                },
                where=DataScheduleIntent.state.in_(("DEFERRED", "ENQUEUED")),
            )
        )
        db.commit()
        if changed:
            logger.warning(
                "scheduler deferred code={} kind={} target={} queued={} retry_at={}",
                code,
                kind,
                day,
                count,
                retry_at.isoformat(),
            )
    except SQLAlchemyError:
        db.rollback()
        # Rate limiting diagnostics is not a parallel execution queue. Actual
        # intentions stay in PostgreSQL; we explicitly report failed persistence.
        previous = _unpersisted_log_at.get(key)
        if previous is None or (now - previous).total_seconds() >= 300:
            _unpersisted_log_at[key] = now
            logger.error(
                "scheduler intent UNPERSISTED code={} kind={} target={}; "
                "startup/readiness compensation required",
                code,
                kind,
                day,
            )


def mark_schedule_complete(db, kind, day):
    event = db.get(DataScheduleIntent, intent_key(kind, day))
    if event:
        event.state, event.error_code, event.updated_at = "COMPLETE", None, datetime.now(UTC)
        db.commit()


@safe_schedule("catchup")
def retry_schedule_intents(db, *, now=None):
    now = now or datetime.now(UTC)
    keys = list(
        db.scalars(
            select(DataScheduleIntent.identity_key)
            .where(
                DataScheduleIntent.state.in_(("DEFERRED", "ENQUEUED")),
                DataScheduleIntent.next_attempt_at <= now,
            )
            .order_by(DataScheduleIntent.target_date, DataScheduleIntent.created_at)
            .limit(100)
        )
    )
    from app.jobs.scheduler import run_scheduled_catchup, scheduled_output_ready

    attempted = 0
    for key in keys:
        event = db.get(DataScheduleIntent, key)
        if event.identity != data_queue_identity():
            event.state, event.error_code = "IDENTITY_CHANGED", "JOB_CONFIG_CHANGED"
            db.commit()
            continue
        job = db.get(JobRun, event.job_id) if event.job_id else None
        if job and job.status in {"QUEUED", "RUNNING"}:
            event.next_attempt_at = now + timedelta(seconds=300)
            db.commit()
            continue
        if job and job.status == "CANCELLED":
            event.state, event.error_code = "CANCELLED", "SCHEDULER_PLAN_CANCELLED"
            db.commit()
            continue
        if job and job.status == "SUCCESS":
            meta = dict(job.job_metadata or {})
            if meta.get("skipped"):
                event.state, event.error_code = (
                    "NEEDS_MANUAL",
                    "CATCHUP_WINDOW_REQUIRES_MANUAL_REPAIR",
                )
                db.commit()
                continue
            if (
                event.kind == "sync_basic"
                or meta.get("stage") != "eod_deferred"
                and scheduled_output_ready(db, event.target_date)
            ):
                event.state, event.error_code = "COMPLETE", None
                db.commit()
                continue
        target = event.target_date if event.kind == "catchup" else None
        metadata = (
            {"source": "scheduler", "trade_date": event.target_date.isoformat()}
            if target
            else {
                "source": "scheduler",
                "schedule_date": event.target_date.isoformat(),
                "stage": "queued",
            }
        )
        if event.kind == "catchup":
            accepted = run_scheduled_catchup(db, None, target, now=now)
        else:
            accepted = (
                enqueue_scheduled_data(
                    db,
                    event.kind,
                    target,
                    step="queued from schedule compensation",
                    metadata=metadata,
                    now=now,
                )
                is not None
            )
        if accepted:
            attempted += 1
    return attempted


def schedule_alerts(db):
    rows = list(
        db.scalars(
            select(DataScheduleIntent)
            .where(DataScheduleIntent.state.in_(("DEFERRED", "NEEDS_MANUAL", "IDENTITY_CHANGED")))
            .order_by(DataScheduleIntent.target_date, DataScheduleIntent.identity_key)
            .limit(21)
        )
    )
    return {
        "pending_count": db.scalar(
            select(func.count())
            .select_from(DataScheduleIntent)
            .where(DataScheduleIntent.state.in_(("DEFERRED", "NEEDS_MANUAL", "IDENTITY_CHANGED")))
        ),
        "items": [
            {
                "kind": row.kind,
                "target_date": row.target_date.isoformat(),
                "state": row.state,
                "error_code": row.error_code,
                "next_attempt_at": row.next_attempt_at.isoformat(),
            }
            for row in rows[:20]
        ],
        "truncated": len(rows) > 20,
    }
