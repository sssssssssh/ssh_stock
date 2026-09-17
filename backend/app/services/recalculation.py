import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange, TradeCalendar
from app.repositories.job_run import update_job
from app.services.calc_metadata import config_hash
from app.services.dirty import (
    mark_dirty_ranges_failed,
    mark_dirty_ranges_processing,
    mark_dirty_ranges_resolved,
)
from app.services.factors import FactorService
from app.services.market import MarketService
from app.services.opportunity import OpportunityService
from app.services.quality.daily_quality import DataQualityError, validate_cross_table_range
from app.services.quality.raw_completeness import check_raw_completeness
from app.services.research import SignalEvaluationService
from app.services.sector import SectorService
from app.services.theme import ThemeFactorService
from app.services.trade_status import TradeStatusService
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
    opportunity_hash = config_hash(settings.opportunity_config)
    metadata: dict[str, Any] = {
        "source": mode,
        "mode": mode,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "evaluate_signals": evaluate_signals,
        "calc_run_id": str(job.id),
        "config_hash": hash_value,
        "strategy_config_hash": hash_value,
        "opportunity_config_hash": opportunity_hash,
        "factor_calc_version": "factor_v1",
        "market_calc_version": "market_v1",
        "sector_calc_version": "sector_v1",
        "theme_calc_version": "theme_v1",
        "trend_calc_version": "trend_v1",
        "opportunity_calc_version": "opportunity_v1",
        "dirty_range_ids": [row.id for row in dirty_ranges],
        "dirty_start_date": start.isoformat() if mode == "dirty_repair" else None,
        "recalc_end_date": end.isoformat() if mode == "dirty_repair" else None,
        "stage": "starting",
        "progress_pct": 0,
    }
    total_rows = 0
    try:
        analysis_start = _factor_warmup_start(db, start)
        metadata["analysis_warmup_start"] = analysis_start.isoformat()
        metadata["factor_warmup_start"] = analysis_start.isoformat()
        validate_recalculation_raw_prerequisites(
            db,
            analysis_start,
            end,
            strategy=settings.strategy,
        )
        if dirty_ranges:
            mark_dirty_ranges_processing(db, dirty_ranges)
        update_job(
            db,
            job,
            status="RUNNING",
            step="80 calculate trade status",
            row_count=total_rows,
            metadata={**metadata, "stage": "trade_status", "progress_pct": 4},
        )
        total_rows += TradeStatusService(db).recalc(
            analysis_start,
            end,
            calc_run_id=job.id,
        )
        factor_chunks = _month_chunks(analysis_start, end)
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
        total_rows += MarketService(db).recalc(analysis_start, end, calc_run_id=job.id)

        update_job(
            db,
            job,
            step="110 calculate sector heat",
            row_count=total_rows,
            metadata={**metadata, "stage": "sectors", "progress_pct": 78},
        )
        total_rows += SectorService(db).recalc(analysis_start, end, calc_run_id=job.id)

        update_job(
            db,
            job,
            step="115 calculate theme heat",
            row_count=total_rows,
            metadata={**metadata, "stage": "themes", "progress_pct": 84},
        )
        total_rows += ThemeFactorService(db).recalc(start, end, calc_run_id=job.id)

        update_job(
            db,
            job,
            step="120 calculate trend states",
            row_count=total_rows,
            metadata={**metadata, "stage": "states", "progress_pct": 90},
        )
        trend_rows = TrendService(db).recalc(analysis_start, end, calc_run_id=job.id)
        total_rows += trend_rows["states"] + trend_rows["signals"]

        update_job(
            db,
            job,
            step="130 calculate opportunities",
            row_count=total_rows,
            metadata={**metadata, "stage": "opportunities", "progress_pct": 92},
        )
        total_rows += OpportunityService(db).recalc(start, end, calc_run_id=job.id)

        update_job(
            db,
            job,
            step="180 validate cross table quality",
            row_count=total_rows,
            metadata={**metadata, "stage": "cross_table_quality", "progress_pct": 94},
        )
        cross_table_quality = validate_cross_table_range(
            db,
            start,
            end,
            job_id=job.id,
            strategy=settings.strategy,
        )
        metadata = {**metadata, **cross_table_quality.as_metadata()}
        if cross_table_quality.has_error:
            raise DataQualityError(
                "cross table quality failed: "
                f"dates={cross_table_quality.error_dates[:100]} "
                f"datasets={cross_table_quality.error_datasets}"
            )

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


def validate_recalculation_raw_prerequisites(
    db: Session,
    start: date,
    end: date,
    *,
    strategy: dict[str, Any] | None = None,
) -> None:
    open_dates = list(
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.cal_date >= start,
                TradeCalendar.cal_date <= end,
                TradeCalendar.is_open.is_(True),
            )
            .order_by(TradeCalendar.cal_date)
        )
        .scalars()
        .all()
    )
    failures: list[str] = []
    for trade_date in open_dates:
        result = check_raw_completeness(
            db,
            trade_date,
            strategy=strategy,
            persist=False,
        )
        if not result.is_complete:
            statuses = result.as_metadata()["current_day_datasets"]
            failed = {
                dataset: status
                for dataset, status in statuses.items()
                if (
                    (dataset in {"index_daily", "stock_st", "suspend_d"} and status != "PASS")
                    or (
                        dataset not in {"index_daily", "stock_st", "suspend_d"}
                        and status not in {"PASS", "WARNING"}
                    )
                )
            }
            failures.append(f"trade_date={trade_date} failed_datasets={failed} statuses={statuses}")
    if failures:
        detail = "; ".join(failures[:20])
        raise DataQualityError(
            "recalculation raw prerequisites failed; run backfill first. "
            f"dates/datasets/statuses={detail}"
        )


def _factor_warmup_start(
    db: Session,
    start: date,
    *,
    trading_days: int = 250,
) -> date:
    dates = list(
        db.execute(
            select(TradeCalendar.cal_date)
            .where(
                TradeCalendar.cal_date <= start,
                TradeCalendar.is_open.is_(True),
            )
            .order_by(TradeCalendar.cal_date.desc())
            .limit(trading_days + 1)
        )
        .scalars()
        .all()
    )
    return min(dates) if dates else start


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
