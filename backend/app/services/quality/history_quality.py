import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import StockDaily, TradeCalendar
from app.services.quality.daily_quality import (
    CoverageResult,
    check_daily_coverage,
    expected_stock_codes,
    persist_coverage_result,
    record_cross_table_quality,
)
from app.services.quality.raw_completeness import ensure_stock_basic_ready


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


ProgressCallback = Callable[[HistoricalQualitySummary, date, CoverageResult], None]


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
            if result.status == "PASS":
                pass_days += 1
            elif result.status == "WARNING":
                warning_days += 1
            elif result.status == "ERROR":
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
    ) -> CoverageResult:
        expected_codes = self._expected_stock_codes(trade_date)
        actual_codes = self._stock_daily_codes(trade_date)
        result = check_daily_coverage(
            trade_date=trade_date,
            actual_codes=actual_codes,
            expected_codes=expected_codes,
            warning_coverage_rate=_daily_threshold(self.strategy, "warning", 0.98),
            error_coverage_rate=_daily_threshold(self.strategy, "error", 0.95),
            dataset="stock_daily",
        )
        persist_coverage_result(
            self.db,
            result,
            duplicate_count=self._stock_daily_duplicate_count(trade_date),
            job_id=job_id,
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

    def _expected_stock_codes(self, trade_date: date) -> set[str]:
        return expected_stock_codes(self.db, trade_date)

    def _stock_daily_codes(self, trade_date: date) -> set[str]:
        return set(
            self.db.execute(
                select(StockDaily.ts_code).where(StockDaily.trade_date == trade_date)
            )
            .scalars()
            .all()
        )

    def _stock_daily_duplicate_count(self, trade_date: date) -> int:
        duplicate_rows = (
            self.db.execute(
                select(func.count())
                .select_from(
                    select(StockDaily.ts_code)
                    .where(StockDaily.trade_date == trade_date)
                    .group_by(StockDaily.ts_code)
                    .having(func.count() > 1)
                    .subquery()
                )
            ).scalar_one()
            or 0
        )
        return int(duplicate_rows)


def _daily_threshold(
    strategy: dict,
    severity: str,
    default: float,
) -> float:
    daily = strategy.get("data_quality", {}).get("daily", {})
    value = daily.get(f"{severity}_coverage_rate", default) if isinstance(daily, dict) else default
    return float(value)
