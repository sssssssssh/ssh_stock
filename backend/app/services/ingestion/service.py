import uuid
from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.clock import business_today
from app.core.config import get_settings
from app.models.market_data import (
    DataQualityDaily,
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
    Theme,
    ThemeDaily,
    ThemeLimitDaily,
    ThemeMemberInterval,
    ThemeMemberSnapshot,
    ThemeMoneyflowDaily,
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
    normalize_theme_daily,
    normalize_theme_limit,
    normalize_theme_member_intervals,
    normalize_theme_members,
    normalize_theme_moneyflow,
    normalize_themes,
    normalize_trade_calendar,
)
from app.services.price_limit import validate_price_limit_rows
from app.services.quality.daily_quality import (
    CoverageResult,
    check_daily_coverage,
    expected_stock_daily_codes,
    persist_coverage_result,
)
from app.services.quality.raw_checks import check_raw_daily
from app.services.quality.raw_completeness import (
    ensure_stock_basic_ready,
    validate_trade_calendar_rows,
)
from app.services.quality.theme_quality import expected_theme_codes_on_date

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
THEME_DAILY_VALUE_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "avg_price",
    "change",
    "pct_change",
    "vol",
    "turnover_rate",
    "total_mv",
]
THEME_MONEYFLOW_VALUE_COLUMNS = [
    "lead_stock",
    "close_price",
    "pct_change",
    "theme_index",
    "company_num",
    "lead_stock_pct_change",
    "net_buy_amount",
    "net_sell_amount",
    "net_amount",
]
THEME_LIMIT_VALUE_COLUMNS = [
    "days",
    "up_stat",
    "cons_nums",
    "up_nums",
    "pct_chg",
    "hot_rank",
]


class ThemeDailyQualityError(ValueError):
    pass


class EodDataNotReadyError(RuntimeError):
    pass


