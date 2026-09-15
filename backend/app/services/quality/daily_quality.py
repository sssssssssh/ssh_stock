import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    DataQualityDaily,
    MarketDaily,
    SectorFactorDaily,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockStateDaily,
    StockSuspendDaily,
    TradeCalendar,
)
from app.repositories.upsert import upsert_rows
from app.services.calc_metadata import config_hash
from app.services.universe import is_stock_active_on


@dataclass(frozen=True)
class CoverageResult:
    trade_date: date
    dataset: str
    expected_rows: int
    actual_rows: int
    coverage_rate: float | None
    missing_codes: list[str]
    extra_codes: list[str]
    status: str
    warning_count: int = 0
    error_count: int = 0

    @property
    def missing_count(self) -> int:
        return len(self.missing_codes)


@dataclass(frozen=True)
class CrossTableQualityResult:
    trade_date: date
    counts: dict[str, int]
    results: dict[str, str]
    error_datasets: list[str]

    @property
    def has_error(self) -> bool:
        return bool(self.error_datasets)


@dataclass(frozen=True)
class CrossTableRangeResult:
    checked_days: int
    error_days: int
    error_dates: list[date]
    error_datasets: dict[str, list[str]]

    @property
    def has_error(self) -> bool:
        return bool(self.error_dates)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "cross_table_checked_days": self.checked_days,
            "cross_table_error_days": self.error_days,
            "cross_table_error_dates": [day.isoformat() for day in self.error_dates[:100]],
            "cross_table_error_datasets": {
                day: datasets
                for day, datasets in list(self.error_datasets.items())[:100]
            },
        }


class DataQualityError(RuntimeError):
    pass


def expected_stock_codes(db: Session, trade_date: date) -> set[str]:
    rows = db.execute(
        select(StockBasic.ts_code, StockBasic.list_date, StockBasic.delist_date)
    ).all()
    return {
        row.ts_code
        for row in rows
        if is_stock_active_on(row.list_date, row.delist_date, trade_date)
    }


def check_daily_coverage(
    *,
    trade_date: date,
    actual_codes: set[str],
    expected_codes: set[str],
    warning_coverage_rate: float = 0.98,
    error_coverage_rate: float = 0.95,
    dataset: str = "stock_daily",
) -> CoverageResult:
    # Current expected universe is listed and not delisted stocks only. Suspended
    # stocks are not excluded until Milestone 9 adds suspension data.
    if not expected_codes:
        return CoverageResult(
            trade_date=trade_date,
            dataset=dataset,
            expected_rows=0,
            actual_rows=len(actual_codes),
            coverage_rate=None,
            missing_codes=[],
            extra_codes=sorted(actual_codes),
            status="WARNING",
            warning_count=1,
        )

    missing_codes = sorted(expected_codes - actual_codes)
    extra_codes = sorted(actual_codes - expected_codes)
    coverage_rate = len(actual_codes & expected_codes) / len(expected_codes)
    if coverage_rate < error_coverage_rate:
        status = "ERROR"
        error_count = 1
        warning_count = 0
    elif coverage_rate < warning_coverage_rate:
        status = "WARNING"
        error_count = 0
        warning_count = 1
    else:
        status = "PASS"
        error_count = 0
        warning_count = 0

    return CoverageResult(
        trade_date=trade_date,
        dataset=dataset,
        expected_rows=len(expected_codes),
        actual_rows=len(actual_codes),
        coverage_rate=coverage_rate,
        missing_codes=missing_codes,
        extra_codes=extra_codes,
        status=status,
        warning_count=warning_count,
        error_count=error_count,
    )


def persist_coverage_result(
    db: Session,
    result: CoverageResult,
    *,
    duplicate_count: int = 0,
    null_count: int = 0,
    job_id: uuid.UUID | None = None,
    extra_issue_codes: dict[str, Any] | None = None,
    preserve_existing_detail_counts: bool = False,
) -> None:
    issue_codes: dict[str, Any] = {
        "missing_codes": result.missing_codes,
        "extra_codes": result.extra_codes,
    }
    if extra_issue_codes:
        issue_codes.update(extra_issue_codes)
    if result.expected_rows == 0:
        issue_codes["warnings"] = ["NO_EXPECTED_UNIVERSE"]
    rows = [
        {
            "trade_date": result.trade_date,
            "dataset": result.dataset,
            "expected_rows": result.expected_rows,
            "actual_rows": result.actual_rows,
            "coverage_rate": result.coverage_rate,
            "missing_count": result.missing_count,
            "duplicate_count": duplicate_count,
            "null_count": null_count,
            "warning_count": result.warning_count,
            "error_count": result.error_count,
            "status": result.status,
            "issue_codes": issue_codes,
            "job_id": job_id,
        }
    ]
    update_columns = None
    if preserve_existing_detail_counts:
        update_columns = [
            "expected_rows",
            "actual_rows",
            "coverage_rate",
            "missing_count",
            "warning_count",
            "error_count",
            "status",
            "issue_codes",
            "job_id",
        ]
    upsert_rows(
        db,
        DataQualityDaily,
        rows,
        ["trade_date", "dataset"],
        update_columns=update_columns,
    )


