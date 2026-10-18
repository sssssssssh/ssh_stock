from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.job import JobRun, ProviderApiLog


def completed_data_source(calc_run_id):
    """New-format staged Derived rows are retained, but not published as ready."""
    return ~select(JobRun.id).where(
        JobRun.id == calc_run_id,
        or_(JobRun.execution_token.is_not(None), JobRun.status == "RUNNING"),
        JobRun.status != "SUCCESS",
    ).exists()


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
    from app.services.job_execution import current_execution

    execution = current_execution.get()
    if execution is not None and status == "RUNNING":
        job.parent_job_id = execution.job_id
        job.worker_id = execution.worker_id
        job.execution_token = execution.token
        job.execution_started_at = datetime.now(UTC)
        job.last_progress_at = job.execution_started_at
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
    if getattr(job, "execution_token", None) is not None:
        return _update_owned_data_job(
            db, job, status=status, step=step, row_count=row_count,
            error_message=error_message, metadata=metadata, now=now,
        )
    if status is not None:
        job.status = status
        if status in {"SUCCESS", "PARTIAL", "FAILED", "CANCELLED"}:
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


def _update_owned_data_job(db, job, *, status, step, row_count, error_message, metadata, now):
    from app.services.job_execution import JobOwnershipLost, checkpoint, current_execution

    execution = current_execution.get()
    if execution is None or (job.worker_id, job.execution_token) != (
        execution.worker_id, execution.token,
    ):
        raise JobOwnershipLost("JOB_OWNERSHIP_LOST")
    if status not in {"FAILED", "CANCELLED"}:
        checkpoint()
    values = {"last_progress_at": now}
    if status is not None:
        values["status"] = status
    if status in {"SUCCESS", "PARTIAL", "FAILED", "CANCELLED"}:
        values["finished_at"] = now
    for key, value in (("step", step), ("row_count", row_count), ("error_message", error_message)):
        if value is not None:
            values[key] = value[:2048] if key == "error_message" else value
    if metadata is not None:
        values["job_metadata"] = {**dict(job.job_metadata or {}), **metadata}
    conditions = [JobRun.id == job.id, JobRun.status == "RUNNING",
                  JobRun.worker_id == execution.worker_id,
                  JobRun.execution_token == execution.token]
    if status in {"SUCCESS", "PARTIAL"}:
        conditions.append(JobRun.cancel_requested.is_(False))
    with db.no_autoflush:
        result = db.execute(update(JobRun).where(*conditions).values(**values)
                            .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        checkpoint()
        raise JobOwnershipLost("JOB_OWNERSHIP_LOST")
    db.commit()
    db.refresh(job)
    return job


def touch_job_heartbeat(
    db: Session,
    job_id: object,
    worker_id: str,
    *,
    now: datetime | None = None,
    execution_token: object | None = None,
) -> bool:
    ownership = [JobRun.id == job_id, JobRun.status == "RUNNING", JobRun.worker_id == worker_id]
    if execution_token is not None:
        ownership.append(JobRun.execution_token == execution_token)
    result = db.execute(
        update(JobRun)
        .where(*ownership)
        .values(heartbeat_at=now or datetime.now(UTC))
    )
    db.commit()
    return result.rowcount == 1


def cancel_requested(db: Session, job_id: object) -> bool:
    result = db.execute(select(JobRun.cancel_requested).where(JobRun.id == job_id))
    scalar = getattr(result, "scalar_one_or_none", None)
    return bool(scalar()) if callable(scalar) else False


def finish_cancelled(db: Session, job: JobRun, *, metadata: dict[str, Any] | None = None) -> None:
    update_job(
        db,
        job,
        status="CANCELLED",
        step="cancelled by user",
        metadata=metadata if metadata is not None else dict(job.job_metadata or {}),
    )


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
