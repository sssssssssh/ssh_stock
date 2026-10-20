from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.v1.common import clamp_limit, clamp_offset, envelope, scalar_count
from app.core.config import get_settings
from app.core.db import get_db
from app.core.published_db import get_published_db, published_snapshot
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange
from app.services.analysis_identity import analysis_strategy_hash
from app.services.dirty import (
    latest_raw_trade_date,
    repairable_dirty_ranges,
    unresolved_dirty_ranges,
)
from app.services.job_guard import (
    INGESTION_JOB_TYPES,
    ActiveIngestionJobError,
    QueueCapacityError,
    _acquire_ingestion_advisory_lock,
    create_queued_ingestion_job,
    scheduler_setting,
)
from app.services.paper.queue import PAPER_JOB_TYPES
from app.services.portfolio.backtest_application import (
    BACKTEST_JOB_TYPE,
    BacktestApplicationService,
    BacktestConflictError,
)
from app.services.trading_calendar_guard import TradingCalendarError, require_recalculation_days

router = APIRouter()
CANCELLABLE_RUNNING_JOB_TYPES = {
    *INGESTION_JOB_TYPES,
    "backfill",
    "recalculate",
    "RESEARCH_EVAL",
    "portfolio_backtest",
}


class DataJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DailyJobRequest(DataJobRequest):
    trade_date: date
    depends_on_job_id: UUID | None = None


class BackfillJobRequest(DataJobRequest):
    start: date
    end: date
    depends_on_job_id: UUID | None = None


class RecalculateJobRequest(DataJobRequest):
    start: date
    end: date
    evaluate_signals: bool = Field(default=True)
    mode: str = Field(default="manual", pattern="^(manual|dirty_repair)$")
    depends_on_job_id: UUID | None = None


class ValidateDataJobRequest(DataJobRequest):
    start: date
    end: date
    depends_on_job_id: UUID | None = None


@router.get("/queue")
def data_queue(db: Session = Depends(get_published_db)) -> dict:
    rows = list(db.scalars(select(JobRun).where(
        JobRun.job_type.in_(INGESTION_JOB_TYPES), JobRun.parent_job_id.is_(None),
        JobRun.status.in_(("RUNNING", "QUEUED")),
    ).order_by(JobRun.started_at, JobRun.id).execution_options(populate_existing=True)))
    payloads = _job_payloads(db, rows)
    running = [row for row in payloads if row["status"] == "RUNNING"]
    queued = [row for row in payloads if row["status"] == "QUEUED"]
    dependency_ids = {row.depends_on_job_id for row in rows if row.depends_on_job_id}
    dependencies = dict(db.execute(select(JobRun.id, JobRun.status).where(
        JobRun.id.in_(dependency_ids))).all()) if dependency_ids else {}
    for position, row in enumerate(queued, 1):
        row["queue_position"] = position
        if row["depends_on_job_id"]:
            row["dependency_status"] = dependencies.get(UUID(row["depends_on_job_id"]), "UNKNOWN")
    return envelope({"running": running, "queued": queued,
                     "running_count": len(running), "queued_count": len(queued)})


def _creation_response(job: JobRun, db: Session) -> dict:
    duplicate = bool(getattr(job, "_queue_deduplicated", False))
    with published_snapshot(db) as reader:
        queue = data_queue(reader)["data"]
        current = next((row for row in [*queue["running"], *queue["queued"]]
                        if row["id"] == str(job.id)), None)
        if current is None:
            current = _job_payloads(reader, [reader.get(JobRun, job.id)])[0]
    return envelope(current, {"accepted": not duplicate, "deduplicated": duplicate,
                              "queue_position": current.get("queue_position")})


def _execution_unconfirmed(job: JobRun) -> bool:
    return job.status == "RUNNING" and (
        bool(dict(job.job_metadata or {}).get("execution_unconfirmed")) or
        job.job_type in INGESTION_JOB_TYPES and job.execution_token is None
    )


