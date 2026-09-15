import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import IndexDaily, SectorFactorDaily, SectorMember, StockFactorDaily
from app.repositories.replace_slice import replace_slice_rows
from app.services.calc_metadata import calculation_metadata
from app.services.sector.engine import SectorConfig, calculate_sector_factors


class SectorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def recalc(self, start: date, end: date, calc_run_id: uuid.UUID | None = None) -> int:
        lookback_start = start - timedelta(days=100)
        factors = self._read_factors(lookback_start, end)
        members = self._read_members()
        index_daily = self._read_index_daily(lookback_start, end)

        config = SectorConfig.from_strategy(self.settings.strategy)
        sector_factors = calculate_sector_factors(
            factors=factors,
            members=members,
            index_daily=index_daily,
            start=start,
            end=end,
            config=config,
        )
        metadata = calculation_metadata(
            config=self.settings.strategy,
            calc_version="sector_v1",
            calc_run_id=calc_run_id,
        )
        rows = [{**_clean_row(row), **metadata} for row in sector_factors.to_dict("records")]
        count = replace_slice_rows(
            self.db,
            SectorFactorDaily,
            rows,
            scope_filters=[
                SectorFactorDaily.trade_date >= start,
                SectorFactorDaily.trade_date <= end,
            ],
            key_columns=["trade_date", "sector_id"],
        )
        self.db.commit()
        logger.info("recalculated sector_factor_daily start={} end={} rows={}", start, end, count)
        return count

    def _read_factors(self, start: date, end: date) -> pd.DataFrame:
        stmt = (
            select(
                StockFactorDaily.trade_date,
                StockFactorDaily.ts_code,
                StockFactorDaily.adj_close,
                StockFactorDaily.ma20,
                StockFactorDaily.ma60,
                StockFactorDaily.return1,
                StockFactorDaily.return3,
                StockFactorDaily.return5,
                StockFactorDaily.return20,
                StockFactorDaily.breakout20,
                StockFactorDaily.rps60,
                StockFactorDaily.amount_ma20,
                StockFactorDaily.amount_ratio20,
                StockFactorDaily.eligible,
            )
            .where(StockFactorDaily.trade_date >= start, StockFactorDaily.trade_date <= end)
            .order_by(StockFactorDaily.trade_date, StockFactorDaily.ts_code)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())

    def _read_members(self) -> pd.DataFrame:
        stmt = select(
            SectorMember.sector_id,
            SectorMember.ts_code,
            SectorMember.valid_from,
            SectorMember.valid_to,
            SectorMember.is_latest,
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
