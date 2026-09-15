import os
import socket
import time
import uuid
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.backfill_job import BackfillJob
from app.jobs.basic_info_job import BasicInfoJob
from app.jobs.daily_job import DailyJob
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange
from app.providers.logging_provider import LoggingMarketDataProvider
from app.providers.tushare_provider import TushareProvider
from app.repositories.job_run import update_job
from app.services.dirty import recover_stale_processing_ranges
from app.services.job_guard import recover_stale_ingestion_jobs, scheduler_setting
from app.services.quality.history_quality import (
    HistoricalDataQualityService,
    HistoricalQualitySummary,
)
from app.services.recalculation import run_recalculation

WORKER_JOB_TYPES = ("daily", "sync_basic", "backfill", "recalculate", "validate_data")


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def claim_next_job(db: Session, worker_id: str) -> uuid.UUID | None:
    job = (
        db.execute(
            select(JobRun)
            .where(
                JobRun.status == "QUEUED",
                JobRun.job_type.in_(WORKER_JOB_TYPES),
            )
            .order_by(JobRun.started_at, JobRun.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if job is None:
        return None
    now = datetime.now(UTC)
    job.status = "RUNNING"
    job.worker_id = worker_id
    job.heartbeat_at = now
    job.step = "claimed by worker"
    db.add(job)
    db.commit()
    return job.id


def execute_claimed_job(db: Session, job_id: uuid.UUID) -> None:
    job = db.get(JobRun, job_id)
    if job is None:
        return
    metadata = dict(job.job_metadata or {})
    try:
        if job.job_type == "daily":
            provider = _provider(db)
            target = job.target_trade_date or _metadata_date(metadata, "trade_date")
            DailyJob(db, provider).run(target, job=job)
        elif job.job_type == "sync_basic":
            provider = _provider(db)
            BasicInfoJob(db, provider).run(job=job, source=str(metadata.get("source", "worker")))
        elif job.job_type == "backfill":
            provider = _provider(db)
            BackfillJob(db, provider).run(
                _metadata_date(metadata, "start"),
                _metadata_date(metadata, "end"),
                job=job,
            )
        elif job.job_type == "recalculate":
            run_recalculation(
                db,
                job,
                _metadata_date(metadata, "start"),
                _metadata_date(metadata, "end"),
                evaluate_signals=bool(metadata.get("evaluate_signals", True)),
                mode=str(metadata.get("mode", "manual")),
                dirty_ranges=_load_dirty_ranges(db, metadata.get("dirty_range_ids", [])),
            )
        elif job.job_type == "validate_data":
            run_validate_data_job(db, job, metadata)
        else:
            raise ValueError(f"unsupported worker job type: {job.job_type}")
    except Exception as exc:
        db.rollback()
        failed = db.get(JobRun, job_id)
        if failed is not None and failed.status not in {"SUCCESS", "FAILED"}:
            update_job(
                db,
                failed,
                status="FAILED",
                step=failed.step or "worker execution failed",
                error_message=str(exc),
            )
        logger.exception("worker job failed job_id={} type={}", job_id, job.job_type)


def run_worker() -> None:
    poll_seconds = float(scheduler_setting("worker_poll_seconds", 2))
    stale_hours = float(scheduler_setting("stale_job_hours", 24))
    worker_id = worker_identity()
    with SessionLocal() as db:
        recovered_jobs = recover_stale_ingestion_jobs(db, stale_job_hours=stale_hours)
        recovered_dirty = recover_stale_processing_ranges(db, stale_hours=stale_hours)
        logger.info(
            "worker startup id={} recovered_jobs={} recovered_dirty={}",
            worker_id,
            recovered_jobs,
            recovered_dirty,
        )
    while True:
        with SessionLocal() as db:
            job_id = claim_next_job(db, worker_id)
        if job_id is None:
            time.sleep(poll_seconds)
            continue
        with SessionLocal() as db:
            execute_claimed_job(db, job_id)


def run_validate_data_job(db: Session, job: JobRun, metadata: dict[str, Any]) -> None:
    start = _metadata_date(metadata, "start")
    end = _metadata_date(metadata, "end")
    base_metadata: dict[str, Any] = {
        **metadata,
        "stage": "validate_data",
        "progress_pct": 0,
        "total_trade_days": 0,
        "completed_trade_days": 0,
        "pass_days": 0,
        "warning_days": 0,
        "error_days": 0,
    }
    update_job(
        db,
        job,
        status="RUNNING",
        step="00 start validate data",
        metadata=base_metadata,
    )

    def progress(
        summary: HistoricalQualitySummary,
        trade_date: date,
        result: object,
    ) -> None:
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
            row_count=summary.completed_days,
            metadata={
                **base_metadata,
                **summary.as_dict(),
                **raw_metadata,
                "current_trade_date": trade_date.isoformat(),
                "progress_pct": progress_pct,
            },
        )

    summary = HistoricalDataQualityService(db, get_settings().strategy).validate(
        start,
        end,
        job_id=job.id,
        progress_callback=progress,
    )
    update_job(
        db,
        job,
        status="SUCCESS",
        step="200 validate data complete",
        row_count=summary.completed_days,
        metadata={
            **base_metadata,
            **summary.as_dict(),
            "stage": "success",
            "progress_pct": 100,
        },
    )


def _metadata_date(metadata: dict[str, Any], key: str) -> date:
    value = metadata.get(key)
    if isinstance(value, date):
        return value
    if not value:
        raise ValueError(f"job metadata missing date: {key}")
    return date.fromisoformat(str(value))


def _load_dirty_ranges(db: Session, ids: object) -> list[DataDirtyRange]:
    values = [int(value) for value in ids] if isinstance(ids, list) else []
    if not values:
        return []
    return list(
        db.execute(select(DataDirtyRange).where(DataDirtyRange.id.in_(values)))
        .scalars()
        .all()
    )


def _provider(db: Session) -> LoggingMarketDataProvider:
    return LoggingMarketDataProvider(db, TushareProvider())
