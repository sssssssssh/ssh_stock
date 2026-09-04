import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange
from app.repositories.job_run import update_job
from app.services.calc_metadata import config_hash
from app.services.dirty import (
    mark_dirty_ranges_failed,
    mark_dirty_ranges_processing,
    mark_dirty_ranges_resolved,
)
from app.services.factors import FactorService
from app.services.market import MarketService
from app.services.research import SignalEvaluationService
from app.services.sector import SectorService
from app.services.trend import TrendService


def run_recalculation(
    db: Session,
    job: JobRun,
    start: date,
    end: date,
    *,
    evaluate_signals: bool,
    mode: str = "manual",
    dirty_ranges: list[DataDirtyRange] | None = None,
) -> None:
    dirty_ranges = dirty_ranges or []
    settings = get_settings()
    hash_value = config_hash(settings.strategy)
    metadata: dict[str, Any] = {
        "source": mode,
        "mode": mode,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "evaluate_signals": evaluate_signals,
        "calc_run_id": str(job.id),
        "config_hash": hash_value,
        "factor_calc_version": "factor_v1",
        "market_calc_version": "market_v1",
        "sector_calc_version": "sector_v1",
        "dirty_range_ids": [row.id for row in dirty_ranges],
        "dirty_start_date": start.isoformat() if mode == "dirty_repair" else None,
        "recalc_end_date": end.isoformat() if mode == "dirty_repair" else None,
        "stage": "starting",
        "progress_pct": 0,
    }
    total_rows = 0
    try:
        if dirty_ranges:
            mark_dirty_ranges_processing(db, dirty_ranges)
        factor_chunks = _month_chunks(start, end)
        factor_service = FactorService(db)
        for index, (chunk_start, chunk_end) in enumerate(factor_chunks, start=1):
            start_progress = round(8 + ((index - 1) / len(factor_chunks)) * 52, 1)
            chunk_metadata = {
                **metadata,
                "stage": "factors",
                "progress_pct": start_progress,
                "factor_chunk_index": index,
                "factor_chunk_count": len(factor_chunks),
                "factor_chunk_start": chunk_start.isoformat(),
                "factor_chunk_end": chunk_end.isoformat(),
            }
            update_job(
                db,
                job,
                status="RUNNING",
                step=f"90 factors {chunk_start}..{chunk_end}",
                row_count=total_rows,
                metadata=chunk_metadata,
            )
            total_rows += factor_service.recalc(chunk_start, chunk_end, calc_run_id=job.id)
            metadata = {
                **chunk_metadata,
                "progress_pct": round(8 + (index / len(factor_chunks)) * 52, 1),
            }
            update_job(
                db,
                job,
                status="RUNNING",
                step=f"90 factors done {chunk_end}",
                row_count=total_rows,
                metadata=metadata,
            )

        update_job(
            db,
            job,
            step="100 calculate market score",
            row_count=total_rows,
            metadata={**metadata, "stage": "market", "progress_pct": 65},
        )
        total_rows += MarketService(db).recalc(start, end, calc_run_id=job.id)

        update_job(
            db,
            job,
            step="110 calculate sector heat",
            row_count=total_rows,
            metadata={**metadata, "stage": "sectors", "progress_pct": 78},
        )
        total_rows += SectorService(db).recalc(start, end, calc_run_id=job.id)

        update_job(
            db,
            job,
            step="120 calculate trend states",
            row_count=total_rows,
            metadata={**metadata, "stage": "states", "progress_pct": 90},
        )
        trend_rows = TrendService(db).recalc(start, end)
        total_rows += trend_rows["states"] + trend_rows["signals"]

        if evaluate_signals:
            update_job(
                db,
                job,
                step="190 evaluate signals",
                row_count=total_rows,
                metadata={**metadata, "stage": "signal_eval", "progress_pct": 96},
            )
            signal_eval_rows = SignalEvaluationService(db).evaluate(start=start, end=end)
            metadata["signal_eval"] = signal_eval_rows
            total_rows += signal_eval_rows["evaluated"]

        update_job(
            db,
            job,
            status="SUCCESS",
            step="200 recalculation complete",
            row_count=total_rows,
            metadata={**metadata, "stage": "success", "progress_pct": 100},
        )
        if dirty_ranges:
            mark_dirty_ranges_resolved(db, dirty_ranges)
    except Exception as exc:
        if dirty_ranges:
            mark_dirty_ranges_failed(db, dirty_ranges, str(exc))
        update_job(
            db,
            job,
            status="FAILED",
            step="recalculation failed",
            error_message=str(exc),
            row_count=total_rows,
            metadata={**metadata, "stage": "failed"},
        )
        raise


def _month_chunks(start: date, end: date) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        chunk_end = min(end, next_month - timedelta(days=1))
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def create_recalculation_job(
    db: Session,
    *,
    start: date,
    end: date,
    evaluate_signals: bool,
    mode: str,
    dirty_ranges: list[DataDirtyRange] | None = None,
    job_id: uuid.UUID | None = None,
) -> JobRun:
    from app.repositories.job_run import start_job

    dirty_ranges = dirty_ranges or []
    settings = get_settings()
    job = start_job(
        db,
        "recalculate",
        end,
        status="QUEUED",
        step="queued from scheduler" if mode == "dirty_repair" else "queued from catchup",
        metadata={
            "source": mode,
            "mode": mode,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "evaluate_signals": evaluate_signals,
            "calc_run_id": str(job_id) if job_id else None,
            "config_hash": config_hash(settings.strategy),
            "dirty_range_ids": [row.id for row in dirty_ranges],
            "progress_pct": 0,
        },
    )
    return job
