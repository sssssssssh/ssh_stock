import uuid
from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import IndexDaily, TradeCalendar
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job, update_job
from app.repositories.upsert import upsert_rows
from app.services.ingestion import IngestionService
from app.services.ingestion.normalizers import normalize_trade_calendar
from app.services.quality.raw_completeness import (
    RawCompletenessResult,
    check_raw_completeness,
    ensure_stock_basic_ready,
    validate_trade_calendar_rows,
)

RAW_DATASET_STEPS = {
    "stock_st": ("20 sync stock_st", "sync_stock_st"),
    "suspend_d": ("25 sync suspend_d", "sync_suspend_daily"),
    "stock_daily": ("30 sync daily", "sync_daily"),
    "adj_factor": ("40 sync adj_factor", "sync_adj_factor"),
    "daily_basic": ("50 sync daily_basic", "sync_daily_basic"),
    "index_daily": ("60 sync index_daily", "sync_index_daily"),
    "stk_limit": ("66 sync stk_limit", "sync_stock_limit"),
}


class BackfillJob:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.provider = provider
        self.ingestion = IngestionService(db, provider)

    def run(self, start: date, end: date, job: JobRun | None = None) -> None:
        job = job or start_job(self.db, "backfill", end)
        metadata: dict[str, object] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "stage": "starting",
            "progress_pct": 0,
        }
        update_job(
            self.db,
            job,
            status="RUNNING",
            step="00 start backfill",
            metadata=metadata,
        )
        total_rows = 0
        try:
            ensure_stock_basic_ready(self.db)
            update_job(
                self.db,
                job,
                step="10 sync trade_calendar",
                metadata={**metadata, "stage": "calendar", "progress_pct": 5},
            )
            calendar_df = self.provider.get_trade_calendar(start, end)
            calendar_rows = normalize_trade_calendar(calendar_df)
            validate_trade_calendar_rows(start, end, calendar_rows)
            total_rows += upsert_rows(self.db, TradeCalendar, calendar_rows, ["cal_date"])
            self.db.commit()
            open_dates = [row["cal_date"] for row in calendar_rows if row["is_open"]]
            metadata = {
                **metadata,
                "open_days": len(open_dates),
                "completed_open_days": 0,
                "stage": "daily",
                "progress_pct": 10,
            }
            if _any_index_daily_incomplete(self.db, open_dates):
                update_job(
                    self.db,
                    job,
                    step="60 sync index_daily range",
                    row_count=total_rows,
                    metadata={**metadata, "stage": "index_daily_range", "progress_pct": 14},
                )
                try:
                    total_rows += self.ingestion.sync_index_daily_range(start, end, job_id=job.id)
                except Exception as exc:
                    self.db.rollback()
                    logger.warning(
                        "index_daily range sync failed; "
                        "falling back to daily sync start={} end={} error={}",
                        start,
                        end,
                        exc,
                    )
                    metadata = {
                        **metadata,
                        "index_daily_range_status": "WARNING",
                        "index_daily_range_error": str(exc)[:512],
                    }
                    update_job(
                        self.db,
                        job,
                        step="60 index_daily range fallback",
                        row_count=total_rows,
                        metadata=metadata,
                    )

            skipped_raw_days = 0
            synced_dataset_count = 0
            skipped_dataset_count = 0
            for index, current in enumerate(open_dates, 1):
                metadata = _daily_progress(metadata, current, index, len(open_dates))
                completeness = check_raw_completeness(
                    self.db,
                    current,
                    strategy=get_settings().strategy,
                    job_id=job.id,
                    persist=True,
                )
                if completeness.is_complete:
                    skipped_raw_days += 1
                    skipped_dataset_count += len(RAW_DATASET_STEPS)
                    update_job(
                        self.db,
                        job,
                        step=f"30 skip existing raw {current}",
                        row_count=total_rows,
                        metadata={
                            **metadata,
                            **completeness.as_metadata(),
                            "current_day_action": "skip",
                            "skipped_raw_days": skipped_raw_days,
                            "synced_dataset_count": synced_dataset_count,
                            "skipped_dataset_count": skipped_dataset_count,
                        },
                    )
                    continue

                for dataset in RAW_DATASET_STEPS:
                    completeness = _refresh_after_stock_daily_if_needed(
                        self.db,
                        current,
                        completeness,
                        job.id,
                    )
                    dataset_status = completeness.dataset(dataset).status
                    if _dataset_is_skippable(completeness, dataset):
                        skipped_dataset_count += 1
                        continue

                    step_prefix, method_name = RAW_DATASET_STEPS[dataset]
                    update_job(
                        self.db,
                        job,
                        step=f"{step_prefix} {current}",
                        row_count=total_rows,
                        metadata={
                            **metadata,
                            **completeness.as_metadata(),
                            "current_day_action": "sync",
                            "current_day_dataset": dataset,
                            "current_day_dataset_status": dataset_status,
                            "skipped_raw_days": skipped_raw_days,
                            "synced_dataset_count": synced_dataset_count,
                            "skipped_dataset_count": skipped_dataset_count,
                        },
                    )
                    sync_method = getattr(self.ingestion, method_name)
                    total_rows += sync_method(current, job_id=job.id)
                    synced_dataset_count += 1
                    completeness = check_raw_completeness(
                        self.db,
                        current,
                        strategy=get_settings().strategy,
                        job_id=job.id,
                        persist=True,
                    )

                if not completeness.is_complete:
                    raise ValueError(_raw_incomplete_error(completeness))
            metadata = _clear_daily_progress({
                **metadata,
                "completed_open_days": len(open_dates),
                "current_open_day_index": len(open_dates),
                "synced_dataset_count": synced_dataset_count,
                "skipped_dataset_count": skipped_dataset_count,
            })

            update_job(
                self.db,
                job,
                status="SUCCESS",
                step="180 raw sync complete",
                row_count=total_rows,
                metadata={
                    **metadata,
                    "completed_open_days": len(open_dates),
                    "stage": "success",
                    "progress_pct": 100,
                },
            )
            logger.info("backfill job success start={} end={} rows={}", start, end, total_rows)
        except Exception as exc:
            self.db.rollback()
            update_job(self.db, job, status="FAILED", row_count=total_rows, error_message=str(exc))
            logger.exception("backfill job failed start={} end={}", start, end)
            raise


