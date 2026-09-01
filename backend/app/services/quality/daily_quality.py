import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import (
    DataQualityDaily,
    SectorFactorDaily,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockStateDaily,
)
from app.repositories.upsert import upsert_rows
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
) -> None:
    issue_codes: dict[str, Any] = {
        "missing_codes": result.missing_codes,
        "extra_codes": result.extra_codes,
    }
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
    upsert_rows(db, DataQualityDaily, rows, ["trade_date", "dataset"])


def record_cross_table_quality(
    db: Session,
    trade_date: date,
    *,
    job_id: uuid.UUID | None = None,
) -> dict[str, int]:
    counts = {
        "stock_daily": _count_date(db, StockDaily, StockDaily.trade_date, trade_date),
        "stock_adj_factor": _count_date(db, StockAdjFactor, StockAdjFactor.trade_date, trade_date),
        "stock_daily_basic": _count_date(
            db, StockDailyBasic, StockDailyBasic.trade_date, trade_date
        ),
        "stock_factor_daily": _count_date(
            db, StockFactorDaily, StockFactorDaily.trade_date, trade_date
        ),
        "stock_state_daily": _count_date(
            db, StockStateDaily, StockStateDaily.trade_date, trade_date
        ),
        "sector_factor_daily": _count_date(
            db, SectorFactorDaily, SectorFactorDaily.trade_date, trade_date
        ),
    }
    expected = expected_stock_codes(db, trade_date)
    _persist_simple(
        db,
        trade_date,
        "stock_daily_vs_expected",
        len(expected),
        counts["stock_daily"],
        job_id,
    )
    _persist_simple(
        db,
        trade_date,
        "adj_vs_daily",
        counts["stock_daily"],
        counts["stock_adj_factor"],
        job_id,
    )
    _persist_simple(
        db,
        trade_date,
        "basic_vs_daily",
        counts["stock_daily"],
        counts["stock_daily_basic"],
        job_id,
    )
    _persist_simple(
        db,
        trade_date,
        "factor_vs_daily",
        counts["stock_daily"],
        counts["stock_factor_daily"],
        job_id,
    )
    _persist_simple(
        db,
        trade_date,
        "state_vs_factor",
        counts["stock_factor_daily"],
        counts["stock_state_daily"],
        job_id,
    )
    return counts


def _persist_simple(
    db: Session,
    trade_date: date,
    dataset: str,
    expected_rows: int,
    actual_rows: int,
    job_id: uuid.UUID | None,
) -> None:
    if expected_rows <= 0:
        coverage_rate = None
        status = "WARNING"
        warning_count = 1
        error_count = 0
    else:
        coverage_rate = min(actual_rows / expected_rows, 1.0)
        status = "PASS" if actual_rows >= expected_rows else "WARNING"
        warning_count = 0 if status == "PASS" else 1
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
                "issue_codes": {},
                "job_id": job_id,
            }
        ],
        ["trade_date", "dataset"],
    )


def _count_date(db: Session, model: type, column: Any, trade_date: date) -> int:
    return int(
        db.execute(select(func.count()).select_from(model).where(column == trade_date)).scalar_one()
    )
