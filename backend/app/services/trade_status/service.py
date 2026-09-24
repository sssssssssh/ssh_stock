import uuid
from datetime import date
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    StockBasic,
    StockDaily,
    StockLimitDaily,
    StockStDaily,
    StockSuspendDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.repositories.replace_slice import replace_slice_rows
from app.services.analysis_identity import (
    TRADE_STATUS_CALC_VERSION,
    analysis_strategy_config,
)
from app.services.calc_metadata import calculation_metadata
from app.services.trade_status.engine import calculate_trade_status_rows


class TradeStatusService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def recalc(self, start: date, end: date, calc_run_id: uuid.UUID | None = None) -> int:
        trade_dates = list(
            self.db.execute(
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
        status = calculate_trade_status_rows(
            trade_dates=trade_dates,
            stock_basic=self._read_stock_basic(),
            daily=self._read_range(StockDaily, start, end),
            stock_st=self._read_range(StockStDaily, start, end),
            suspend_daily=self._read_range(StockSuspendDaily, start, end),
            stock_limit=self._read_range(StockLimitDaily, start, end),
            exclude_st=bool(self.settings.strategy.get("universe", {}).get("exclude_st", True)),
        )
        metadata = calculation_metadata(
            config=analysis_strategy_config(self.settings.strategy),
            calc_version=TRADE_STATUS_CALC_VERSION,
            calc_run_id=calc_run_id,
        )
        rows = [{**_clean_row(row), **metadata} for row in status.to_dict("records")]
        count = replace_slice_rows(
            self.db,
            StockTradeStatusDaily,
            rows,
            scope_filters=[
                StockTradeStatusDaily.trade_date >= start,
                StockTradeStatusDaily.trade_date <= end,
            ],
            key_columns=["trade_date", "ts_code"],
        )
        self.db.commit()
        logger.info(
            "recalculated stock_trade_status_daily start={} end={} rows={}",
            start,
            end,
            count,
        )
        return count

    def _read_stock_basic(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.db.execute(
                select(
                    StockBasic.ts_code,
                    StockBasic.list_date,
                    StockBasic.delist_date,
                )
            )
            .mappings()
            .all()
        )

    def _read_range(self, model: type, start: date, end: date) -> pd.DataFrame:
        return pd.DataFrame(
            self.db.execute(
                select(*model.__table__.columns).where(
                    model.trade_date >= start,
                    model.trade_date <= end,
                )
            )
            .mappings()
            .all()
        )


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: None if pd.isna(value) else value.item() if hasattr(value, "item") else value
        for key, value in row.items()
    }
