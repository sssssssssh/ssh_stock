import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import (
    IndexDaily,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    TradeCalendar,
)
from app.services.quality.daily_quality import (
    CoverageResult,
    check_daily_coverage,
    expected_stock_codes,
    persist_coverage_result,
)

RAW_PASS_STATUSES = {"PASS", "WARNING"}


@dataclass(frozen=True)
class RawDatasetCompleteness:
    dataset: str
    status: str
    expected_rows: int
    actual_rows: int
    coverage_rate: float | None
    missing_codes: list[str]
    extra_codes: list[str]

    @property
    def is_acceptable(self) -> bool:
        return self.status in RAW_PASS_STATUSES


@dataclass(frozen=True)
class RawCompletenessResult:
    trade_date: date
    stock_daily: RawDatasetCompleteness
    adj_factor: RawDatasetCompleteness
    daily_basic: RawDatasetCompleteness
    index_daily: RawDatasetCompleteness

    @property
    def stock_daily_status(self) -> str:
        return self.stock_daily.status

    @property
    def adj_factor_status(self) -> str:
        return self.adj_factor.status

    @property
    def daily_basic_status(self) -> str:
        return self.daily_basic.status

    @property
    def index_daily_status(self) -> str:
        return self.index_daily.status

    @property
    def is_complete(self) -> bool:
        return (
            self.stock_daily.is_acceptable
            and self.adj_factor.is_acceptable
            and self.daily_basic.is_acceptable
            and self.index_daily.status == "PASS"
        )

    def dataset(self, name: str) -> RawDatasetCompleteness:
        return {
            "stock_daily": self.stock_daily,
            "adj_factor": self.adj_factor,
            "daily_basic": self.daily_basic,
            "index_daily": self.index_daily,
        }[name]

    def as_metadata(self) -> dict[str, object]:
        return {
            "stock_daily_status": self.stock_daily_status,
            "adj_factor_status": self.adj_factor_status,
            "daily_basic_status": self.daily_basic_status,
            "index_daily_status": self.index_daily_status,
            "current_day_datasets": {
                "stock_daily": self.stock_daily_status,
                "adj_factor": self.adj_factor_status,
                "daily_basic": self.daily_basic_status,
                "index_daily": self.index_daily_status,
            },
            "error_dataset_count": sum(
                1
                for dataset in [
                    self.stock_daily,
                    self.adj_factor,
                    self.daily_basic,
                    self.index_daily,
                ]
                if dataset.status == "ERROR"
            ),
        }


def ensure_stock_basic_ready(db: Session) -> None:
    rows = db.execute(
        select(StockBasic.list_status, func.count())
        .select_from(StockBasic)
        .group_by(StockBasic.list_status)
    ).all()
    counts = {str(status): int(count) for status, count in rows if status}
    if counts.get("L", 0) <= 0 or counts.get("D", 0) <= 0:
        raise RuntimeError("stock_basic is missing or incomplete, run sync-basic first")


