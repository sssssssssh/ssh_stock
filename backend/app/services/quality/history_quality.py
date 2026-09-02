import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.market_data import TradeCalendar
from app.services.quality.daily_quality import record_cross_table_quality
from app.services.quality.raw_completeness import (
    RawCompletenessResult,
    check_raw_completeness,
    ensure_stock_basic_ready,
)


@dataclass(frozen=True)
class HistoricalQualitySummary:
    total_days: int
    completed_days: int
    pass_days: int
    warning_days: int
    error_days: int

    def as_dict(self) -> dict[str, int]:
        return {
            "total_trade_days": self.total_days,
            "completed_trade_days": self.completed_days,
            "pass_days": self.pass_days,
            "warning_days": self.warning_days,
            "error_days": self.error_days,
        }


ProgressCallback = Callable[[HistoricalQualitySummary, date, RawCompletenessResult], None]


class HistoricalDataQualityService:
    def __init__(self, db: Session, strategy: dict | None = None) -> None:
        self.db = db
        self.strategy = strategy or {}

    def validate(
        self,
        start: date,
        end: date,
        *,
        job_id: uuid.UUID | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> HistoricalQualitySummary:
        ensure_stock_basic_ready(self.db)
        trade_dates = self._open_trade_dates(start, end)
        total_days = len(trade_dates)
        pass_days = 0
        warning_days = 0
        error_days = 0
        summary = HistoricalQualitySummary(total_days, 0, 0, 0, 0)
        for index, trade_date in enumerate(trade_dates, 1):
            result = self.validate_trade_date(
                trade_date,
                job_id=job_id,
                include_cross_table=True,
            )
            if result.overall_status == "PASS":
                pass_days += 1
            elif result.overall_status == "WARNING":
                warning_days += 1
            elif result.overall_status == "ERROR":
                error_days += 1
            summary = HistoricalQualitySummary(
                total_days=total_days,
                completed_days=index,
                pass_days=pass_days,
                warning_days=warning_days,
                error_days=error_days,
            )
            if progress_callback:
                progress_callback(summary, trade_date, result)
        return summary

    def validate_trade_date(
        self,
        trade_date: date,
        *,
        job_id: uuid.UUID | None = None,
        include_cross_table: bool = True,
    ) -> RawCompletenessResult:
        result = check_raw_completeness(
            self.db,
            trade_date,
            strategy=self.strategy,
            job_id=job_id,
            persist=True,
        )
        if include_cross_table:
            record_cross_table_quality(
                self.db,
                trade_date,
                job_id=job_id,
                strategy=self.strategy,
            )
        return result

    def _open_trade_dates(self, start: date, end: date) -> list[date]:
        return list(
            self.db.execute(
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
