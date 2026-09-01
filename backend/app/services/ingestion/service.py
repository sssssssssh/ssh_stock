import uuid
from datetime import date

from loguru import logger
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
    TradeCalendar,
)
from app.providers.base import MarketDataProvider
from app.repositories.upsert import upsert_rows
from app.services.dirty import changed_trade_dates, record_dirty_range
from app.services.ingestion.normalizers import (
    normalize_adj_factor,
    normalize_daily_basic,
    normalize_index_daily,
    normalize_sector_members,
    normalize_sectors,
    normalize_stock_basic,
    normalize_stock_daily,
    normalize_trade_calendar,
)
from app.services.quality.daily_quality import (
    check_daily_coverage,
    expected_stock_codes,
    persist_coverage_result,
)
from app.services.quality.raw_checks import check_raw_daily

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


class IngestionService:
    def __init__(self, db: Session, provider: MarketDataProvider) -> None:
        self.db = db
        self.provider = provider
        self.settings = get_settings()

    def sync_trade_calendar(self, start: date, end: date) -> int:
        df = self.provider.get_trade_calendar(start, end)
        rows = normalize_trade_calendar(df)
        count = upsert_rows(self.db, TradeCalendar, rows, ["cal_date"])
        logger.info("synced trade_calendar rows={}", count)
        return count

    def sync_stock_basic(self) -> int:
        df = self.provider.get_stock_basic()
        rows = normalize_stock_basic(df)
        count = upsert_rows(self.db, StockBasic, rows, ["ts_code"])
        logger.info("synced stock_basic rows={}", count)
        return count

    def sync_daily(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
        df = self.provider.get_daily(trade_date)
        issues = check_raw_daily(df, min_rows=0)
        fatal = [issue for issue in issues if issue.severity == "ERROR"]
        if fatal:
            raise ValueError(f"daily quality check failed: {[issue.code for issue in fatal]}")
        rows = normalize_stock_daily(df)
        expected_codes = expected_stock_codes(self.db, trade_date)
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
        persist_coverage_result(
            self.db,
            quality,
            duplicate_count=duplicate_count,
            null_count=null_count,
            job_id=job_id,
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
        logger.info("synced stock_daily trade_date={} rows={}", trade_date, count)
        return count

    def sync_adj_factor(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
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
        logger.info("synced stock_adj_factor trade_date={} rows={}", trade_date, count)
        return count

    def sync_daily_basic(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
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
        logger.info("synced stock_daily_basic trade_date={} rows={}", trade_date, count)
        return count

    def sync_index_daily(self, trade_date: date, job_id: uuid.UUID | None = None) -> int:
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
        logger.info("synced index_daily trade_date={} rows={}", trade_date, count)
        return count

    def sync_sector_metadata(self) -> int:
        df = self.provider.get_sector_classification()
        rows = normalize_sectors(df, source="SW")
        count = upsert_rows(self.db, Sector, rows, ["source", "source_code"])
        logger.info("synced sector metadata rows={}", count)
        return count

    def sync_sector_members(self) -> int:
        sector_rows = self.db.query(Sector).filter(Sector.source == "SW").all()
        code_to_id = {row.source_code: row.sector_id for row in sector_rows}
        list_dates = {
            row.ts_code: row.list_date
            for row in self.db.query(StockBasic.ts_code, StockBasic.list_date).all()
            if row.list_date is not None
        }
        df = self.provider.get_sector_members()
        rows = normalize_sector_members(df, code_to_id, stock_list_dates=list_dates)
        count = upsert_rows(
            self.db,
            SectorMember,
            rows,
            ["sector_id", "ts_code", "valid_from"],
        )
        logger.info("synced sector members rows={}", count)
        return count


def _quality_threshold(strategy: dict, severity: str) -> float:
    daily = strategy.get("data_quality", {}).get("daily", {})
    key = f"{severity}_coverage_rate"
    default = 0.98 if severity == "warning" else 0.95
    return float(daily.get(key, default))
