import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import IndexDaily, MarketDaily, StockDaily, StockFactorDaily
from app.repositories.upsert import upsert_rows
from app.services.calc_metadata import calculation_metadata
from app.services.market.engine import MarketConfig, calculate_market_daily


class MarketService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def recalc(self, start: date, end: date, calc_run_id: uuid.UUID | None = None) -> int:
        lookback_start = start - timedelta(days=100)
        factors = self._read_factors(lookback_start, end)
        daily = self._read_daily(lookback_start, end)
        index_daily = self._read_index_daily(lookback_start, end)

        config = MarketConfig.from_strategy(self.settings.strategy)
        market = calculate_market_daily(
            factors=factors,
            daily=daily,
            index_daily=index_daily,
            start=start,
            end=end,
            config=config,
        )
        metadata = calculation_metadata(
            config=self.settings.strategy,
            calc_version="market_v1",
            calc_run_id=calc_run_id,
        )
        rows = [{**_clean_row(row), **metadata} for row in market.to_dict("records")]
        count = upsert_rows(self.db, MarketDaily, rows, ["trade_date"])
        self.db.commit()
        logger.info("recalculated market_daily start={} end={} rows={}", start, end, count)
        return count

    def _read_factors(self, start: date, end: date) -> pd.DataFrame:
        stmt = (
            select(
                StockFactorDaily.trade_date,
                StockFactorDaily.ts_code,
                StockFactorDaily.adj_close,
                StockFactorDaily.ma20,
                StockFactorDaily.ma60,
                StockFactorDaily.low20,
                StockFactorDaily.low60,
                StockFactorDaily.breakout20,
                StockFactorDaily.breakout60,
                StockFactorDaily.eligible,
            )
            .where(StockFactorDaily.trade_date >= start, StockFactorDaily.trade_date <= end)
            .order_by(StockFactorDaily.trade_date, StockFactorDaily.ts_code)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())

    def _read_daily(self, start: date, end: date) -> pd.DataFrame:
        stmt = (
            select(
                StockDaily.trade_date,
                StockDaily.ts_code,
                StockDaily.close,
                StockDaily.pre_close,
                StockDaily.pct_chg,
                StockDaily.amount,
            )
            .where(StockDaily.trade_date >= start, StockDaily.trade_date <= end)
            .order_by(StockDaily.trade_date, StockDaily.ts_code)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())

    def _read_index_daily(self, start: date, end: date) -> pd.DataFrame:
        stmt = (
            select(IndexDaily.trade_date, IndexDaily.ts_code, IndexDaily.close)
            .where(IndexDaily.trade_date >= start, IndexDaily.trade_date <= end)
            .order_by(IndexDaily.ts_code, IndexDaily.trade_date)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if pd.isna(value):
            cleaned[key] = None
        elif hasattr(value, "item"):
            cleaned[key] = value.item()
        else:
            cleaned[key] = value
    return cleaned
