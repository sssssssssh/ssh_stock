import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, scalar_count
from app.core.db import SessionLocal, get_db
from app.jobs.backfill_job import BackfillJob
from app.jobs.daily_job import DailyJob
from app.models.job import JobRun
from app.providers.logging_provider import LoggingMarketDataProvider
from app.providers.tushare_provider import TushareProvider
from app.repositories.job_run import start_job, update_job

router = APIRouter()


class DailyJobRequest(BaseModel):
    trade_date: date


class BackfillJobRequest(BaseModel):
    start: date
    end: date
    evaluate_signals: bool = Field(default=False)


@router.get("")
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    job_type: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    row_limit = clamp_limit(limit, default=20, maximum=100)
    row_offset = clamp_offset(offset)
    filters = []
    if status:
        filters.append(JobRun.status == status)
    if job_type:
        filters.append(JobRun.job_type == job_type)

    rows = (
        db.execute(
            select(JobRun)
            .where(*filters)
            .order_by(desc(JobRun.started_at))
            .limit(row_limit)
            .offset(row_offset)
        )
        .scalars()
        .all()
    )
    total_stmt = select(func.count()).select_from(JobRun).where(*filters)
    return envelope(
        [
            _job_payload(row)
            for row in rows
        ],
        {"limit": row_limit, "offset": row_offset, "total": scalar_count(db, total_stmt)},
    )


@router.post("/daily")
def enqueue_daily_job(
    payload: DailyJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _reject_if_active_ingestion_job(db)
    job = start_job(
        db,
        "daily",
        payload.trade_date,
        status="QUEUED",
        step="queued from api",
        metadata={"source": "api", "trade_date": payload.trade_date.isoformat()},
    )
    background_tasks.add_task(_run_daily_job, job.id, payload.trade_date)
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/backfill")
def enqueue_backfill_job(
    payload: BackfillJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.end < payload.start:
        raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
    _reject_if_active_ingestion_job(db)
    job = start_job(
        db,
        "backfill",
        payload.end,
        status="QUEUED",
        step="queued from api",
        metadata={
            "source": "api",
            "start": payload.start.isoformat(),
            "end": payload.end.isoformat(),
            "evaluate_signals": payload.evaluate_signals,
        },
    )
    background_tasks.add_task(
        _run_backfill_job,
        job.id,
        payload.start,
        payload.end,
        payload.evaluate_signals,
    )
    return envelope(_job_payload(job), {"accepted": True})


def _reject_if_active_ingestion_job(db: Session) -> None:
    active = db.execute(
        select(JobRun.id)
        .where(
            JobRun.job_type.in_(["daily", "backfill"]),
            JobRun.status.in_(["QUEUED", "RUNNING"]),
        )
        .limit(1)
    ).scalar_one_or_none()
    if active:
        raise HTTPException(status_code=409, detail=f"active ingestion job exists: {active}")


def _run_daily_job(job_id: uuid.UUID, trade_date: date) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, job_id)
        if not job:
            return
        try:
            DailyJob(db, _provider(db)).run(trade_date, job=job)
        except Exception as exc:
            _mark_background_failed(db, job_id, exc)


def _run_backfill_job(
    job_id: uuid.UUID,
    start: date,
    end: date,
    evaluate_signals: bool,
) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, job_id)
        if not job:
            return
        try:
            BackfillJob(db, _provider(db)).run(start, end, job=job)
            if evaluate_signals:
                update_job(db, job, step="190 evaluate signals")
                from app.services.research import SignalEvaluationService

                rows = SignalEvaluationService(db).evaluate()
                metadata = dict(job.job_metadata or {})
                metadata["signal_eval"] = rows
                update_job(
                    db,
                    job,
                    status="SUCCESS",
                    step="200 signal eval complete",
                    metadata=metadata,
                )
        except Exception as exc:
            _mark_background_failed(db, job_id, exc)


def _provider(db: Session) -> LoggingMarketDataProvider:
    return LoggingMarketDataProvider(db, TushareProvider())


def _mark_background_failed(db: Session, job_id: uuid.UUID, exc: Exception) -> None:
    db.rollback()
    job = db.get(JobRun, job_id)
    if not job:
        return
    update_job(
        db,
        job,
        status="FAILED",
        step=job.step or "background failed",
        error_message=str(exc),
    )


def _job_payload(row: JobRun) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "job_type": row.job_type,
        "target_trade_date": row.target_trade_date.isoformat()
        if row.target_trade_date
        else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "status": row.status,
        "step": row.step,
        "row_count": row.row_count,
        "error_message": row.error_message,
        "metadata": row.job_metadata,
    }