def record_cross_table_quality(
    db: Session,
    trade_date: date,
    *,
    job_id: uuid.UUID | None = None,
    strategy: dict[str, Any] | None = None,
) -> CrossTableQualityResult:
    settings = get_settings()
    strategy = strategy or settings.strategy
    hash_value = config_hash(strategy)
    algo_version = settings.algo_version
    counts = {
        "stock_daily": _count_date(db, StockDaily, StockDaily.trade_date, trade_date),
        "stock_adj_factor": _count_date(db, StockAdjFactor, StockAdjFactor.trade_date, trade_date),
        "stock_daily_basic": _count_date(
            db, StockDailyBasic, StockDailyBasic.trade_date, trade_date
        ),
        "stock_factor_daily": _count_date(
            db,
            StockFactorDaily,
            StockFactorDaily.trade_date,
            trade_date,
            StockFactorDaily.calc_version == "factor_v1",
            StockFactorDaily.config_hash == hash_value,
        ),
        "stock_state_daily": _count_date(
            db,
            StockStateDaily,
            StockStateDaily.trade_date,
            trade_date,
            StockStateDaily.algo_version == algo_version,
        ),
        "sector_factor_daily": _count_date(
            db,
            SectorFactorDaily,
            SectorFactorDaily.trade_date,
            trade_date,
            SectorFactorDaily.calc_version == "sector_v1",
            SectorFactorDaily.config_hash == hash_value,
        ),
        "market_daily": _count_date(
            db,
            MarketDaily,
            MarketDaily.trade_date,
            trade_date,
            MarketDaily.calc_version == "market_v1",
            MarketDaily.config_hash == hash_value,
        ),
    }
    expected = expected_stock_codes(db, trade_date) - _suspended_codes(db, trade_date)
    results = {}
    results["stock_daily_vs_expected"] = _persist_simple(
        db,
        trade_date,
        "stock_daily_vs_expected",
        len(expected),
        counts["stock_daily"],
        job_id,
        warning_coverage_rate=_daily_threshold(strategy, "warning", 0.98),
        error_coverage_rate=_daily_threshold(strategy, "error", 0.95),
    )
    results["adj_vs_daily"] = _persist_simple(
        db,
        trade_date,
        "adj_vs_daily",
        counts["stock_daily"],
        counts["stock_adj_factor"],
        job_id,
        warning_coverage_rate=_cross_table_threshold(strategy, "adj_vs_daily", "warning", 0.98),
        error_coverage_rate=_cross_table_threshold(strategy, "adj_vs_daily", "error", 0.95),
    )
    results["basic_vs_daily"] = _persist_simple(
        db,
        trade_date,
        "basic_vs_daily",
        counts["stock_daily"],
        counts["stock_daily_basic"],
        job_id,
        warning_coverage_rate=_cross_table_threshold(strategy, "basic_vs_daily", "warning", 0.98),
        error_coverage_rate=_cross_table_threshold(strategy, "basic_vs_daily", "error", 0.95),
    )
    results["factor_vs_daily"] = _persist_simple(
        db,
        trade_date,
        "factor_vs_daily",
        counts["stock_daily"],
        counts["stock_factor_daily"],
        job_id,
        warning_coverage_rate=_cross_table_threshold(strategy, "factor_vs_daily", "warning", 0.98),
        error_coverage_rate=_cross_table_threshold(strategy, "factor_vs_daily", "error", 0.90),
    )
    results["state_vs_factor"] = _persist_simple(
        db,
        trade_date,
        "state_vs_factor",
        counts["stock_factor_daily"],
        counts["stock_state_daily"],
        job_id,
        warning_coverage_rate=_cross_table_threshold(
            strategy, "state_vs_factor", "warning", 0.98
        ),
        error_coverage_rate=_cross_table_threshold(strategy, "state_vs_factor", "error", 0.90),
    )
    return CrossTableQualityResult(
        trade_date=trade_date,
        counts=counts,
        results=results,
        error_datasets=[
            dataset
            for dataset, status in results.items()
            if status == "ERROR"
            and dataset
            in {
                "stock_daily_vs_expected",
                "adj_vs_daily",
                "basic_vs_daily",
                "factor_vs_daily",
                "state_vs_factor",
            }
        ],
    )


