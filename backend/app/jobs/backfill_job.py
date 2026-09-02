import uuid
from datetime import date

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import (
    DataQualityDaily,
    IndexDaily,
    StockAdjFactor,
    StockDaily,
    StockDailyBasic,
    TradeCalendar,
)
from app.providers.base import MarketDataProvider
from app.repositories.job_run import start_job, update_job
from app.repositories.upsert import upsert_rows
from app.services.ingestion import IngestionService
from app.services.ingestion.normalizers import normalize_trade_calendar
from app.services.quality.history_quality import HistoricalDataQualityService


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
            update_job(
                self.db,
                job,
                step="10 sync trade_calendar",
                metadata={**metadata, "stage": "calendar", "progress_pct": 5},
            )
            calendar_df = self.provider.get_trade_calendar(start, end)
            calendar_rows = normalize_trade_calendar(calendar_df)
            total_rows += upsert_rows(self.db, TradeCalendar, calendar_rows, ["cal_date"])
            open_dates = [row["cal_date"] for row in calendar_rows if row["is_open"]]
            metadata = {
                **metadata,
                "open_days": len(open_dates),
                "completed_open_days": 0,
                "stage": "daily",
                "progress_pct": 10,
            }

            skipped_raw_days = 0
            for index, current in enumerate(open_dates, 1):
                metadata = _daily_progress(metadata, current, index, len(open_dates))
                if _raw_data_complete(self.db, current, job_id=job.id):
                    skipped_raw_days += 1
                    update_job(
                        self.db,
                        job,
                        step=f"30 skip existing raw {current}",
                        row_count=total_rows,
                        metadata={
                            **metadata,
                            "current_day_action": "skip",
                            "skipped_raw_days": skipped_raw_days,
                        },
                    )
                    continue
                update_job(
                    self.db,
                    job,
                    step=f"30 sync daily {current}",
                    row_count=total_rows,
                    metadata={
                        **metadata,
                        "current_day_action": "sync",
                        "skipped_raw_days": skipped_raw_days,
                    },
                )
                total_rows += self.ingestion.sync_daily(current, job_id=job.id)
                total_rows += self.ingestion.sync_adj_factor(current, job_id=job.id)
                total_rows += self.ingestion.sync_daily_basic(current, job_id=job.id)
                total_rows += self.ingestion.sync_index_daily(current, job_id=job.id)
            metadata = _clear_daily_progress({
                **metadata,
                "completed_open_days": len(open_dates),
                "current_open_day_index": len(open_dates),
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
    return cleaned


def _raw_data_complete(
    db: Session,
    trade_date: date,
    *,
    job_id: uuid.UUID | None = None,
) -> bool:
    table_counts = [
        _date_row_count(db, StockDaily.trade_date, trade_date),
        _date_row_count(db, StockAdjFactor.trade_date, trade_date),
        _date_row_count(db, StockDailyBasic.trade_date, trade_date),
        _date_row_count(db, IndexDaily.trade_date, trade_date),
    ]
    if any(count <= 0 for count in table_counts):
        return False

    quality_status = db.execute(
        select(DataQualityDaily.status)
        .where(DataQualityDaily.trade_date == trade_date)
        .where(DataQualityDaily.dataset == "stock_daily")
        .order_by(DataQualityDaily.checked_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if quality_status in {"PASS", "WARNING"}:
        return True
    if quality_status == "ERROR":
        return False

    result = HistoricalDataQualityService(db, get_settings().strategy).validate_trade_date(
        trade_date,
        job_id=job_id,
        include_cross_table=False,
    )
    return result.status in {"PASS", "WARNING"}


def _date_row_count(db: Session, column: object, trade_date: date) -> int:
    table = column.class_
    return int(
        db.execute(
            select(func.count()).select_from(table).where(column == trade_date)
        ).scalar_one()
    )
