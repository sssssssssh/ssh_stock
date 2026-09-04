import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, scalar_count
from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.jobs.backfill_job import BackfillJob
from app.jobs.basic_info_job import BasicInfoJob
from app.jobs.daily_job import DailyJob
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange
from app.providers.logging_provider import LoggingMarketDataProvider
from app.providers.tushare_provider import TushareProvider
from app.repositories.job_run import start_job, update_job
from app.services.calc_metadata import config_hash
from app.services.dirty import (
    latest_raw_trade_date,
    open_dirty_ranges,
)
from app.services.job_guard import ActiveIngestionJobError, reject_if_active_ingestion_job
from app.services.quality.history_quality import (
    HistoricalDataQualityService,
    HistoricalQualitySummary,
)
from app.services.recalculation import run_recalculation

router = APIRouter()


class DailyJobRequest(BaseModel):
    trade_date: date


class BackfillJobRequest(BaseModel):
    start: date
    end: date


class RecalculateJobRequest(BaseModel):
    start: date
    end: date
    evaluate_signals: bool = Field(default=True)
    mode: str = Field(default="manual", pattern="^(manual|dirty_repair)$")


class ValidateDataJobRequest(BaseModel):
    start: date
    end: date


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


@router.post("/sync-basic")
def enqueue_sync_basic_job(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _reject_if_active_ingestion_job(db)
    job = start_job(
        db,
        "sync_basic",
        None,
        status="QUEUED",
        step="queued from api",
        metadata={"source": "api", "stage": "queued", "progress_pct": 0},
    )
    background_tasks.add_task(_run_sync_basic_job, job.id)
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
            "calculate": False,
        },
    )
    background_tasks.add_task(
        _run_backfill_job,
        job.id,
        payload.start,
        payload.end,
    )
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/recalculate")
def enqueue_recalculate_job(
    payload: RecalculateJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.end < payload.start:
        raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
    _reject_if_active_ingestion_job(db)
    start = payload.start
    end = payload.end
    dirty_range_ids: list[int] = []
    if payload.mode == "dirty_repair":
        dirty_ranges = open_dirty_ranges(db)
        if not dirty_ranges:
            raise HTTPException(status_code=404, detail="no open dirty ranges")
        latest = latest_raw_trade_date(db)
        if latest is None:
            raise HTTPException(status_code=422, detail="no stock_daily data available")
        start = min(row.dirty_start_date for row in dirty_ranges)
        end = latest
        dirty_range_ids = [row.id for row in dirty_ranges]
    settings = get_settings()
    hash_value = config_hash(settings.strategy)
    job = start_job(
        db,
        "recalculate",
        end,
        status="QUEUED",
        step="queued from api",
        metadata={
            "source": payload.mode,
            "mode": payload.mode,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "evaluate_signals": payload.evaluate_signals,
            "calc_run_id": None,
            "config_hash": hash_value,
            "dirty_range_ids": dirty_range_ids,
            "progress_pct": 0,
        },
    )
    background_tasks.add_task(
        _run_recalculate_job,
        job.id,
        start,
        end,
        payload.evaluate_signals,
        payload.mode,
        dirty_range_ids,
    )
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/validate-data")
def enqueue_validate_data_job(
    payload: ValidateDataJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.end < payload.start:
        raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
    _reject_if_active_ingestion_job(db)
    job = start_job(
        db,
        "validate_data",
        payload.end,
        status="QUEUED",
        step="queued from api",
        metadata={
            "source": "api",
            "start": payload.start.isoformat(),
            "end": payload.end.isoformat(),
            "stage": "queued",
            "progress_pct": 0,
        },
    )
    background_tasks.add_task(_run_validate_data_job, job.id, payload.start, payload.end)
    return envelope(_job_payload(job), {"accepted": True})


def _reject_if_active_ingestion_job(db: Session) -> None:
    try:
        reject_if_active_ingestion_job(db)
    except ActiveIngestionJobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _run_daily_job(job_id: uuid.UUID, trade_date: date) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, job_id)
        if not job:
            return
        try:
            DailyJob(db, _provider(db)).run(trade_date, job=job)
        except Exception as exc:
            _mark_background_failed(db, job_id, exc)


def _run_sync_basic_job(job_id: uuid.UUID) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, job_id)
        if not job:
            return
        try:
            BasicInfoJob(db, _provider(db)).run(job=job)
        except Exception as exc:
            _mark_background_failed(db, job_id, exc)


def _run_backfill_job(
    job_id: uuid.UUID,
    start: date,
    end: date,
) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, job_id)
        if not job:
            return
        try:
            BackfillJob(db, _provider(db)).run(start, end, job=job)
        except Exception as exc:
            _mark_background_failed(db, job_id, exc)


def _run_validate_data_job(job_id: uuid.UUID, start: date, end: date) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, job_id)
        if not job:
            return
        metadata: dict[str, Any] = {
            "source": "api",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "stage": "validate_data",
            "progress_pct": 0,
            "total_trade_days": 0,
            "completed_trade_days": 0,
            "pass_days": 0,
            "warning_days": 0,
            "error_days": 0,
        }
        total_rows = 0
        try:
            update_job(
                db,
                job,
                status="RUNNING",
                step="00 start validate data",
                row_count=total_rows,
                metadata=metadata,
            )

            def progress(
                summary: HistoricalQualitySummary,
                trade_date: date,
                result: object,
            ) -> None:
                nonlocal total_rows
                total_rows = summary.completed_days
                progress_pct = (
                    round(summary.completed_days / summary.total_days * 100, 1)
                    if summary.total_days
                    else 100
                )
                raw_metadata = result.as_metadata() if hasattr(result, "as_metadata") else {}
                update_job(
                    db,
                    job,
                    status="RUNNING",
                    step=f"70 validate raw data {trade_date}",
                    row_count=total_rows,
                    metadata={
                        **metadata,
                        **summary.as_dict(),
                        **raw_metadata,
                        "current_trade_date": trade_date.isoformat(),
                        "progress_pct": progress_pct,
                    },
                )

            summary = HistoricalDataQualityService(db, get_settings().strategy).validate(
                start,
                end,
                job_id=job_id,
                progress_callback=progress,
            )
            update_job(
                db,
                job,
                status="SUCCESS",
                step="200 validate data complete",
                row_count=summary.completed_days,
                metadata={
                    **metadata,
                    **summary.as_dict(),
                    "stage": "success",
                    "progress_pct": 100,
                },
            )
        except Exception as exc:
            _mark_background_failed(db, job_id, exc)


def _run_recalculate_job(
    job_id: uuid.UUID,
    start: date,
    end: date,
    evaluate_signals: bool,
    mode: str = "manual",
    dirty_range_ids: list[int] | None = None,
) -> None:
    with SessionLocal() as db:
        job = db.get(JobRun, job_id)
        if not job:
            return
        try:
            run_recalculation(
                db,
                job,
                start,
                end,
                evaluate_signals=evaluate_signals,
                mode=mode,
                dirty_ranges=_load_dirty_ranges(db, dirty_range_ids or []),
            )
        except Exception as exc:
            _mark_background_failed(db, job_id, exc)


def _provider(db: Session) -> LoggingMarketDataProvider:
    return LoggingMarketDataProvider(db, TushareProvider())


def _load_dirty_ranges(db: Session, dirty_range_ids: list[int]) -> list[DataDirtyRange]:
    if not dirty_range_ids:
        return []
    return list(
        db.execute(
            select(DataDirtyRange).where(DataDirtyRange.id.in_(dirty_range_ids))
        )
        .scalars()
        .all()
    )


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
