import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    IndexDaily,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockFactorDaily,
    StockTradeStatusDaily,
)
from app.repositories.calculation_frame import read_calculation_frame
from app.repositories.replace_slice import replace_slice_rows
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    TRADE_STATUS_CALC_VERSION,
    analysis_strategy_config,
    analysis_strategy_hash,
)
from app.services.calc_metadata import calculation_metadata
from app.services.calculation_progress import run_calculation
from app.services.factors.engine import FactorConfig, calculate_stock_factors
from app.services.job_execution import checkpoint


class FactorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.input_window = None

    def recalc(self, start: date, end: date, calc_run_id: uuid.UUID | None = None) -> int:
        lookback_start = start - timedelta(days=430)
        if self.input_window is not None:
            self.input_window.prepare(lookback_start, end)
        daily = self._read_daily(lookback_start, end)
        adj_factor = self._read_adj_factor(lookback_start, end)
        stock_basic = self._read_stock_basic()
        trade_status = self._read_trade_status(lookback_start, end)
        index_daily = self._read_index_daily(lookback_start, end)

        benchmark = self.settings.strategy.get("benchmark", {}).get("primary", "000300.SH")
        config = FactorConfig.from_strategy(self.settings.strategy)
        if self.input_window is not None:
            from app.services.calculation_memory import check_calculation_memory

            check_calculation_memory(reserve=max(256 * 1024**2, self.input_window.bytes * 2))
        factors = run_calculation("factors.compute", calculate_stock_factors,
            daily=daily,
            adj_factor=adj_factor,
            stock_basic=stock_basic,
            index_daily=index_daily,
            benchmark_code=benchmark,
            start=start,
            end=end,
            config=config,
            trade_status=trade_status,
            optimize_cpu=self.settings.factor_cpu_optimization_enabled,
            check_cancelled=checkpoint if self.input_window is not None
            or self.settings.factor_cpu_optimization_enabled else None,
        )
        if self.input_window is not None:
            check_calculation_memory()
        metadata = calculation_metadata(
            config=analysis_strategy_config(self.settings.strategy),
            calc_version=FACTOR_CALC_VERSION,
            calc_run_id=calc_run_id,
        )
        rows = [{**_clean_row(row), **metadata} for row in factors.to_dict("records")]
        count = replace_slice_rows(
            self.db,
            StockFactorDaily,
            rows,
            scope_filters=[
                StockFactorDaily.trade_date >= start,
                StockFactorDaily.trade_date <= end,
            ],
            key_columns=["trade_date", "ts_code"],
        )
        self.db.commit()
        logger.info("recalculated stock_factor_daily start={} end={} rows={}", start, end, count)
        return count

    def _read_daily(self, start: date, end: date) -> pd.DataFrame:
        stmt = (
            select(
                StockDaily.trade_date,
                StockDaily.ts_code,
                StockDaily.open,
                StockDaily.high,
                StockDaily.low,
                StockDaily.close,
                StockDaily.vol,
                StockDaily.amount,
            )
            .where(StockDaily.trade_date >= start, StockDaily.trade_date <= end)
            .order_by(StockDaily.ts_code, StockDaily.trade_date)
        )
        return self._read_input(stmt, name="factors.stock_daily", start=start, end=end,
                                date_column=StockDaily.trade_date)

    def _read_adj_factor(self, start: date, end: date) -> pd.DataFrame:
        stmt = select(
            StockAdjFactor.trade_date,
            StockAdjFactor.ts_code,
            StockAdjFactor.adj_factor,
        ).where(StockAdjFactor.trade_date >= start, StockAdjFactor.trade_date <= end)
        return self._read_input(stmt, name="factors.adj_factor", start=start, end=end,
                                date_column=StockAdjFactor.trade_date)

    def _read_stock_basic(self) -> pd.DataFrame:
        stmt = select(
            StockBasic.ts_code,
            StockBasic.list_date,
            StockBasic.delist_date,
        )
        return self._read_input(stmt, name="factors.stock_basic")

    def _read_trade_status(self, start: date, end: date) -> pd.DataFrame:
        hash_value = analysis_strategy_hash(self.settings.strategy)
        if self.settings.ab_merge_read_enabled:
            from app.repositories.ab_merge_read import ABMergeReadRepository, ReadWindow

            return ABMergeReadRepository(self.db).read_trade_status(
                window=ReadWindow(start, end), calc_version=TRADE_STATUS_CALC_VERSION,
                config_hash=hash_value,
            )
        stmt = select(
            StockTradeStatusDaily.trade_date,
            StockTradeStatusDaily.ts_code,
            StockTradeStatusDaily.is_active,
            StockTradeStatusDaily.is_suspended,
            StockTradeStatusDaily.is_st,
            StockTradeStatusDaily.st_status_unknown,
        ).where(
            StockTradeStatusDaily.trade_date >= start,
            StockTradeStatusDaily.trade_date <= end,
            StockTradeStatusDaily.calc_version == TRADE_STATUS_CALC_VERSION,
            StockTradeStatusDaily.config_hash == hash_value,
        )
        return self._read_input(stmt, name="factors.trade_status", start=start, end=end,
                                date_column=StockTradeStatusDaily.trade_date)

    def _read_index_daily(self, start: date, end: date) -> pd.DataFrame:
        stmt = (
            select(IndexDaily.trade_date, IndexDaily.ts_code, IndexDaily.close)
            .where(IndexDaily.trade_date >= start, IndexDaily.trade_date <= end)
            .order_by(IndexDaily.ts_code, IndexDaily.trade_date)
        )
        return self._read_input(stmt, name="factors.index_daily", start=start, end=end,
                                date_column=IndexDaily.trade_date)

    def _read_input(self, statement, *, name, **window):
        if self.input_window is not None:
            return self.input_window.read(statement, name=name, **window)
        return read_calculation_frame(self.db, statement, name=name)


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
