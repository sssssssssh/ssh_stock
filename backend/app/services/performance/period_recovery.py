import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import JobRun
from app.services.performance.period_application import PERFORMANCE_PERIOD_JOB_TYPE

PERIOD_HEARTBEAT_TIMEOUT_CODE = "PERIOD_WORKER_HEARTBEAT_TIMEOUT"


def recover_stale_performance_period_jobs(
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
        select(JobRun.id, JobRun.worker_id).where(
            JobRun.job_type == PERFORMANCE_PERIOD_JOB_TYPE,
            JobRun.status == "RUNNING",
            JobRun.heartbeat_at < cutoff,
        )
    ).all()
    recovered = 0
    for job_id, worker_id in candidates:
        if before_lock_hook:
            before_lock_hook(job_id)
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
        job.status = "FAILED"
        job.finished_at = current
        job.step = "period heartbeat stale; recalculation required"
        job.error_message = (
            "worker heartbeat expired during period calculation; explicit recalculation required"
        )
        job.job_metadata = {
            **dict(job.job_metadata or {}),
            "stage": "failed",
            "error_code": PERIOD_HEARTBEAT_TIMEOUT_CODE,
        }
        db.add(job)
        recovered += 1
    db.commit()
    return recovered