def validate_trade_calendar_rows(start: date, end: date, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("trade_calendar returned empty response")
    dates = sorted(row["cal_date"] for row in rows if row.get("cal_date"))
    if not dates:
        raise ValueError("trade_calendar returned no valid calendar dates")
    if dates[0] > start or dates[-1] < end:
        raise ValueError(
            "trade_calendar returned incomplete date range: "
            f"requested={start}..{end} actual={dates[0]}..{dates[-1]}"
        )


def trade_calendar_open_status(db: Session, trade_date: date) -> bool | None:
    return db.execute(
        select(TradeCalendar.is_open).where(TradeCalendar.cal_date == trade_date)
    ).scalar_one_or_none()


def check_raw_completeness(
    db: Session,
    trade_date: date,
    *,
    strategy: dict[str, Any] | None = None,
    job_id: uuid.UUID | None = None,
    persist: bool = False,
) -> RawCompletenessResult:
    strategy = strategy or {}
    stock_daily_codes = _codes_for_date(db, StockDaily, StockDaily.trade_date, trade_date)
    adj_factor_codes = _codes_for_date(db, StockAdjFactor, StockAdjFactor.trade_date, trade_date)
    daily_basic_codes = _codes_for_date(
        db, StockDailyBasic, StockDailyBasic.trade_date, trade_date
    )
    index_daily_codes = _codes_for_date(db, IndexDaily, IndexDaily.trade_date, trade_date)

    # Current expected universe does not subtract suspended stocks yet. Milestone 9 should
    # introduce suspension data and use active stocks minus suspended stocks here.
    stock_daily = _coverage_dataset(
        db,
        trade_date,
        "stock_daily",
        expected_stock_codes(db, trade_date),
        stock_daily_codes,
        warning_coverage_rate=_daily_threshold(strategy, "warning", 0.98),
        error_coverage_rate=_daily_threshold(strategy, "error", 0.95),
        job_id=job_id,
        persist=persist,
    )
    adj_factor = _coverage_dataset(
        db,
        trade_date,
        "adj_factor",
        stock_daily_codes,
        adj_factor_codes,
        warning_coverage_rate=_raw_threshold(strategy, "adj_factor", "warning", 0.98),
        error_coverage_rate=_raw_threshold(strategy, "adj_factor", "error", 0.95),
        job_id=job_id,
        persist=persist,
    )
    daily_basic = _coverage_dataset(
        db,
        trade_date,
        "daily_basic",
        stock_daily_codes,
        daily_basic_codes,
        warning_coverage_rate=_raw_threshold(strategy, "daily_basic", "warning", 0.98),
        error_coverage_rate=_raw_threshold(strategy, "daily_basic", "error", 0.95),
        job_id=job_id,
        persist=persist,
    )
    index_daily = _index_daily_dataset(
        db,
        trade_date,
        _benchmark_indices(strategy),
        index_daily_codes,
        job_id=job_id,
        persist=persist,
    )
    return RawCompletenessResult(
        trade_date=trade_date,
        stock_daily=stock_daily,
        adj_factor=adj_factor,
        daily_basic=daily_basic,
        index_daily=index_daily,
    )


def _coverage_dataset(
    db: Session,
    trade_date: date,
    dataset: str,
    expected_codes: set[str],
    actual_codes: set[str],
    *,
    warning_coverage_rate: float,
    error_coverage_rate: float,
    job_id: uuid.UUID | None,
    persist: bool,
) -> RawDatasetCompleteness:
    result = check_daily_coverage(
        trade_date=trade_date,
        actual_codes=actual_codes,
        expected_codes=expected_codes,
        warning_coverage_rate=warning_coverage_rate,
        error_coverage_rate=error_coverage_rate,
        dataset=dataset,
    )
    if persist:
        persist_coverage_result(db, result, job_id=job_id)
    return RawDatasetCompleteness(
        dataset=dataset,
        status=result.status,
        expected_rows=result.expected_rows,
        actual_rows=result.actual_rows,
        coverage_rate=result.coverage_rate,
        missing_codes=result.missing_codes,
        extra_codes=result.extra_codes,
    )


def _index_daily_dataset(
    db: Session,
    trade_date: date,
    expected_codes: set[str],
    actual_codes: set[str],
    *,
    job_id: uuid.UUID | None,
    persist: bool,
) -> RawDatasetCompleteness:
    status = "PASS" if expected_codes and expected_codes <= actual_codes else "ERROR"
    coverage_rate = (
        len(expected_codes & actual_codes) / len(expected_codes) if expected_codes else None
    )
    result = check_daily_coverage(
        trade_date=trade_date,
        actual_codes=actual_codes,
        expected_codes=expected_codes,
        warning_coverage_rate=1.0,
        error_coverage_rate=1.0,
        dataset="index_daily",
    )
    result = CoverageResult(
        trade_date=result.trade_date,
        dataset=result.dataset,
        expected_rows=result.expected_rows,
        actual_rows=result.actual_rows,
        coverage_rate=coverage_rate,
        missing_codes=result.missing_codes,
        extra_codes=result.extra_codes,
        status=status,
        warning_count=0,
        error_count=0 if status == "PASS" else 1,
    )
    if persist:
        persist_coverage_result(db, result, job_id=job_id)
    return RawDatasetCompleteness(
        dataset="index_daily",
        status=status,
        expected_rows=len(expected_codes),
        actual_rows=len(actual_codes),
        coverage_rate=coverage_rate,
        missing_codes=sorted(expected_codes - actual_codes),
        extra_codes=sorted(actual_codes - expected_codes),
    )


def _codes_for_date(db: Session, model: type, column: Any, trade_date: date) -> set[str]:
    return set(
        db.execute(select(model.ts_code).where(column == trade_date))
        .scalars()
        .all()
    )


def _benchmark_indices(strategy: dict[str, Any]) -> set[str]:
    benchmark = strategy.get("benchmark", {}) if isinstance(strategy, dict) else {}
    codes = benchmark.get("market_indices") if isinstance(benchmark, dict) else None
    if not codes and isinstance(benchmark, dict) and benchmark.get("primary"):
        codes = [benchmark["primary"]]
    return {str(code) for code in (codes or ["000300.SH"]) if code}


def _daily_threshold(strategy: dict[str, Any], severity: str, default: float) -> float:
    daily = strategy.get("data_quality", {}).get("daily", {})
    value = daily.get(f"{severity}_coverage_rate", default) if isinstance(daily, dict) else default
    return float(value)


def _raw_threshold(
    strategy: dict[str, Any],
    dataset: str,
    severity: str,
    default: float,
) -> float:
    raw_quality = strategy.get("raw_quality", {}) if isinstance(strategy, dict) else {}
    dataset_config = raw_quality.get(dataset, {}) if isinstance(raw_quality, dict) else {}
    if isinstance(dataset_config, dict) and f"{severity}_coverage_rate" in dataset_config:
        return float(dataset_config[f"{severity}_coverage_rate"])

    cross_name = "adj_vs_daily" if dataset == "adj_factor" else "basic_vs_daily"
    cross_table = strategy.get("data_quality", {}).get("cross_table", {})
    cross_config = cross_table.get(cross_name, {}) if isinstance(cross_table, dict) else {}
    if isinstance(cross_config, dict) and f"{severity}_coverage_rate" in cross_config:
        return float(cross_config[f"{severity}_coverage_rate"])
    return default
