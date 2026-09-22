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
RESEARCH_JOB_TYPE = "RESEARCH_EVAL"
PRODUCTION_MUTATING_JOB_TYPES = ("daily", "sync_basic", "backfill", "recalculate", "catchup")
INGESTION_ADVISORY_LOCK_KEY = 7_307_202_609_15
RESEARCH_ADVISORY_LOCK_KEY = 7_307_202_609_19


class ResearchQueueConflictError(RuntimeError):
    pass


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
    queued_stale_hours: float | None = None,
    running_heartbeat_timeout_minutes: float | None = None,
    now: datetime | None = None,
) -> int:
    return _recover_stale_jobs(
        db,
        active_ingestion_jobs(db),
        stale_job_hours=stale_job_hours,
        queued_stale_hours=queued_stale_hours,
        running_heartbeat_timeout_minutes=running_heartbeat_timeout_minutes,
        now=now,
    )


def recover_stale_research_jobs(
    db: Session,
    *,
    queued_stale_hours: float | None = None,
    running_heartbeat_timeout_minutes: float | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> int:
    jobs = db.execute(
        select(JobRun).where(
            JobRun.job_type == RESEARCH_JOB_TYPE,
            JobRun.status.in_(ACTIVE_JOB_STATUSES),
        )
    ).scalars().all()
    return _recover_stale_jobs(
        db,
        jobs,
        queued_stale_hours=queued_stale_hours,
        running_heartbeat_timeout_minutes=running_heartbeat_timeout_minutes,
        now=now,
        commit=commit,
    )


def _recover_stale_jobs(
    db: Session,
    jobs: list[JobRun],
    *,
    stale_job_hours: float | None = None,
    queued_stale_hours: float | None = None,
    running_heartbeat_timeout_minutes: float | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> int:
    queued_hours = float(
        queued_stale_hours
        or stale_job_hours
        or scheduler_setting("queued_stale_hours", 24)
    )
    running_minutes = float(
        running_heartbeat_timeout_minutes
        or (stale_job_hours * 60 if stale_job_hours is not None else 0)
        or scheduler_setting("running_heartbeat_timeout_minutes", 15)
    )
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    recovered = 0
    for job in jobs:
        original_status = job.status
        reference_at = (
            (getattr(job, "heartbeat_at", None) or job.started_at)
            if job.status == "RUNNING"
            else job.started_at
        )
        if reference_at is None:
            continue
        if reference_at.tzinfo is None:
            reference_at = reference_at.replace(tzinfo=UTC)
        timeout = (
            timedelta(minutes=running_minutes)
            if job.status == "RUNNING"
            else timedelta(hours=queued_hours)
        )
        if reference_at > current - timeout:
            continue
        job.status = "FAILED"
        job.finished_at = current
        job.error_message = (
            "stale RUNNING job recovered after heartbeat timeout"
            if original_status == "RUNNING"
            else "stale QUEUED job recovered after queue timeout"
        )
        db.add(job)
        recovered += 1
    if recovered and commit:
        db.commit()
    return recovered


def research_can_run(db: Session) -> bool:
    return not bool(db.scalar(
        select(func.count()).select_from(JobRun).where(
            JobRun.job_type.in_(PRODUCTION_MUTATING_JOB_TYPES),
            JobRun.status.in_(ACTIVE_JOB_STATUSES),
        )
    ))


def production_can_run(db: Session) -> bool:
    return not bool(db.scalar(
        select(func.count()).select_from(JobRun).where(
            JobRun.job_type == RESEARCH_JOB_TYPE,
            JobRun.status == "RUNNING",
        )
    ))


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


def _acquire_research_advisory_lock(db: Session) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(select(func.pg_advisory_xact_lock(RESEARCH_ADVISORY_LOCK_KEY))).scalar_one()