@router.get("")
def list_jobs(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    job_type: str | None = None,
    db: Session = Depends(get_published_db),
) -> dict:
    row_limit = clamp_limit(limit, default=20, maximum=100)
    row_offset = clamp_offset(offset)
    filters = [JobRun.job_type.not_in(PAPER_JOB_TYPES)]
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
        _job_payloads(db, rows),
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
        metadata={"source": "api", "trade_date": payload.trade_date.isoformat(),
                  "depends_on_job_id": _dependency_id(payload)},
    )
    return _creation_response(job, db)


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
    return _creation_response(job, db)


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
            "depends_on_job_id": _dependency_id(payload),
        },
    )
    return _creation_response(job, db)


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
    try:
        require_recalculation_days(db, start, end)
    except TradingCalendarError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code}) from exc
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
            "depends_on_job_id": _dependency_id(payload),
        },
    )
    return _creation_response(job, db)


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
            "depends_on_job_id": _dependency_id(payload),
        },
    )
    return _creation_response(job, db)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    job = db.get(JobRun, job_id)
    if job is None or job.job_type in PAPER_JOB_TYPES:
        raise HTTPException(status_code=404, detail="job not found")
    if job.job_type == BACKTEST_JOB_TYPE:
        raw_run_id = dict(job.job_metadata or {}).get("portfolio_run_id")
        try:
            run_id = UUID(str(raw_run_id))
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=409,
                detail="portfolio backtest job has invalid run identity",
            ) from exc
        try:
            _, job = BacktestApplicationService(db).cancel(run_id)
        except BacktestConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        assert job is not None
        return envelope(_job_payload(job))
    _acquire_ingestion_advisory_lock(db)
    # Refresh under the same row lock used by claim/terminal CAS, never write a
    # detached GET snapshot over a concurrently completed job.
    if job.parent_job_id:
        parent = db.scalar(select(JobRun).where(JobRun.id == job.parent_job_id)
                           .with_for_update(key_share=True).execution_options(populate_existing=True))
        if parent and _execution_unconfirmed(parent):
            db.rollback()
            raise HTTPException(status_code=409, detail={"code": "JOB_EXECUTION_UNCONFIRMED"})
        if parent and parent.status == "RUNNING":
            parent.cancel_requested = True
            parent.cancel_requested_at = parent.cancel_requested_at or datetime.now(UTC)
    # NO KEY UPDATE still serializes claim/terminal writes, but is compatible
    # with candidate FK KEY SHARE locks; do not wait for the whole candidate tx.
    job = db.scalar(select(JobRun).where(JobRun.id == job_id).with_for_update(key_share=True)
                    .execution_options(populate_existing=True))
    if job.status == "CANCELLED":
        # Idempotency must not add an audit timestamp or cancel a parent after
        # this child's terminal state has already won the race.
        db.rollback()
        return envelope(_job_payload(job), {"cancel_accepted": True, "cancel_completed": True})
    if job.status == "QUEUED":
        job.status = "CANCELLED"
        job.cancel_requested = True
        job.finished_at = datetime.now(UTC)
        job.step = "cancelled before execution"
    elif job.status == "RUNNING":
        if _execution_unconfirmed(job):
            db.rollback()
            raise HTTPException(status_code=409, detail={"code": "JOB_EXECUTION_UNCONFIRMED"})
        if job.job_type not in CANCELLABLE_RUNNING_JOB_TYPES:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "JOB_TYPE_NOT_CANCELLABLE_WHILE_RUNNING",
                    "message": (
                        f"running job type {job.job_type} does not support safe cancellation"
                    ),
                },
            )
        job.cancel_requested = True
    elif job.status != "CANCELLED":
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "JOB_ALREADY_TERMINAL"})
    job.cancel_requested_at = job.cancel_requested_at or datetime.now(UTC)
    db.add(job)
    db.commit()
    db.refresh(job)
    return envelope(_job_payload(job), {"cancel_accepted": True,
                                       "cancel_completed": job.status == "CANCELLED"})


def _dependency_id(payload) -> str | None:
    return str(payload.depends_on_job_id) if payload.depends_on_job_id else None


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
    except QueueCapacityError as exc:
        raise HTTPException(status_code=429, detail={"code": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}) from exc


def _load_dirty_ranges(db: Session, dirty_range_ids: list[int]) -> list[DataDirtyRange]:
    if not dirty_range_ids:
        return []
    return list(
        db.execute(select(DataDirtyRange).where(DataDirtyRange.id.in_(dirty_range_ids)))
        .scalars()
        .all()
    )


def _job_payloads(db, rows):
    if not rows:
        return []
    identities = {row.parent_job_id or row.id for row in rows}
    publications = {record.job_id: record for record in db.scalars(
        select(DataPublication).where(DataPublication.job_id.in_(identities)))}
    payloads = []
    for row in rows:
        payload = _job_payload(row)
        record = publications.get(row.parent_job_id or row.id)
        if record:
            state = record.state
            if state == "ABORTED" and row.status == "SUCCESS" and dict(
                    row.job_metadata or {}).get("publication", {}).get("state") == "NO_CHANGES":
                state = "NO_CHANGES"
            payload["publication"] = {"state": state, "identity": str(record.job_id),
                "published_at": record.published_at.isoformat() if record.published_at else None,
                "parent_owned": row.parent_job_id is not None}
        payloads.append(payload)
    return payloads


def _job_payload(row: JobRun) -> dict[str, Any]:
    unconfirmed = _execution_unconfirmed(row)
    reference = row.heartbeat_at or row.started_at
    if reference is not None and reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    heartbeat_stale = row.status == "RUNNING" and (
        reference is None or reference <= datetime.now(UTC) - timedelta(
            minutes=float(scheduler_setting("running_heartbeat_timeout_minutes", 15))
        )
    )
    now = datetime.now(UTC)
    def elapsed(value):
        if value is None:
            return 0
        return (now - (value if value.tzinfo else value.replace(tzinfo=UTC))).total_seconds()
    return {
        "id": str(row.id),
        "job_type": row.job_type,
        "target_trade_date": row.target_trade_date.isoformat() if row.target_trade_date else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
        "heartbeat_stale": heartbeat_stale,
        "execution_unconfirmed": unconfirmed,
        "worker_id": row.worker_id,
        "status": row.status,
        "step": row.step,
        "row_count": row.row_count,
        "error_message": row.error_message,
        "cancel_requested": row.cancel_requested,
        "execution_started_at": (row.execution_started_at.isoformat()
                                 if row.execution_started_at else None),
        "cancel_requested_at": (row.cancel_requested_at.isoformat()
                                if row.cancel_requested_at else None),
        "last_progress_at": row.last_progress_at.isoformat() if row.last_progress_at else None,
        "parent_job_id": str(row.parent_job_id) if row.parent_job_id else None,
        "depends_on_job_id": str(row.depends_on_job_id) if row.depends_on_job_id else None,
        "can_cancel": row.status == "QUEUED" or (
            row.status == "RUNNING" and row.job_type in CANCELLABLE_RUNNING_JOB_TYPES
            and not row.cancel_requested and not unconfirmed
        ),
        "progress_stalled": (row.status == "RUNNING" and row.last_progress_at is not None
            and elapsed(row.last_progress_at) >= float(
                scheduler_setting("progress_warning_seconds", 600))),
        "cancel_delayed": (row.status == "RUNNING" and bool(row.cancel_requested)
            and elapsed(row.cancel_requested_at) >= float(
                scheduler_setting("cancel_warning_seconds", 120))),
        "metadata": row.job_metadata,
    }
