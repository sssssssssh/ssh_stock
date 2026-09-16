from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.job import JobRun, ProviderApiLog


def start_job(
    db: Session,
    job_type: str,
    target_trade_date: date | None,
    *,
    status: str = "RUNNING",
    step: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> JobRun:
    job = JobRun(
        job_type=job_type,
        target_trade_date=target_trade_date,
        status=status,
        step=step,
        row_count=0,
        job_metadata=metadata or {},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(
    db: Session,
    job: JobRun,
    *,
    status: str | None = None,
    step: str | None = None,
    row_count: int | None = None,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> JobRun:
    now = datetime.now(UTC)
    if status is not None:
        job.status = status
        if status in {"SUCCESS", "PARTIAL", "FAILED"}:
            job.finished_at = now
    if status == "RUNNING" or (status is None and job.status == "RUNNING"):
        job.heartbeat_at = now
    if step is not None:
        job.step = step
    if row_count is not None:
        job.row_count = row_count
    if error_message is not None:
        job.error_message = error_message[:2048]
    if metadata is not None:
        job.job_metadata = metadata
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def touch_job_heartbeat(
    db: Session,
    job_id: object,
    worker_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    result = db.execute(
        update(JobRun)
        .where(
            JobRun.id == job_id,
            JobRun.status == "RUNNING",
            JobRun.worker_id == worker_id,
        )
        .values(heartbeat_at=now or datetime.now(UTC))
    )
    db.commit()
    return result.rowcount == 1


def log_provider_call(
    db: Session,
    *,
    provider: str,
    api_name: str,
    trade_date: date | None,
    elapsed_ms: int | None,
    row_count: int | None,
    status: str,
    error_type: str | None = None,
) -> None:
    db.add(
        ProviderApiLog(
            provider=provider,
            api_name=api_name,
            trade_date=trade_date,
            elapsed_ms=elapsed_ms,
            row_count=row_count,
            status=status,
            error_type=error_type,
        )
    )
