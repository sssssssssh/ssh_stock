from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.repositories.job_run import start_job

INGESTION_JOB_TYPES = (
    "daily",
    "sync_basic",
    "backfill",
    "recalculate",
    "validate_data",
    "catchup",
)
ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING")
INGESTION_ADVISORY_LOCK_KEY = 7_307_202_609_15


@dataclass(frozen=True)
class ActiveIngestionJobError(RuntimeError):
    job_id: str
    job_type: str
    status: str

    def __str__(self) -> str:
        return f"active ingestion job exists: {self.job_id} ({self.job_type} {self.status})"


def scheduler_setting(name: str, default: Any) -> Any:
    scheduler = get_settings().app_config.get("app", {}).get("scheduler", {})
    if not isinstance(scheduler, dict):
        return default
    return scheduler.get(name, default)


def active_ingestion_jobs(db: Session) -> list[JobRun]:
    return list(
        db.execute(
            select(JobRun)
            .where(
                JobRun.job_type.in_(INGESTION_JOB_TYPES),
                JobRun.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(JobRun.started_at)
        )
        .scalars()
        .all()
    )


def recover_stale_ingestion_jobs(
    db: Session,
    *,
    stale_job_hours: float | None = None,
    now: datetime | None = None,
) -> int:
    hours = float(stale_job_hours or scheduler_setting("stale_job_hours", 24))
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    cutoff = current - timedelta(hours=hours)
    recovered = 0
    for job in active_ingestion_jobs(db):
        started_at = (
            getattr(job, "heartbeat_at", None)
            if job.status == "RUNNING"
            else job.started_at
        ) or job.started_at
        if started_at is None:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        if started_at > cutoff:
            continue
        job.status = "FAILED"
        job.finished_at = current
        job.error_message = "stale job recovered after process restart"
        db.add(job)
        recovered += 1
    if recovered:
        db.commit()
    return recovered


def find_active_ingestion_job(
    db: Session,
    *,
    recover_stale: bool = True,
) -> JobRun | None:
    if recover_stale:
        recover_stale_ingestion_jobs(db)
    jobs = active_ingestion_jobs(db)
    return jobs[0] if jobs else None


def reject_if_active_ingestion_job(db: Session) -> None:
    active = find_active_ingestion_job(db)
    if active:
        raise ActiveIngestionJobError(
            job_id=str(active.id),
            job_type=active.job_type,
            status=active.status,
        )


def create_queued_ingestion_job(
    db: Session,
    job_type: str,
    target_trade_date: date | None,
    *,
    step: str,
    metadata: dict[str, Any],
) -> JobRun:
    recover_stale_ingestion_jobs(db)
    _acquire_ingestion_advisory_lock(db)
    active = find_active_ingestion_job(db, recover_stale=False)
    if active:
        raise ActiveIngestionJobError(
            job_id=str(active.id),
            job_type=active.job_type,
            status=active.status,
        )
    return start_job(
        db,
        job_type,
        target_trade_date,
        status="QUEUED",
        step=step,
        metadata=metadata,
    )


def _acquire_ingestion_advisory_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        select(func.pg_advisory_xact_lock(INGESTION_ADVISORY_LOCK_KEY))
    ).scalar_one()
