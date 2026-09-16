import uuid
from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    IndexDaily,
    Sector,
    SectorMember,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    StockLimitDaily,
    StockStDaily,
    StockSuspendDaily,
    TradeCalendar,
)
from app.providers.base import MarketDataProvider
from app.repositories.upsert import upsert_rows
from app.services.dirty import (
    changed_trade_dates,
    reconcile_daily_snapshot,
    record_dirty_range,
)
from app.services.ingestion.normalizers import (
    current_sector_members_missing_in_date,
    normalize_adj_factor,
    normalize_daily_basic,
    normalize_index_daily,
    normalize_sector_members,
    normalize_sectors,
    normalize_stock_basic,
    normalize_stock_daily,
    normalize_stock_limit,
    normalize_stock_st,
    normalize_stock_suspend,
    normalize_trade_calendar,
)
from app.services.quality.daily_quality import (
    CoverageResult,
    check_daily_coverage,
    expected_stock_daily_codes,
    persist_coverage_result,
)
from app.services.quality.raw_checks import check_raw_daily
from app.services.quality.raw_completeness import validate_trade_calendar_rows

DAILY_VALUE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]
ADJ_FACTOR_VALUE_COLUMNS = ["adj_factor"]
DAILY_BASIC_VALUE_COLUMNS = [
    "close",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
]
INDEX_DAILY_VALUE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "pct_chg",
    "vol",
    "amount",
]
ST_VALUE_COLUMNS = ["name", "st_type", "st_type_name"]
SUSPEND_VALUE_COLUMNS = ["suspend_timing"]
LIMIT_VALUE_COLUMNS = ["pre_close", "up_limit", "down_limit", "asset_type", "exchange"]


