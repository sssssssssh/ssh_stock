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
from app.services.quality.raw_checks import check_raw_daily


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

    def sync_daily(self, trade_date: date) -> int:
        df = self.provider.get_daily(trade_date)
        issues = check_raw_daily(df, min_rows=1)
        fatal = [issue for issue in issues if issue.severity == "ERROR"]
        if fatal:
            raise ValueError(f"daily quality check failed: {[issue.code for issue in fatal]}")
        rows = normalize_stock_daily(df)
        count = upsert_rows(self.db, StockDaily, rows, ["trade_date", "ts_code"])
        logger.info("synced stock_daily trade_date={} rows={}", trade_date, count)
        return count

    def sync_adj_factor(self, trade_date: date) -> int:
        df = self.provider.get_adj_factor(trade_date)
        rows = normalize_adj_factor(df)
        count = upsert_rows(self.db, StockAdjFactor, rows, ["trade_date", "ts_code"])
        logger.info("synced stock_adj_factor trade_date={} rows={}", trade_date, count)
        return count

    def sync_daily_basic(self, trade_date: date) -> int:
        df = self.provider.get_daily_basic(trade_date)
        rows = normalize_daily_basic(df)
        count = upsert_rows(self.db, StockDailyBasic, rows, ["trade_date", "ts_code"])
        logger.info("synced stock_daily_basic trade_date={} rows={}", trade_date, count)
        return count

    def sync_index_daily(self, trade_date: date) -> int:
        benchmark = self.settings.strategy.get("benchmark", {})
        codes = benchmark.get("market_indices", ["000300.SH"])
        df = self.provider.get_index_daily(trade_date, codes)
        rows = normalize_index_daily(df)
        count = upsert_rows(self.db, IndexDaily, rows, ["trade_date", "ts_code"])
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
        df = self.provider.get_sector_members()
        rows = normalize_sector_members(df, code_to_id)
        count = upsert_rows(
            self.db,
            SectorMember,
            rows,
            ["sector_id", "ts_code", "valid_from"],
        )
        logger.info("synced sector members rows={}", count)
        return count
