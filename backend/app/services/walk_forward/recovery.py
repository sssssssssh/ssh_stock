import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import JobRun
from app.models.walk_forward import PortfolioWalkForwardStudy
from app.services.walk_forward.application import WALK_FORWARD_VALIDATION_JOB_TYPE
from app.services.walk_forward.identity import study_lock_key, validation_lock_key

WALK_FORWARD_VALIDATION_HEARTBEAT_TIMEOUT_CODE = (
    "WALK_FORWARD_VALIDATION_WORKER_HEARTBEAT_TIMEOUT"
)


def recover_stale_walk_forward_validation_jobs(
    db: Session,
    *,
    timeout_minutes: float,
    now: datetime | None = None,
    before_lock_hook: Callable[[uuid.UUID], None] | None = None,
) -> int:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    cutoff = current - timedelta(minutes=timeout_minutes)
    candidates = db.execute(
        select(JobRun.id, JobRun.worker_id, JobRun.job_metadata).where(
            JobRun.job_type == WALK_FORWARD_VALIDATION_JOB_TYPE,
            JobRun.status == "RUNNING",
            JobRun.heartbeat_at < cutoff,
        )
    ).all()
    recovered = 0
    for job_id, worker_id, metadata in candidates:
        if before_lock_hook:
            before_lock_hook(job_id)
        try:
            study_id = uuid.UUID(str(dict(metadata or {})["study_id"]))
        except (KeyError, TypeError, ValueError):
            study_id = None
        study = None
        if study_id is not None:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(
                    select(func.pg_advisory_xact_lock(study_lock_key(study_id)))
                ).scalar_one()
            study = db.scalar(
                select(PortfolioWalkForwardStudy)
                .where(PortfolioWalkForwardStudy.id == study_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            source_hash = str(dict(metadata or {}).get("source_hash") or "")
            if source_hash and db.get_bind().dialect.name == "postgresql":
                db.execute(
                    select(
                        func.pg_advisory_xact_lock(
                            validation_lock_key(study_id, source_hash)
                        )
                    )
                ).scalar_one()
        job = db.scalar(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if (
            job is None
            or job.status != "RUNNING"
            or job.worker_id != worker_id
            or job.heartbeat_at is None
            or job.heartbeat_at >= cutoff
        ):
            continue
        cancelled = bool(
            job.cancel_requested or (study is not None and study.cancel_requested)
        )
        job.status = "CANCELLED" if cancelled else "FAILED"
        job.finished_at = current
        job.step = (
            "cancelled by walk-forward study stop gate"
            if cancelled
            else "walk-forward validation heartbeat stale; recalculate explicitly"
        )
        job.error_message = None if cancelled else (
            "worker heartbeat expired during walk-forward validation; "
            "explicit recalculation required"
        )
        job.job_metadata = {
            **dict(job.job_metadata or {}),
            "stage": "CANCELLED" if cancelled else "FAILED",
            "error_code": (
                "WALK_FORWARD_CANCELLED"
                if cancelled
                else WALK_FORWARD_VALIDATION_HEARTBEAT_TIMEOUT_CODE
            ),
        }
        db.add(job)
        recovered += 1
    db.commit()
    return recovered