class IngestionService:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.provider = provider
        self.settings = get_settings()

    def sync_trade_calendar(self, start: date, end: date) -> int:
        try:
            df = self.provider.get_trade_calendar(start, end)
            rows = normalize_trade_calendar(df)
            validate_trade_calendar_rows(start, end, rows)
            count = upsert_rows(self.db, TradeCalendar, rows, ["cal_date"])
            self.db.commit()
            logger.info("synced trade_calendar rows={}", count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_stock_basic(self) -> int:
        try:
            df = self.provider.get_stock_basic()
            rows = normalize_stock_basic(df)
            count = upsert_rows(self.db, StockBasic, rows, ["ts_code"])
            self.db.commit()
            logger.info("synced stock_basic rows={}", count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_daily(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        try:
            df = self.provider.get_daily(trade_date)
            issues = check_raw_daily(df, min_rows=0)
            fatal = [issue for issue in issues if issue.severity == "ERROR"]
            rows = normalize_stock_daily(df)
            expected_codes = expected_stock_daily_codes(self.db, trade_date)
            actual_codes = {row["ts_code"] for row in rows}
            quality = check_daily_coverage(
                trade_date=trade_date,
                actual_codes=actual_codes,
                expected_codes=expected_codes,
                warning_coverage_rate=_quality_threshold(self.settings.strategy, "warning"),
                error_coverage_rate=_quality_threshold(self.settings.strategy, "error"),
                dataset="stock_daily",
            )
            duplicate_count = (
                int(df.duplicated(subset=["trade_date", "ts_code"]).sum()) if not df.empty else 0
            )
            null_count = sum(
                1
                for row in rows
                for column in DAILY_VALUE_COLUMNS
                if row.get(column) is None
            )
            if fatal:
                quality = replace(
                    quality,
                    status="ERROR",
                    warning_count=0,
                    error_count=max(1, len(fatal)),
                )
            persist_coverage_result(
                self.db,
                quality,
                duplicate_count=duplicate_count,
                null_count=null_count,
                job_id=job_id,
                extra_issue_codes={"raw_issues": [issue.code for issue in fatal]},
            )
            if fatal:
                self.db.commit()
                raise ValueError(
                    f"daily quality check failed: {[issue.code for issue in fatal]}"
                )
            if quality.status == "ERROR":
                self.db.commit()
                raise ValueError(
                    "daily coverage check failed: "
                    f"actual={quality.actual_rows} expected={quality.expected_rows} "
                    f"coverage={quality.coverage_rate:.4f}"
                )
            dirty_dates = changed_trade_dates(
                self.db,
                StockDaily,
                rows,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=DAILY_VALUE_COLUMNS,
                preserve_existing_on_null_columns=DAILY_VALUE_COLUMNS,
            )
            record_dirty_range(
                self.db,
                dataset="stock_daily",
                dirty_dates=dirty_dates,
                reason="stock_daily source values changed",
                source_job_id=job_id,
            )
            count = upsert_rows(
                self.db,
                StockDaily,
                rows,
                ["trade_date", "ts_code"],
                preserve_existing_on_null_columns=DAILY_VALUE_COLUMNS,
            )
            self.db.commit()
            logger.info("synced stock_daily trade_date={} rows={}", trade_date, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_adj_factor(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        try:
            df = self.provider.get_adj_factor(trade_date)
            rows = normalize_adj_factor(df)
            dirty_dates = changed_trade_dates(
                self.db,
                StockAdjFactor,
                rows,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=ADJ_FACTOR_VALUE_COLUMNS,
                preserve_existing_on_null_columns=ADJ_FACTOR_VALUE_COLUMNS,
            )
            record_dirty_range(
                self.db,
                dataset="stock_adj_factor",
                dirty_dates=dirty_dates,
                reason="stock_adj_factor source values changed",
                source_job_id=job_id,
            )
            count = upsert_rows(
                self.db,
                StockAdjFactor,
                rows,
                ["trade_date", "ts_code"],
                preserve_existing_on_null_columns=ADJ_FACTOR_VALUE_COLUMNS,
            )
            self.db.commit()
            logger.info("synced stock_adj_factor trade_date={} rows={}", trade_date, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_daily_basic(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        try:
            df = self.provider.get_daily_basic(trade_date)
            rows = normalize_daily_basic(df)
            dirty_dates = changed_trade_dates(
                self.db,
                StockDailyBasic,
                rows,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=DAILY_BASIC_VALUE_COLUMNS,
                preserve_existing_on_null_columns=DAILY_BASIC_VALUE_COLUMNS,
            )
            record_dirty_range(
                self.db,
                dataset="stock_daily_basic",
                dirty_dates=dirty_dates,
                reason="stock_daily_basic source values changed",
                source_job_id=job_id,
            )
            count = upsert_rows(
                self.db,
                StockDailyBasic,
                rows,
                ["trade_date", "ts_code"],
                preserve_existing_on_null_columns=DAILY_BASIC_VALUE_COLUMNS,
            )
            self.db.commit()
            logger.info("synced stock_daily_basic trade_date={} rows={}", trade_date, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_index_daily(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        try:
            benchmark = self.settings.strategy.get("benchmark", {})
            codes = benchmark.get("market_indices", ["000300.SH"])
            df = self.provider.get_index_daily(trade_date, codes)
            rows = normalize_index_daily(df)
            dirty_dates = changed_trade_dates(
                self.db,
                IndexDaily,
                rows,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=INDEX_DAILY_VALUE_COLUMNS,
                preserve_existing_on_null_columns=INDEX_DAILY_VALUE_COLUMNS,
            )
            record_dirty_range(
                self.db,
                dataset="index_daily",
                dirty_dates=dirty_dates,
                reason="index_daily source values changed",
                source_job_id=job_id,
            )
            count = upsert_rows(
                self.db,
                IndexDaily,
                rows,
                ["trade_date", "ts_code"],
                preserve_existing_on_null_columns=INDEX_DAILY_VALUE_COLUMNS,
            )
            self.db.commit()
            logger.info("synced index_daily trade_date={} rows={}", trade_date, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_stock_st(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        try:
            df = self.provider.get_stock_st(trade_date)
            rows = normalize_stock_st(df)
            issues = _raw_frame_issues(
                df,
                rows,
                key_columns=["trade_date", "ts_code"],
            )
            _persist_event_quality(
                self.db,
                trade_date,
                "stock_st",
                rows,
                issues=issues,
                job_id=job_id,
            )
            if issues:
                self.db.commit()
                raise ValueError(f"stock_st quality check failed: {issues}")
            dirty_dates = reconcile_daily_snapshot(
                self.db,
                StockStDaily,
                rows,
                trade_date=trade_date,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=ST_VALUE_COLUMNS,
            )
            count = upsert_rows(
                self.db,
                StockStDaily,
                rows,
                ["trade_date", "ts_code"],
                update_columns=ST_VALUE_COLUMNS + ["updated_at"],
            )
            record_dirty_range(
                self.db,
                dataset="stock_st_daily",
                dirty_dates=dirty_dates,
                reason="stock_st source values changed",
                source_job_id=job_id,
            )
            self.db.commit()
            logger.info("synced stock_st trade_date={} rows={}", trade_date, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_suspend_daily(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        try:
            df = self.provider.get_suspend_daily(trade_date)
            rows = normalize_stock_suspend(df)
            issues = _raw_frame_issues(
                df,
                rows,
                key_columns=["trade_date", "ts_code", "suspend_type"],
            )
            invalid_types = sorted(
                {
                    str(row["suspend_type"])
                    for row in rows
                    if row["suspend_type"] not in {"S", "R"}
                }
            )
            if invalid_types:
                issues.append(f"INVALID_SUSPEND_TYPE:{','.join(invalid_types)}")
            _persist_event_quality(
                self.db,
                trade_date,
                "suspend_d",
                rows,
                issues=issues,
                job_id=job_id,
            )
            if issues:
                self.db.commit()
                raise ValueError(f"suspend_d quality check failed: {issues}")
            dirty_dates = reconcile_daily_snapshot(
                self.db,
                StockSuspendDaily,
                rows,
                trade_date=trade_date,
                conflict_columns=["trade_date", "ts_code", "suspend_type"],
                compare_columns=SUSPEND_VALUE_COLUMNS,
            )
            count = upsert_rows(
                self.db,
                StockSuspendDaily,
                rows,
                ["trade_date", "ts_code", "suspend_type"],
                update_columns=SUSPEND_VALUE_COLUMNS + ["updated_at"],
            )
            record_dirty_range(
                self.db,
                dataset="stock_suspend_daily",
                dirty_dates=dirty_dates,
                reason="suspend_d source values changed",
                source_job_id=job_id,
            )
            self.db.commit()
            logger.info("synced suspend_d trade_date={} rows={}", trade_date, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_stock_limit(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        try:
            df = self.provider.get_stock_limit(trade_date)
            rows = normalize_stock_limit(df)
            issues = _raw_frame_issues(
                df,
                rows,
                key_columns=["trade_date", "ts_code"],
            )
            expected_codes = expected_stock_daily_codes(self.db, trade_date)
            valid_codes = {
                str(row["ts_code"])
                for row in rows
                if row["up_limit"] is not None
                and row["up_limit"] > 0
                and row["down_limit"] is not None
                and row["down_limit"] > 0
            }
            quality = check_daily_coverage(
                trade_date=trade_date,
                actual_codes=valid_codes,
                expected_codes=expected_codes,
                warning_coverage_rate=_raw_quality_threshold(
                    self.settings.strategy, "stk_limit", "warning", 0.98
                ),
                error_coverage_rate=_raw_quality_threshold(
                    self.settings.strategy, "stk_limit", "error", 0.95
                ),
                dataset="stk_limit",
            )
            if issues:
                quality = replace(
                    quality,
                    status="ERROR",
                    warning_count=0,
                    error_count=max(1, quality.error_count),
                )
            persist_coverage_result(
                self.db,
                quality,
                duplicate_count=_duplicate_count(
                    rows, ["trade_date", "ts_code"]
                ),
                null_count=sum(
                    1
                    for row in rows
                    if row["up_limit"] is None or row["down_limit"] is None
                ),
                job_id=job_id,
                extra_issue_codes={"raw_issues": issues},
            )
            if quality.status == "ERROR":
                self.db.commit()
                raise ValueError(
                    "stk_limit quality check failed: "
                    f"coverage={quality.coverage_rate} issues={issues}"
                )
            dirty_dates = reconcile_daily_snapshot(
                self.db,
                StockLimitDaily,
                rows,
                trade_date=trade_date,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=LIMIT_VALUE_COLUMNS,
            )
            count = upsert_rows(
                self.db,
                StockLimitDaily,
                rows,
                ["trade_date", "ts_code"],
                update_columns=LIMIT_VALUE_COLUMNS + ["updated_at"],
            )
            record_dirty_range(
                self.db,
                dataset="stock_limit_daily",
                dirty_dates=dirty_dates,
                reason="stk_limit source values changed",
                source_job_id=job_id,
            )
            self.db.commit()
            logger.info("synced stk_limit trade_date={} rows={}", trade_date, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_index_daily_range(
        self,
        start: date,
        end: date,
        job_id: uuid.UUID | None = None,
    ) -> int:
        try:
            benchmark = self.settings.strategy.get("benchmark", {})
            codes = benchmark.get("market_indices", ["000300.SH"])
            frames = [
                self.provider.get_index_daily_range(code, chunk_start, chunk_end)
                for code in codes
                for chunk_start, chunk_end in _index_range_chunks(start, end)
            ]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            rows = normalize_index_daily(df)
            dirty_dates = changed_trade_dates(
                self.db,
                IndexDaily,
                rows,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=INDEX_DAILY_VALUE_COLUMNS,
                preserve_existing_on_null_columns=INDEX_DAILY_VALUE_COLUMNS,
            )
            record_dirty_range(
                self.db,
                dataset="index_daily",
                dirty_dates=dirty_dates,
                reason="index_daily source values changed",
                source_job_id=job_id,
            )
            count = upsert_rows(
                self.db,
                IndexDaily,
                rows,
                ["trade_date", "ts_code"],
                preserve_existing_on_null_columns=INDEX_DAILY_VALUE_COLUMNS,
            )
            self.db.commit()
            logger.info("synced index_daily range start={} end={} rows={}", start, end, count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_sector_metadata(self) -> int:
        try:
            df = self.provider.get_sector_classification()
            rows = normalize_sectors(df, source="SW")
            if not rows:
                raise ValueError("sector metadata returned no valid rows")
            count = upsert_rows(self.db, Sector, rows, ["source", "source_code"])
            source_codes = {str(row["source_code"]) for row in rows}
            self.db.execute(
                update(Sector)
                .where(
                    Sector.source == "SW",
                    Sector.source_code.not_in(source_codes),
                )
                .values(is_active=False)
            )
            self.db.commit()
            logger.info("synced sector metadata rows={}", count)
            return count
        except Exception:
            self.db.rollback()
            raise

    def sync_sector_members(self) -> int:
        try:
            sector_rows = self.db.query(Sector).filter(Sector.source == "SW").all()
            code_to_id = {row.source_code: row.sector_id for row in sector_rows}
            df = self.provider.get_sector_members()
            missing_current_dates = current_sector_members_missing_in_date(df)
            if missing_current_dates:
                raise ValueError(
                    "sector member PIT_INVALID: current members missing in_date: "
                    f"{missing_current_dates[:20]}"
                )
            rows = _deduplicate_sector_member_rows(
                normalize_sector_members(df, code_to_id)
            )
            if not rows:
                raise ValueError("sector members returned no valid rows")
            natural_keys = {
                (row["sector_id"], row["ts_code"], row["valid_from"])
                for row in rows
            }
            existing_members = list(
                self.db.execute(
                    select(SectorMember)
                    .join(Sector, SectorMember.sector_id == Sector.sector_id)
                    .where(Sector.source == "SW")
                )
                .scalars()
                .all()
            )
            for member in existing_members:
                key = (member.sector_id, member.ts_code, member.valid_from)
                if key not in natural_keys:
                    self.db.delete(member)
            count = upsert_rows(
                self.db,
                SectorMember,
                rows,
                ["sector_id", "ts_code", "valid_from"],
            )
            self.db.commit()
            logger.info("synced sector members rows={}", count)
            return count
        except Exception:
            self.db.rollback()
            raise


def _quality_threshold(strategy: dict, severity: str) -> float:
    daily = strategy.get("data_quality", {}).get("daily", {})
    key = f"{severity}_coverage_rate"
    default = 0.98 if severity == "warning" else 0.95
    return float(daily.get(key, default))


def _raw_quality_threshold(
    strategy: dict,
    dataset: str,
    severity: str,
    default: float,
) -> float:
    return float(
        strategy.get("raw_quality", {})
        .get(dataset, {})
        .get(f"{severity}_coverage_rate", default)
    )


def _raw_frame_issues(
    df: pd.DataFrame,
    rows: list[dict[str, object]],
    *,
    key_columns: list[str],
) -> list[str]:
    issues: list[str] = []
    if len(rows) != len(df.index):
        issues.append("INVALID_REQUIRED_FIELDS")
    if _duplicate_count(rows, key_columns):
        issues.append("DUPLICATE_NATURAL_KEY")
    if df.attrs.get("provider_warning") == "POSSIBLE_TRUNCATION":
        issues.append("POSSIBLE_TRUNCATION")
    return issues


def _duplicate_count(rows: list[dict[str, object]], key_columns: list[str]) -> int:
    keys = [tuple(row.get(column) for column in key_columns) for row in rows]
    return len(keys) - len(set(keys))


def _deduplicate_sector_member_rows(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    deduplicated: dict[tuple[object, object, object], dict[str, object]] = {}
    for row in rows:
        key = (row["sector_id"], row["ts_code"], row["valid_from"])
        existing = deduplicated.get(key)
        if existing is None or (
            existing.get("valid_to") is not None and row.get("valid_to") is None
        ):
            deduplicated[key] = row
    return list(deduplicated.values())


def _index_range_chunks(
    start: date,
    end: date,
    *,
    chunk_days: int = 730,
) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(end, current + timedelta(days=chunk_days - 1))
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _persist_event_quality(
    db: Session,
    trade_date: date,
    dataset: str,
    rows: list[dict[str, object]],
    *,
    issues: list[str],
    job_id: uuid.UUID | None,
) -> None:
    duplicate_count = _duplicate_count(
        rows,
        ["trade_date", "ts_code", "suspend_type"]
        if dataset == "suspend_d"
        else ["trade_date", "ts_code"],
    )
    status = "ERROR" if issues else "PASS"
    result = CoverageResult(
        trade_date=trade_date,
        dataset=dataset,
        expected_rows=len(rows),
        actual_rows=len(rows),
        coverage_rate=1.0,
        missing_codes=[],
        extra_codes=[],
        status=status,
        error_count=1 if issues else 0,
    )
    persist_coverage_result(
        db,
        result,
        duplicate_count=duplicate_count,
        job_id=job_id,
        extra_issue_codes={"raw_issues": issues},
    )
