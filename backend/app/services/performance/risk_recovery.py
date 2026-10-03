import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import JobRun
from app.services.performance.risk_application import PERFORMANCE_RISK_JOB_TYPE

PERFORMANCE_RISK_HEARTBEAT_TIMEOUT_CODE = (
    "PERFORMANCE_RISK_WORKER_HEARTBEAT_TIMEOUT"
)
PERFORMANCE_RISK_HEARTBEAT_TIMEOUT_MESSAGE = (
    "worker heartbeat expired during performance risk calculation; "
    "explicit recalculation required"
)


def recover_stale_performance_risk_jobs(
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
        select(JobRun.id, JobRun.worker_id)
        .where(
            JobRun.job_type == PERFORMANCE_RISK_JOB_TYPE,
            JobRun.status == "RUNNING",
            JobRun.heartbeat_at < cutoff,
        )
        .order_by(JobRun.id)
    ).all()
    recovered = 0
    for job_id, candidate_worker_id in candidates:
        if before_lock_hook is not None:
            before_lock_hook(job_id)
        job = db.execute(
            select(JobRun)
            .where(JobRun.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
        if (
            job is None
            or job.job_type != PERFORMANCE_RISK_JOB_TYPE
            or job.status != "RUNNING"
            or job.worker_id != candidate_worker_id
            or job.heartbeat_at is None
            or job.heartbeat_at >= cutoff
        ):
            continue
        job.status = "FAILED"
        job.finished_at = current
        job.step = "risk heartbeat stale; recalculation required"
        job.error_message = PERFORMANCE_RISK_HEARTBEAT_TIMEOUT_MESSAGE
        job.job_metadata = {
            **dict(job.job_metadata or {}),
            "stage": "failed",
            "error_code": PERFORMANCE_RISK_HEARTBEAT_TIMEOUT_CODE,
        }
        db.add(job)
        recovered += 1
    db.commit()
    return recovered
