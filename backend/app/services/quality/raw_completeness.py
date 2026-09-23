import uuid
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.market_data import (
    DataQualityDaily,
    IndexDaily,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    StockLimitDaily,
    StockStDaily,
    StockSuspendDaily,
    TradeCalendar,
)
from app.services.quality.daily_quality import (
    CoverageResult,
    check_daily_coverage,
    expected_stock_daily_codes,
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
    invalid_count: int = 0
    invalid_codes: list[str] = field(default_factory=list)

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
    stock_st: RawDatasetCompleteness | None = None
    suspend_d: RawDatasetCompleteness | None = None
    stk_limit: RawDatasetCompleteness | None = None

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
    def stock_st_status(self) -> str:
        return self.stock_st.status if self.stock_st else "NOT_CHECKED"

    @property
    def suspend_d_status(self) -> str:
        return self.suspend_d.status if self.suspend_d else "NOT_CHECKED"

    @property
    def stk_limit_status(self) -> str:
        return self.stk_limit.status if self.stk_limit else "NOT_CHECKED"

    @property
    def is_complete(self) -> bool:
        return (
            self.stock_daily.is_acceptable
            and self.adj_factor.is_acceptable
            and self.daily_basic.is_acceptable
            and self.index_daily.status == "PASS"
            and (self.stock_st is None or self.stock_st.status == "PASS")
            and (self.suspend_d is None or self.suspend_d.status == "PASS")
            and (self.stk_limit is None or self.stk_limit.is_acceptable)
        )

    @property
    def overall_status(self) -> str:
        datasets = [
            self.stock_daily,
            self.adj_factor,
            self.daily_basic,
            self.index_daily,
            *[dataset for dataset in [self.stock_st, self.suspend_d, self.stk_limit] if dataset],
        ]
        if any(dataset.status == "ERROR" for dataset in datasets):
            return "ERROR"
        if any(dataset.status == "WARNING" for dataset in datasets):
            return "WARNING"
        return "PASS"

    def dataset(self, name: str) -> RawDatasetCompleteness:
        return {
            "stock_daily": self.stock_daily,
            "adj_factor": self.adj_factor,
            "daily_basic": self.daily_basic,
            "index_daily": self.index_daily,
            "stock_st": self.stock_st,
            "suspend_d": self.suspend_d,
            "stk_limit": self.stk_limit,
        }[name]

    def as_metadata(self) -> dict[str, object]:
        return {
            "stock_daily_status": self.stock_daily_status,
            "adj_factor_status": self.adj_factor_status,
            "daily_basic_status": self.daily_basic_status,
            "index_daily_status": self.index_daily_status,
            "stock_st_status": self.stock_st_status,
            "suspend_d_status": self.suspend_d_status,
            "stk_limit_status": self.stk_limit_status,
            "current_day_datasets": {
                "stock_daily": self.stock_daily_status,
                "adj_factor": self.adj_factor_status,
                "daily_basic": self.daily_basic_status,
                "index_daily": self.index_daily_status,
                "stock_st": self.stock_st_status,
                "suspend_d": self.suspend_d_status,
                "stk_limit": self.stk_limit_status,
            },
            "current_day_status": self.overall_status,
            "current_day_invalid_counts": {
                "stock_daily": self.stock_daily.invalid_count,
                "adj_factor": self.adj_factor.invalid_count,
                "daily_basic": self.daily_basic.invalid_count,
                "index_daily": self.index_daily.invalid_count,
                "stock_st": self.stock_st.invalid_count if self.stock_st else 0,
                "suspend_d": self.suspend_d.invalid_count if self.suspend_d else 0,
                "stk_limit": self.stk_limit.invalid_count if self.stk_limit else 0,
            },
            "error_dataset_count": sum(
                1
                for dataset in [
                    self.stock_daily,
                    self.adj_factor,
                    self.daily_basic,
                    self.index_daily,
                    *[
                        dataset
                        for dataset in [self.stock_st, self.suspend_d, self.stk_limit]
                        if dataset
                    ],
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
    expected_daily_codes = expected_stock_daily_codes(db, trade_date)
    adj_factor_codes, invalid_adj_factor_codes = _valid_codes_for_date(
        db,
        StockAdjFactor,
        StockAdjFactor.trade_date,
        trade_date,
        positive_columns=[StockAdjFactor.adj_factor],
    )
    daily_basic_codes, invalid_daily_basic_codes = _valid_codes_for_date(
        db,
        StockDailyBasic,
        StockDailyBasic.trade_date,
        trade_date,
        required_columns=[
            StockDailyBasic.close,
            StockDailyBasic.total_mv,
            StockDailyBasic.circ_mv,
        ],
    )
    index_daily_codes, invalid_index_daily_codes = _valid_codes_for_date(
        db,
        IndexDaily,
        IndexDaily.trade_date,
        trade_date,
        positive_columns=[IndexDaily.close, IndexDaily.pre_close],
    )

    stock_daily = _coverage_dataset(
        db,
        trade_date,
        "stock_daily",
        expected_daily_codes,
        stock_daily_codes,
        warning_coverage_rate=_daily_threshold(strategy, "warning", 0.98),
        error_coverage_rate=_daily_threshold(strategy, "error", 0.95),
        job_id=job_id,
        persist=persist,
        preserve_existing_detail_counts=True,
        preserve_existing_issue_details=True,
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
        invalid_codes=invalid_adj_factor_codes,
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
        invalid_codes=invalid_daily_basic_codes,
    )
    index_daily = _index_daily_dataset(
        db,
        trade_date,
        _benchmark_indices(strategy),
        index_daily_codes,
        invalid_codes=invalid_index_daily_codes,
        job_id=job_id,
        persist=persist,
    )
    stock_st = _event_quality_dataset(
        db,
        trade_date,
        "stock_st",
        StockStDaily,
        job_id=job_id,
        persist=persist,
    )
    suspend_d = _event_quality_dataset(
        db,
        trade_date,
        "suspend_d",
        StockSuspendDaily,
        job_id=job_id,
        persist=persist,
    )
    valid_limit_codes, invalid_limit_codes = _valid_codes_for_date(
        db,
        StockLimitDaily,
        StockLimitDaily.trade_date,
        trade_date,
        positive_columns=[StockLimitDaily.up_limit, StockLimitDaily.down_limit],
    )
    stk_limit = _coverage_dataset(
        db,
        trade_date,
        "stk_limit",
        expected_daily_codes,
        valid_limit_codes,
        warning_coverage_rate=_raw_threshold(strategy, "stk_limit", "warning", 0.98),
        error_coverage_rate=_raw_threshold(strategy, "stk_limit", "error", 0.95),
        job_id=job_id,
        persist=persist,
        invalid_codes=invalid_limit_codes,
        preserve_existing_detail_counts=True,
        preserve_existing_issue_details=True,
        source_warnings=_quality_source_warnings(db, trade_date, "stk_limit"),
    )
    return RawCompletenessResult(
        trade_date=trade_date,
        stock_daily=stock_daily,
        adj_factor=adj_factor,
        daily_basic=daily_basic,
        index_daily=index_daily,
        stock_st=stock_st,
        suspend_d=suspend_d,
        stk_limit=stk_limit,
    )


def _event_quality_dataset(
    db: Session,
    trade_date: date,
    dataset: str,
    model: type,
    *,
    job_id: uuid.UUID | None,
    persist: bool,
) -> RawDatasetCompleteness:
    quality = db.execute(
        select(DataQualityDaily).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == dataset,
        )
    ).scalar_one_or_none()
    actual_rows = int(
        db.execute(
            select(func.count()).select_from(model).where(model.trade_date == trade_date)
        ).scalar_one()
    )
    status = quality.status if quality is not None else "ERROR"
    result = RawDatasetCompleteness(
        dataset=dataset,
        status=status,
        expected_rows=actual_rows,
        actual_rows=actual_rows,
        coverage_rate=1.0 if quality is not None else None,
        missing_codes=[],
        extra_codes=[],
    )
    if persist and quality is None:
        persist_coverage_result(
            db,
            CoverageResult(
                trade_date=trade_date,
                dataset=dataset,
                expected_rows=actual_rows,
                actual_rows=actual_rows,
                coverage_rate=None,
                missing_codes=[],
                extra_codes=[],
                status="ERROR",
                error_count=1,
            ),
            job_id=job_id,
            extra_issue_codes={"errors": ["SOURCE_SYNC_EVIDENCE_MISSING"]},
            preserve_existing_detail_counts=True,
        )
    return result


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
    invalid_codes: set[str] | None = None,
    preserve_existing_detail_counts: bool = False,
    preserve_existing_issue_details: bool = False,
    source_warnings: list[str] | None = None,
) -> RawDatasetCompleteness:
    invalid_codes = invalid_codes or set()
    result = check_daily_coverage(
        trade_date=trade_date,
        actual_codes=actual_codes,
        expected_codes=expected_codes,
        warning_coverage_rate=warning_coverage_rate,
        error_coverage_rate=error_coverage_rate,
        dataset=dataset,
    )
    if source_warnings and result.status == "PASS":
        result = replace(result, status="WARNING", warning_count=1)
    if persist:
        issue_codes = _invalid_issue_codes(invalid_codes)
        if source_warnings:
            issue_codes["source_warnings"] = source_warnings
        persist_coverage_result(
            db,
            result,
            job_id=job_id,
            extra_issue_codes=issue_codes,
            preserve_existing_detail_counts=preserve_existing_detail_counts,
            preserve_existing_issue_details=preserve_existing_issue_details,
        )
    return RawDatasetCompleteness(
        dataset=dataset,
        status=result.status,
        expected_rows=result.expected_rows,
        actual_rows=result.actual_rows,
        coverage_rate=result.coverage_rate,
        missing_codes=result.missing_codes,
        extra_codes=result.extra_codes,
        invalid_count=len(invalid_codes),
        invalid_codes=_top_invalid_codes(invalid_codes),
    )


def _quality_source_warnings(db: Session, trade_date: date, dataset: str) -> list[str]:
    issue_codes = db.execute(
        select(DataQualityDaily.issue_codes).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == dataset,
        )
    ).scalar_one_or_none()
    if not isinstance(issue_codes, dict):
        return []
    warnings = issue_codes.get("source_warnings", [])
    return [str(item) for item in warnings] if isinstance(warnings, list) else []


def _index_daily_dataset(
    db: Session,
    trade_date: date,
    expected_codes: set[str],
    actual_codes: set[str],
    invalid_codes: set[str] | None = None,
    *,
    job_id: uuid.UUID | None,
    persist: bool,
) -> RawDatasetCompleteness:
    invalid_codes = invalid_codes or set()
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
        persist_coverage_result(
            db,
            result,
            job_id=job_id,
            extra_issue_codes=_invalid_issue_codes(invalid_codes),
        )
    return RawDatasetCompleteness(
        dataset="index_daily",
        status=status,
        expected_rows=len(expected_codes),
        actual_rows=len(actual_codes),
        coverage_rate=coverage_rate,
        missing_codes=sorted(expected_codes - actual_codes),
        extra_codes=sorted(actual_codes - expected_codes),
        invalid_count=len(invalid_codes),
        invalid_codes=_top_invalid_codes(invalid_codes),
    )


def _codes_for_date(db: Session, model: type, column: Any, trade_date: date) -> set[str]:
    return set(
        db.execute(select(model.ts_code).where(column == trade_date))
        .scalars()
        .all()
    )


def _valid_codes_for_date(
    db: Session,
    model: type,
    column: Any,
    trade_date: date,
    *,
    required_columns: list[Any] | None = None,
    positive_columns: list[Any] | None = None,
) -> tuple[set[str], set[str]]:
    required_columns = required_columns or []
    positive_columns = positive_columns or []
    validity_checks = [field.is_not(None) for field in required_columns]
    validity_checks.extend(field.is_not(None) for field in positive_columns)
    validity_checks.extend(field > 0 for field in positive_columns)
    if not validity_checks:
        codes = _codes_for_date(db, model, column, trade_date)
        return codes, set()

    validity = and_(*validity_checks)
    valid_codes = set(
        db.execute(select(model.ts_code).where(column == trade_date, validity))
        .scalars()
        .all()
    )
    invalid_codes = set(
        db.execute(select(model.ts_code).where(column == trade_date, ~validity))
        .scalars()
        .all()
    )
    return valid_codes, invalid_codes


def _invalid_issue_codes(invalid_codes: set[str]) -> dict[str, Any]:
    if not invalid_codes:
        return {}
    return {
        "invalid_count": len(invalid_codes),
        "invalid_codes": _top_invalid_codes(invalid_codes),
    }


def _top_invalid_codes(invalid_codes: set[str]) -> list[str]:
    return sorted(invalid_codes)[:100]


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
