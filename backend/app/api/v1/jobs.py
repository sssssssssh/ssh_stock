from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, scalar_count
from app.core.config import get_settings
from app.core.db import get_db
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange
from app.services.analysis_identity import analysis_strategy_hash
from app.services.dirty import (
    latest_raw_trade_date,
    repairable_dirty_ranges,
    unresolved_dirty_ranges,
)
from app.services.job_guard import (
    ActiveIngestionJobError,
    create_queued_ingestion_job,
    scheduler_setting,
)

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
        [_job_payload(row) for row in rows],
        {"limit": row_limit, "offset": row_offset, "total": scalar_count(db, total_stmt)},
    )


@router.post("/daily")
def enqueue_daily_job(
    payload: DailyJobRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = _enqueue_job(
        db,
        "daily",
        payload.trade_date,
        status="QUEUED",
        step="queued from api",
        metadata={"source": "api", "trade_date": payload.trade_date.isoformat()},
    )
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/sync-basic")
def enqueue_sync_basic_job(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = _enqueue_job(
        db,
        "sync_basic",
        None,
        status="QUEUED",
        step="queued from api",
        metadata={"source": "api", "stage": "queued", "progress_pct": 0},
    )
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/backfill")
def enqueue_backfill_job(
    payload: BackfillJobRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.end < payload.start:
        raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
    job = _enqueue_job(
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
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/recalculate")
def enqueue_recalculate_job(
    payload: RecalculateJobRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.end < payload.start:
        raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
    start = payload.start
    end = payload.end
    dirty_range_ids: list[int] = []
    if payload.mode == "dirty_repair":
        dirty_ranges = repairable_dirty_ranges(
            db,
            max_retry_count=int(scheduler_setting("dirty_max_retry_count", 3)),
        )
        if not dirty_ranges:
            if unresolved_dirty_ranges(db):
                raise HTTPException(
                    status_code=422,
                    detail="no repairable dirty ranges; manual intervention required",
                )
            raise HTTPException(status_code=404, detail="no repairable dirty ranges")
        latest = latest_raw_trade_date(db)
        if latest is None:
            raise HTTPException(status_code=422, detail="no stock_daily data available")
        start = min(row.dirty_start_date for row in dirty_ranges)
        end = latest
        dirty_range_ids = [row.id for row in dirty_ranges]
    settings = get_settings()
    hash_value = analysis_strategy_hash(settings.strategy)
    job = _enqueue_job(
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
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/validate-data")
def enqueue_validate_data_job(
    payload: ValidateDataJobRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if payload.end < payload.start:
        raise HTTPException(status_code=400, detail="end must be greater than or equal to start")
    job = _enqueue_job(
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
    return envelope(_job_payload(job), {"accepted": True})


@router.post("/{job_id}/cancel")
def cancel_job(job_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(JobRun, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == "QUEUED":
        job.status = "CANCELLED"
        job.cancel_requested = True
        job.finished_at = datetime.now(UTC)
        job.step = "cancelled before execution"
    elif job.status == "RUNNING":
        job.cancel_requested = True
        job.step = "cancellation requested"
    elif job.status != "CANCELLED":
        raise HTTPException(status_code=409, detail="job is already finished")
    db.add(job)
    db.commit()
    db.refresh(job)
    return envelope(_job_payload(job))


def _enqueue_job(
    db: Session,
    job_type: str,
    target_trade_date: date | None,
    *,
    status: str,
    step: str,
    metadata: dict[str, Any],
) -> JobRun:
    try:
        return create_queued_ingestion_job(
            db,
            job_type,
            target_trade_date,
            step=step,
            metadata=metadata,
        )
    except ActiveIngestionJobError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _load_dirty_ranges(db: Session, dirty_range_ids: list[int]) -> list[DataDirtyRange]:
    if not dirty_range_ids:
        return []
    return list(
        db.execute(select(DataDirtyRange).where(DataDirtyRange.id.in_(dirty_range_ids)))
        .scalars()
        .all()
    )


def _job_payload(row: JobRun) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "job_type": row.job_type,
        "target_trade_date": row.target_trade_date.isoformat() if row.target_trade_date else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
        "worker_id": row.worker_id,
        "status": row.status,
        "step": row.step,
        "row_count": row.row_count,
        "error_message": row.error_message,
        "cancel_requested": row.cancel_requested,
        "metadata": row.job_metadata,
    }