def _daily_progress(
    metadata: dict[str, object],
    current: date,
    completed_open_days: int,
    open_days: int,
) -> dict[str, object]:
    daily_pct = completed_open_days / open_days if open_days else 1
    return {
        **metadata,
        "stage": "daily",
        "current_trade_date": current.isoformat(),
        "current_open_day_index": completed_open_days,
        "completed_open_days": max(0, completed_open_days - 1),
        "open_days": open_days,
        "progress_pct": round(16 + daily_pct * 59, 1),
    }


def _clear_daily_progress(metadata: dict[str, object]) -> dict[str, object]:
    cleaned = dict(metadata)
    cleaned.pop("current_trade_date", None)
    cleaned.pop("current_open_day_index", None)
    cleaned.pop("completed_open_days", None)
    cleaned.pop("current_day_action", None)
    cleaned.pop("current_day_dataset", None)
    cleaned.pop("current_day_dataset_status", None)
    return cleaned


def _raw_data_complete(
    db: Session,
    trade_date: date,
    *,
    job_id: uuid.UUID | None = None,
) -> bool:
    return check_raw_completeness(
        db,
        trade_date,
        strategy=get_settings().strategy,
        job_id=job_id,
        persist=True,
    ).is_complete


def _dataset_is_skippable(completeness: RawCompletenessResult, dataset: str) -> bool:
    if dataset == "index_daily":
        return completeness.index_daily.status == "PASS"
    detail = completeness.dataset(dataset)
    if detail is None:
        return True
    if dataset in {"stock_st", "suspend_d"}:
        return detail.status == "PASS"
    return detail.is_acceptable


def _refresh_after_stock_daily_if_needed(
    db: Session,
    trade_date: date,
    completeness: RawCompletenessResult,
    job_id: uuid.UUID,
) -> RawCompletenessResult:
    if completeness.stock_daily.is_acceptable:
        return completeness
    return check_raw_completeness(
        db,
        trade_date,
        strategy=get_settings().strategy,
        job_id=job_id,
        persist=True,
    )


def _raw_incomplete_error(completeness: RawCompletenessResult) -> str:
    statuses = completeness.as_metadata()["current_day_datasets"]
    return (
        "raw data incomplete after sync: "
        f"trade_date={completeness.trade_date} statuses={statuses}"
    )


def _any_index_daily_incomplete(db: Session, open_dates: list[date]) -> bool:
    if not open_dates:
        return False
    expected = set(
        get_settings().strategy.get("benchmark", {}).get(
            "market_indices", ["000300.SH"]
        )
    )
    existing: dict[date, set[str]] = {trade_date: set() for trade_date in open_dates}
    rows = db.execute(
        select(IndexDaily.trade_date, IndexDaily.ts_code).where(
            IndexDaily.trade_date.in_(open_dates),
            IndexDaily.ts_code.in_(expected),
            IndexDaily.close.is_not(None),
            IndexDaily.close > 0,
            IndexDaily.pre_close.is_not(None),
            IndexDaily.pre_close > 0,
        )
    ).all()
    for trade_date, ts_code in rows:
        existing[trade_date].add(ts_code)
    return any(not expected <= existing[trade_date] for trade_date in open_dates)