def validate_cross_table_range(
    db: Session,
    start: date,
    end: date,
    *,
    job_id: uuid.UUID | None = None,
    strategy: dict[str, Any] | None = None,
) -> CrossTableRangeResult:
    error_dates: list[date] = []
    error_datasets: dict[str, list[str]] = {}
    checked_days = 0
    for trade_date in _open_trade_dates(db, start, end):
        checked_days += 1
        quality = record_cross_table_quality(
            db,
            trade_date,
            job_id=job_id,
            strategy=strategy,
        )
        if quality.has_error:
            error_dates.append(trade_date)
            error_datasets[trade_date.isoformat()] = quality.error_datasets
    db.commit()
    return CrossTableRangeResult(
        checked_days=checked_days,
        error_days=len(error_dates),
        error_dates=error_dates,
        error_datasets=error_datasets,
    )


def cross_table_coverage_status(
    strategy: dict[str, Any] | None,
    dataset: str,
    expected_rows: int,
    actual_rows: int,
    *,
    warning_default: float = 0.98,
    error_default: float = 0.90,
) -> str:
    if expected_rows <= 0:
        return "WARNING"
    coverage_rate = min(actual_rows / expected_rows, 1.0)
    warning_rate = _cross_table_threshold(strategy, dataset, "warning", warning_default)
    error_rate = _cross_table_threshold(strategy, dataset, "error", error_default)
    if coverage_rate < error_rate:
        return "ERROR"
    if coverage_rate < warning_rate:
        return "WARNING"
    return "PASS"


def _persist_simple(
    db: Session,
    trade_date: date,
    dataset: str,
    expected_rows: int,
    actual_rows: int,
    job_id: uuid.UUID | None,
    *,
    warning_coverage_rate: float,
    error_coverage_rate: float,
) -> str:
    if expected_rows <= 0:
        coverage_rate = None
        status = "WARNING"
        warning_count = 1
        error_count = 0
    else:
        coverage_rate = min(actual_rows / expected_rows, 1.0)
        status = cross_table_coverage_status(
            None,
            dataset,
            expected_rows,
            actual_rows,
            warning_default=warning_coverage_rate,
            error_default=error_coverage_rate,
        )
        if status == "ERROR":
            warning_count = 0
            error_count = 1
        elif status == "WARNING":
            warning_count = 1
            error_count = 0
        else:
            warning_count = 0
            error_count = 0
    upsert_rows(
        db,
        DataQualityDaily,
        [
            {
                "trade_date": trade_date,
                "dataset": dataset,
                "expected_rows": expected_rows,
                "actual_rows": actual_rows,
                "coverage_rate": coverage_rate,
                "missing_count": max(expected_rows - actual_rows, 0),
                "duplicate_count": 0,
                "null_count": 0,
                "warning_count": warning_count,
                "error_count": error_count,
                "status": status,
                "issue_codes": {
                    "coverage_rate": coverage_rate,
                    "warning_coverage_rate": warning_coverage_rate,
                    "error_coverage_rate": error_coverage_rate,
                },
                "job_id": job_id,
            }
        ],
        ["trade_date", "dataset"],
    )
    return status


def _count_date(
    db: Session,
    model: type,
    column: Any,
    trade_date: date,
    *criteria: Any,
) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(model)
            .where(column == trade_date, *criteria)
        ).scalar_one()
    )


def _suspended_codes(db: Session, trade_date: date) -> set[str]:
    return set(
        db.execute(
            select(StockSuspendDaily.ts_code).where(
                StockSuspendDaily.trade_date == trade_date,
                StockSuspendDaily.suspend_type == "S",
            )
        )
        .scalars()
        .all()
    )


def _open_trade_dates(db: Session, start: date, end: date) -> list[date]:
    return list(
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


def _daily_threshold(
    strategy: dict[str, Any] | None,
    severity: str,
    default: float,
) -> float:
    daily = (strategy or {}).get("data_quality", {}).get("daily", {})
    value = daily.get(f"{severity}_coverage_rate", default) if isinstance(daily, dict) else default
    return float(value)


def _cross_table_threshold(
    strategy: dict[str, Any] | None,
    dataset: str,
    severity: str,
    default: float,
) -> float:
    cross_table = (strategy or {}).get("data_quality", {}).get("cross_table", {})
    dataset_config = cross_table.get(dataset, {}) if isinstance(cross_table, dict) else {}
    value = (
        dataset_config.get(f"{severity}_coverage_rate", default)
        if isinstance(dataset_config, dict)
        else default
    )
    return float(value)