class ThemeMemberSnapshotQualityError(ValueError):
    pass


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
            if df.empty and trade_date == business_today():
                raise EodDataNotReadyError(f"EOD_NOT_READY trade_date={trade_date}")
            issues = check_raw_daily(df, min_rows=0)
            fatal = [issue for issue in issues if issue.severity == "ERROR"]
            rows = normalize_stock_daily(df)
            expected_codes = expected_stock_daily_codes(self.db, trade_date)
            actual_codes = {row["ts_code"] for row in rows}
            authoritative_extra_codes = sorted(actual_codes - expected_codes)
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
                1 for row in rows for column in DAILY_VALUE_COLUMNS if row.get(column) is None
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
                extra_issue_codes={
                    "raw_issues": [issue.code for issue in fatal],
                    "authoritative_extra_count": len(authoritative_extra_codes),
                    "authoritative_extra_codes": authoritative_extra_codes[:100],
                },
            )
            if fatal:
                self.db.commit()
                raise ValueError(f"daily quality check failed: {[issue.code for issue in fatal]}")
            if quality.status == "ERROR":
                self.db.commit()
                raise ValueError(
                    "daily coverage check failed: "
                    f"actual={quality.actual_rows} expected={quality.expected_rows} "
                    f"coverage={quality.coverage_rate:.4f}"
                )
            _validate_stock_daily_reconcile_prerequisites(
                self.db,
                trade_date,
                expected_codes,
            )
            existing_codes = set(
                self.db.execute(
                    select(StockDaily.ts_code).where(StockDaily.trade_date == trade_date)
                )
                .scalars()
                .all()
            )
            stale_codes = existing_codes - expected_codes
            write_rows = [row for row in rows if row["ts_code"] in expected_codes]
            dirty_dates = changed_trade_dates(
                self.db,
                StockDaily,
                write_rows,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=DAILY_VALUE_COLUMNS,
                preserve_existing_on_null_columns=DAILY_VALUE_COLUMNS,
            )
            if stale_codes:
                self.db.execute(
                    delete(StockDaily).where(
                        StockDaily.trade_date == trade_date,
                        StockDaily.ts_code.in_(stale_codes),
                    )
                )
                dirty_dates.add(trade_date)
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
                write_rows,
                ["trade_date", "ts_code"],
                preserve_existing_on_null_columns=DAILY_VALUE_COLUMNS,
            )
            self.db.commit()
            logger.info(
                "synced stock_daily trade_date={} rows={} stale_deleted={} excluded={}",
                trade_date,
                count,
                len(stale_codes),
                len(authoritative_extra_codes),
            )
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
                {str(row["suspend_type"]) for row in rows if row["suspend_type"] not in {"S", "R"}}
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
            source_rows = normalize_stock_limit(df)
            expected_codes = expected_stock_daily_codes(self.db, trade_date)
            if not expected_codes:
                raise ValueError(
                    f"stk_limit authoritative universe is empty for {trade_date}; "
                    "destructive reconciliation refused"
                )
            target_rows = [
                row for row in source_rows if str(row["ts_code"]) in expected_codes
            ]
            extra_source_codes = sorted(
                {str(row["ts_code"]) for row in source_rows} - expected_codes
            )
            source_warnings = []
            if warning := df.attrs.get("provider_warning"):
                source_warnings.append(str(warning))
            fatal_issues: list[str] = []
            invalid_required_count = sum(
                1
                for item in df.to_dict("records")
                if _is_missing_required(item.get("trade_date"))
                or _is_missing_required(item.get("ts_code"))
            )
            if len(source_rows) != len(df.index) or invalid_required_count:
                fatal_issues.append("INVALID_REQUIRED_FIELDS")
            duplicate_count = _duplicate_count(target_rows, ["trade_date", "ts_code"])
            if duplicate_count:
                fatal_issues.append("DUPLICATE_NATURAL_KEY")
            limit_validation = validate_price_limit_rows(
                self.db,
                trade_date=trade_date,
                rows=target_rows,
            )
            if limit_validation.invalid_codes:
                fatal_issues.append("INVALID_LIMIT_VALUE")
            valid_codes = limit_validation.valid_codes
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
            if fatal_issues:
                quality = replace(
                    quality,
                    status="ERROR",
                    warning_count=0,
                    error_count=max(1, len(fatal_issues)),
                )
            elif source_warnings and quality.status == "PASS":
                quality = replace(quality, status="WARNING", warning_count=1)
            persist_coverage_result(
                self.db,
                quality,
                duplicate_count=duplicate_count,
                null_count=len(limit_validation.invalid_codes),
                job_id=job_id,
                extra_issue_codes={
                    "source_warnings": source_warnings,
                    "source_row_count": len(df.index),
                    "normalized_row_count": len(source_rows),
                    "target_row_count": len(target_rows),
                    "extra_source_count": len(source_rows) - len(target_rows),
                    "extra_source_codes": extra_source_codes[:100],
                    "fatal_issues": fatal_issues,
                    **limit_validation.issue_codes(),
                },
            )
            if quality.status == "ERROR":
                self.db.commit()
                raise ValueError(
                    "stk_limit quality check failed: "
                    f"coverage={quality.coverage_rate} fatal_issues={fatal_issues} "
                    f"source_warnings={source_warnings} "
                    f"invalid_limit_codes={sorted(limit_validation.invalid_codes)[:100]}"
                )
            dirty_dates = reconcile_daily_snapshot(
                self.db,
                StockLimitDaily,
                target_rows,
                trade_date=trade_date,
                conflict_columns=["trade_date", "ts_code"],
                compare_columns=LIMIT_VALUE_COLUMNS,
            )
            count = upsert_rows(
                self.db,
                StockLimitDaily,
                target_rows,
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
            logger.info(
                "synced stk_limit trade_date={} status={} rows={} source_rows={} "
                "extra_source={} warnings={}",
                trade_date,
                quality.status,
                count,
                len(source_rows),
                len(source_rows) - len(target_rows),
                source_warnings,
            )
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
            rows = _deduplicate_sector_member_rows(normalize_sector_members(df, code_to_id))
            if not rows:
                raise ValueError("sector members returned no valid rows")
            natural_keys = {(row["sector_id"], row["ts_code"], row["valid_from"]) for row in rows}
            existing_members = list(
                self.db.execute(
                    select(SectorMember)
                    .join(Sector, SectorMember.sector_id == Sector.sector_id)
                    .where(
                        Sector.source == "SW",
                        Sector.is_active.is_(True),
                    )
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

    def sync_ths_themes(self, snapshot_date: date) -> int:
        try:
            frame = self.provider.get_ths_concepts()
            rows = normalize_themes(frame, snapshot_date)
            if not rows or frame.attrs.get("provider_warning"):
                raise ValueError("ths theme catalog invalid or possibly truncated")
            source_codes = {str(row["theme_code"]) for row in rows}
            count = upsert_rows(
                self.db,
                Theme,
                rows,
                ["theme_code"],
                update_columns=[
                    "source",
                    "name",
                    "theme_type",
                    "exchange",
                    "constituent_count",
                    "list_date",
                    "is_active",
                    "last_seen_date",
                    "updated_at",
                ],
            )
            self.db.execute(
                update(Theme)
                .where(
                    Theme.source == "THS",
                    Theme.is_active.is_(True),
                    Theme.theme_code.not_in(source_codes),
                )
                .values(is_active=False)
            )
            _persist_theme_quality(
                self.db, snapshot_date, "ths_theme_catalog", len(rows), len(rows), "PASS"
            )
            self.db.commit()
            return count
        except Exception:
            self.db.rollback()
            _persist_theme_quality(self.db, snapshot_date, "ths_theme_catalog", 0, 0, "ERROR")
            self.db.commit()
            raise

    def sync_ths_theme_member_snapshot(self, snapshot_date: date) -> int:
        catalog_rows = list(
            self.db.execute(
                select(Theme.theme_code, Theme.constituent_count).where(
                    Theme.source == "THS",
                    Theme.theme_type == "CONCEPT",
                    Theme.is_active.is_(True),
                )
            )
            .all()
        )
        theme_counts: dict[str, int | None] = {}
        for row in catalog_rows:
            if isinstance(row, str):
                theme_counts[row] = None
            else:
                theme_counts[str(row[0])] = row[1]
        theme_codes = list(theme_counts)
        requested_codes = {
            code for code, count in theme_counts.items() if count is None or count > 0
        }
        existing_quality = self.db.execute(
            select(DataQualityDaily).where(
                DataQualityDaily.trade_date == snapshot_date,
                DataQualityDaily.dataset == "ths_theme_member_snapshot",
            )
        ).scalar_one_or_none()
        try:
            if not theme_codes:
                raise ValueError("no active THS themes; sync catalog first")
            frame = self.provider.get_ths_concept_members(sorted(requested_codes))
            rows = normalize_theme_members(frame, snapshot_date)
            interval_rows = normalize_theme_member_intervals(frame)
            returned_codes = {str(row["theme_code"]) for row in rows}
            missing = sorted(requested_codes - returned_codes)
            unexpected = sorted(returned_codes - requested_codes)
            diagnostics = frame.attrs.get("theme_member_diagnostics", {})
            failed_themes = {
                str(code): str(error)[:500]
                for code, error in dict(diagnostics.get("failed_codes", {})).items()
            }
            warning_themes = {
                str(code): str(warning)[:500]
                for code, warning in dict(diagnostics.get("warning_codes", {})).items()
            }
            if frame.attrs.get("provider_warning") == "POSSIBLE_TRUNCATION":
                warning_themes["__batch__"] = "POSSIBLE_TRUNCATION"
            duplicate_count = _duplicate_count(
                rows, ["snapshot_date", "theme_code", "ts_code"]
            )
            unique = {
                (row["snapshot_date"], row["theme_code"], row["ts_code"]): row for row in rows
            }
            rows = list(unique.values())
            quality_config = self.settings.opportunity_config.get("theme_quality", {}).get(
                "member_snapshot", {}
            )
            warning_threshold = float(quality_config.get("warning_coverage_rate", 0.95))
            error_threshold = float(quality_config.get("error_coverage_rate", 0.90))
            coverage = (
                len(returned_codes & requested_codes) / len(requested_codes)
                if requested_codes
                else None
            )
            fatal_issues = []
            if unexpected:
                fatal_issues.append("UNEXPECTED_THEME_CODE")
            if duplicate_count:
                fatal_issues.append("DUPLICATE_NATURAL_KEY")
            if not frame.empty and not {"ts_code", "con_code"} <= set(frame.columns):
                fatal_issues.append("INVALID_REQUIRED_FIELDS")
            if fatal_issues or coverage is None or coverage < error_threshold:
                status = "ERROR"
            elif coverage < warning_threshold or missing or failed_themes or warning_themes:
                status = "WARNING"
            else:
                status = "PASS"
            issue_metadata = {
                "snapshot_mode": "FULL" if status == "PASS" else "PARTIAL",
                "requested_theme_count": len(requested_codes),
                "returned_theme_count": len(returned_codes & requested_codes),
                "missing_theme_count": len(missing),
                "missing_theme_codes": missing[:100],
                "failed_theme_count": len(failed_themes),
                "failed_themes": dict(list(sorted(failed_themes.items()))[:100]),
                "provider_warning_theme_count": len(warning_themes),
                "provider_warning_themes": dict(
                    list(sorted(warning_themes.items()))[:100]
                ),
                "member_row_count": len(rows),
                "coverage_rate": coverage,
                "fatal_issues": fatal_issues,
                "unexpected_theme_codes": unexpected[:100],
                "issues": ["CURRENT_MEMBER_EMPTY"] if missing else [],
            }
            if _preserve_existing_theme_snapshot(existing_quality, status, coverage):
                existing_count = int(
                    self.db.execute(
                        select(func.count())
                        .select_from(ThemeMemberSnapshot)
                        .where(ThemeMemberSnapshot.snapshot_date == snapshot_date)
                    ).scalar_one()
                )
                logger.warning(
                    "kept better THS theme member snapshot date={} existing_status={} "
                    "new_status={} new_coverage={}",
                    snapshot_date,
                    existing_quality.status,
                    status,
                    coverage,
                )
                return existing_count
            if status == "ERROR":
                _persist_theme_quality(
                    self.db,
                    snapshot_date,
                    "ths_theme_member_snapshot",
                    len(requested_codes),
                    len(returned_codes & requested_codes),
                    status,
                    missing_codes=missing,
                    issue_metadata=issue_metadata,
                )
                self.db.commit()
                raise ThemeMemberSnapshotQualityError(
                    "THS theme member snapshot ERROR "
                    f"coverage={coverage} missing={len(missing)} fatal={fatal_issues}"
                )
            self.db.execute(
                delete(ThemeMemberSnapshot).where(
                    ThemeMemberSnapshot.snapshot_date == snapshot_date
                )
            )
            count = upsert_rows(
                self.db,
                ThemeMemberSnapshot,
                rows,
                ["snapshot_date", "theme_code", "ts_code"],
            )
            if interval_rows:
                upsert_rows(
                    self.db,
                    ThemeMemberInterval,
                    interval_rows,
                    ["theme_code", "ts_code", "valid_from"],
                )
            _persist_theme_quality(
                self.db,
                snapshot_date,
                "ths_theme_member_snapshot",
                len(requested_codes),
                len(returned_codes & requested_codes),
                status,
                missing_codes=missing,
                issue_metadata=issue_metadata,
            )
            self.db.commit()
            logger.info(
                "THS theme member snapshot {} date={} requested={} returned={} "
                "missing={} rows={}",
                status,
                snapshot_date,
                len(requested_codes),
                len(returned_codes & requested_codes),
                len(missing),
                count,
            )
            return count
        except ThemeMemberSnapshotQualityError:
            raise
        except Exception as exc:
            self.db.rollback()
            if _preserve_existing_theme_snapshot(existing_quality, "ERROR", None):
                existing_count = int(
                    self.db.execute(
                        select(func.count())
                        .select_from(ThemeMemberSnapshot)
                        .where(ThemeMemberSnapshot.snapshot_date == snapshot_date)
                    ).scalar_one()
                )
                logger.warning(
                    "kept existing THS theme member snapshot after fetch failure "
                    "date={} status={} error={}",
                    snapshot_date,
                    existing_quality.status,
                    exc,
                )
                return existing_count
            _persist_theme_quality(
                self.db,
                snapshot_date,
                "ths_theme_member_snapshot",
                len(requested_codes),
                0,
                "ERROR",
                error=str(exc),
            )
            self.db.commit()
            raise

    def sync_theme_daily(self, trade_date: date) -> int:
        expected_codes = expected_theme_codes_on_date(self.db, trade_date)
        try:
            if not expected_codes:
                raise ValueError(f"no known THS themes on {trade_date}; sync catalog first")
            frame = self.provider.get_ths_daily(trade_date)
            if frame.attrs.get("provider_warning"):
                raise ValueError("ths_theme_daily POSSIBLE_TRUNCATION")
            source_rows = normalize_theme_daily(frame)
            actual_codes = {row["theme_code"] for row in source_rows}
            rows = [row for row in source_rows if row["theme_code"] in expected_codes]
            quality_config = self.settings.opportunity_config.get("theme_quality", {}).get(
                "daily", {}
            )
            result = check_daily_coverage(
                trade_date=trade_date,
                actual_codes=actual_codes,
                expected_codes=expected_codes,
                warning_coverage_rate=float(quality_config.get("warning_coverage_rate", 0.90)),
                error_coverage_rate=float(quality_config.get("error_coverage_rate", 0.75)),
                dataset="ths_theme_daily",
            )
            persist_coverage_result(self.db, result)
            if result.status == "ERROR":
                self.db.commit()
                raise ThemeDailyQualityError(
                    "ths_theme_daily coverage ERROR "
                    f"expected={result.expected_rows} actual={result.actual_rows}"
                )
            dirty_dates = reconcile_daily_snapshot(
                self.db,
                ThemeDaily,
                rows,
                trade_date=trade_date,
                conflict_columns=["trade_date", "theme_code"],
                compare_columns=THEME_DAILY_VALUE_COLUMNS,
            )
            count = upsert_rows(self.db, ThemeDaily, rows, ["trade_date", "theme_code"])
            record_dirty_range(
                self.db,
                dataset="theme_daily",
                dirty_dates=dirty_dates,
                reason="authoritative theme daily snapshot changed",
            )
            self.db.commit()
            return count
        except ThemeDailyQualityError:
            raise
        except Exception as exc:
            self.db.rollback()
            status = _optional_theme_error_status(exc)
            _persist_theme_quality(
                self.db,
                trade_date,
                "ths_theme_daily",
                len(expected_codes),
                0,
                status,
                error=str(exc),
            )
            self.db.commit()
            raise

    def sync_theme_optional_sources(self, trade_date: date) -> dict[str, str]:
        statuses = {}
        statuses["moneyflow"] = self._sync_optional_theme_source(
            trade_date,
            "ths_theme_moneyflow",
            self.provider.get_ths_concept_moneyflow,
            normalize_theme_moneyflow,
            ThemeMoneyflowDaily,
        )
        statuses["limit"] = self._sync_optional_theme_source(
            trade_date,
            "ths_theme_limit",
            self.provider.get_limit_concept_list,
            normalize_theme_limit,
            ThemeLimitDaily,
        )
        return statuses

    def _sync_optional_theme_source(
        self,
        trade_date: date,
        dataset: str,
        fetch,
        normalize,
        model: type,
    ) -> str:
        try:
            expected_codes = expected_theme_codes_on_date(self.db, trade_date)
            if not expected_codes:
                raise ValueError(f"no known THS themes on {trade_date}; sync catalog first")
            frame = fetch(trade_date)
            if frame.attrs.get("provider_warning"):
                raise ValueError(f"{dataset} POSSIBLE_TRUNCATION")
            source_rows = normalize(frame)
            extra_codes = sorted(
                {row["theme_code"] for row in source_rows} - expected_codes
            )
            rows = [row for row in source_rows if row["theme_code"] in expected_codes]
            status = "WARNING" if extra_codes else "PASS" if rows else "SOURCE_EMPTY"
            compare_columns = (
                THEME_MONEYFLOW_VALUE_COLUMNS
                if model is ThemeMoneyflowDaily
                else THEME_LIMIT_VALUE_COLUMNS
            )
            dirty_dates = reconcile_daily_snapshot(
                self.db,
                model,
                rows,
                trade_date=trade_date,
                conflict_columns=["trade_date", "theme_code"],
                compare_columns=compare_columns,
            )
            upsert_rows(self.db, model, rows, ["trade_date", "theme_code"])
            record_dirty_range(
                self.db,
                dataset=(
                    "theme_moneyflow_daily"
                    if model is ThemeMoneyflowDaily
                    else "theme_limit_daily"
                ),
                dirty_dates=dirty_dates,
                reason=f"authoritative {dataset} snapshot changed",
            )
            _persist_theme_quality(
                self.db,
                trade_date,
                dataset,
                len(rows),
                len(rows),
                status,
                extra_codes=extra_codes,
            )
            self.db.commit()
            return status
        except Exception as exc:
            self.db.rollback()
            status = _optional_theme_error_status(exc)
            _persist_theme_quality(self.db, trade_date, dataset, 0, 0, status, error=str(exc))
            self.db.commit()
            return status


def _validate_stock_daily_reconcile_prerequisites(
    db: Session,
    trade_date: date,
    expected_codes: set[str],
) -> None:
    ensure_stock_basic_ready(db)
    if not expected_codes:
        raise ValueError(
            f"stock_daily authoritative universe is empty for {trade_date}; "
            "destructive reconciliation refused"
        )
    suspend_status = db.execute(
        select(DataQualityDaily.status).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == "suspend_d",
        )
    ).scalar_one_or_none()
    if suspend_status != "PASS":
        raise ValueError(
            f"suspend_d successful source sync evidence missing for {trade_date}; "
            "stock_daily destructive reconciliation refused"
        )


def _persist_theme_quality(
    db: Session,
    trade_date: date,
    dataset: str,
    expected_rows: int,
    actual_rows: int,
    status: str,
    *,
    error: str | None = None,
    extra_codes: list[str] | None = None,
    missing_codes: list[str] | None = None,
    issue_metadata: dict[str, object] | None = None,
) -> None:
    coverage = actual_rows / expected_rows if expected_rows else None
    missing_codes = missing_codes or []
    issue_codes: dict[str, object] = {
        "missing_codes": missing_codes[:100],
        "extra_codes": (extra_codes or [])[:100],
    }
    if error:
        issue_codes["source_error"] = error[:1000]
    if issue_metadata:
        issue_codes.update(issue_metadata)
    is_error = status in {"ERROR", "PERMISSION_UNAVAILABLE", "TRANSIENT_ERROR"}
    upsert_rows(
        db,
        DataQualityDaily,
        [{
            "trade_date": trade_date,
            "dataset": dataset,
            "expected_rows": expected_rows,
            "actual_rows": actual_rows,
            "coverage_rate": coverage,
            "missing_count": len(missing_codes),
            "duplicate_count": 0,
            "null_count": 0,
            "warning_count": 1 if status == "WARNING" else 0,
            "error_count": 1 if is_error else 0,
            "status": status,
            "issue_codes": issue_codes,
        }],
        ["trade_date", "dataset"],
    )


def _preserve_existing_theme_snapshot(
    existing: DataQualityDaily | None,
    new_status: str,
    new_coverage: float | None,
) -> bool:
    if existing is None:
        return False
    rank = {"ERROR": 0, "WARNING": 1, "PASS": 2}
    existing_rank = rank.get(existing.status, 0)
    new_rank = rank.get(new_status, 0)
    if new_rank < existing_rank:
        return True
    return (
        new_status == existing.status == "WARNING"
        and float(new_coverage or 0) < float(existing.coverage_rate or 0)
    )


def _optional_theme_error_status(exc: Exception) -> str:
    message = str(exc).lower()
    if any(marker in message for marker in ("permission", "无权限", "积分不足")):
        return "PERMISSION_UNAVAILABLE"
    if any(
        marker in message for marker in ("timeout", "connection", "unexpected_eof", "max retries")
    ):
        return "TRANSIENT_ERROR"
    return "ERROR"


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
        strategy.get("raw_quality", {}).get(dataset, {}).get(f"{severity}_coverage_rate", default)
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


def _is_missing_required(value: object) -> bool:
    return value is None or bool(pd.isna(value)) or not str(value).strip()


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
