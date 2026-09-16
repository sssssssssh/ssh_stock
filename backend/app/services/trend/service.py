import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    SectorMember,
    StockFactorDaily,
    StockStateDaily,
    StrategySignal,
)
from app.repositories.replace_slice import replace_slice_rows
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    SECTOR_CALC_VERSION,
    TREND_CALC_VERSION,
)
from app.services.calc_metadata import calculation_metadata, config_hash
from app.services.trend.engine import (
    TrendConfig,
    calculate_stock_states,
    generate_strategy_signals,
)


class TrendService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def recalc(
        self,
        start: date,
        end: date,
        algo_version: str | None = None,
        calc_run_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        version = algo_version or self.settings.algo_version
        run_id = calc_run_id or uuid.uuid4()
        lookback_start = start - timedelta(days=180)
        factors = self._read_factors(lookback_start, end)
        market = self._read_market(lookback_start, end)
        sector_members = self._read_sector_members()
        sector_factors = self._read_sector_factors(lookback_start, end)
        previous_states = self._read_previous_states(lookback_start, start, version)

        config = TrendConfig.from_strategy(self.settings.strategy, algo_version=version)
        states = calculate_stock_states(
            factors=factors,
            market=market,
            sector_members=sector_members,
            sector_factors=sector_factors,
            previous_states=previous_states,
            start=start,
            end=end,
            config=config,
        )
        state_metadata = calculation_metadata(
            config=self.settings.strategy,
            calc_version="trend_v1",
            calc_run_id=run_id,
        )
        state_rows = [
            {**_clean_row(row), **state_metadata}
            for row in states.to_dict("records")
        ]
        _ensure_unique_rows(state_rows, ["trade_date", "ts_code", "algo_version"])
        state_count = replace_slice_rows(
            self.db,
            StockStateDaily,
            state_rows,
            scope_filters=[
                StockStateDaily.trade_date >= start,
                StockStateDaily.trade_date <= end,
                StockStateDaily.algo_version == version,
            ],
            key_columns=["trade_date", "ts_code", "algo_version"],
        )

        signals = generate_strategy_signals(states, config)
        signal_metadata = calculation_metadata(
            config=self.settings.strategy,
            calc_version="signal_v1",
            calc_run_id=run_id,
        )
        signal_rows = [
            {**_clean_row(row), **signal_metadata}
            for row in signals.to_dict("records")
        ]
        _ensure_unique_rows(
            signal_rows,
            ["trade_date", "ts_code", "signal_type", "algo_version"],
        )
        signal_count = replace_slice_rows(
            self.db,
            StrategySignal,
            signal_rows,
            scope_filters=[
                StrategySignal.trade_date >= start,
                StrategySignal.trade_date <= end,
                StrategySignal.algo_version == version,
            ],
            key_columns=["trade_date", "ts_code", "signal_type", "algo_version"],
            update_columns=[
                "score",
                "opportunity_score",
                "reason_codes",
                "payload",
                "calc_version",
                "config_hash",
                "calc_run_id",
                "calculated_at",
            ],
        )
        self.db.commit()
        logger.info(
            "recalculated trend states start={} end={} states={} signals={}",
            start,
            end,
            state_count,
            signal_count,
        )
        return {"states": state_count, "signals": signal_count}

    def _read_factors(self, start: date, end: date) -> pd.DataFrame:
        hash_value = config_hash(self.settings.strategy)
        stmt = (
            select(
                StockFactorDaily.trade_date,
                StockFactorDaily.ts_code,
                StockFactorDaily.adj_close,
                StockFactorDaily.ma20,
                StockFactorDaily.ma60,
                StockFactorDaily.ma120,
                StockFactorDaily.return20,
                StockFactorDaily.ma20_slope5,
                StockFactorDaily.ma60_slope10,
                StockFactorDaily.atr20_pct,
                StockFactorDaily.amount_ratio20,
                StockFactorDaily.prev_high20,
                StockFactorDaily.breakout20,
                StockFactorDaily.breakout60,
                StockFactorDaily.cross_above_ma20,
                StockFactorDaily.cross_above_ma60,
                StockFactorDaily.higher_low,
                StockFactorDaily.higher_low_pct,
                StockFactorDaily.drawdown_high60,
                StockFactorDaily.max_drawdown60,
                StockFactorDaily.trend_efficiency20,
                StockFactorDaily.rps20,
                StockFactorDaily.rps60,
                StockFactorDaily.rps120,
                StockFactorDaily.rps20_delta5,
                StockFactorDaily.rps60_delta5,
                StockFactorDaily.eligible,
            )
            .where(
                StockFactorDaily.trade_date >= start,
                StockFactorDaily.trade_date <= end,
                StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
                StockFactorDaily.config_hash == hash_value,
            )
            .order_by(StockFactorDaily.ts_code, StockFactorDaily.trade_date)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())

    def _read_market(self, start: date, end: date) -> pd.DataFrame:
        hash_value = config_hash(self.settings.strategy)
        stmt = (
            select(MarketDaily.trade_date, MarketDaily.market_score)
            .where(
                MarketDaily.trade_date >= start,
                MarketDaily.trade_date <= end,
                MarketDaily.calc_version == MARKET_CALC_VERSION,
                MarketDaily.config_hash == hash_value,
            )
            .order_by(MarketDaily.trade_date)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())

    def _read_sector_members(self) -> pd.DataFrame:
        stmt = select(
            SectorMember.sector_id,
            SectorMember.ts_code,
            SectorMember.valid_from,
            SectorMember.valid_to,
            SectorMember.is_latest,
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())

    def _read_sector_factors(self, start: date, end: date) -> pd.DataFrame:
        hash_value = config_hash(self.settings.strategy)
        stmt = (
            select(
                SectorFactorDaily.trade_date,
                SectorFactorDaily.sector_id,
                SectorFactorDaily.heat_score,
                SectorFactorDaily.heat_momentum3,
            )
            .where(
                SectorFactorDaily.trade_date >= start,
                SectorFactorDaily.trade_date <= end,
                SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
                SectorFactorDaily.config_hash == hash_value,
            )
            .order_by(SectorFactorDaily.trade_date, SectorFactorDaily.sector_id)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())

    def _read_previous_states(
        self, start: date, target_start: date, algo_version: str
    ) -> pd.DataFrame:
        hash_value = config_hash(self.settings.strategy)
        stmt = (
            select(
                StockStateDaily.trade_date,
                StockStateDaily.ts_code,
                StockStateDaily.state,
                StockStateDaily.state_day_count,
            )
            .where(
                StockStateDaily.trade_date >= start,
                StockStateDaily.trade_date < target_start,
                StockStateDaily.algo_version == algo_version,
                StockStateDaily.calc_version == TREND_CALC_VERSION,
                StockStateDaily.config_hash == hash_value,
            )
            .order_by(StockStateDaily.ts_code, StockStateDaily.trade_date)
        )
        return pd.DataFrame(self.db.execute(stmt).mappings().all())


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            cleaned[key] = value
        elif pd.isna(value):
            cleaned[key] = None
        elif hasattr(value, "item"):
            cleaned[key] = value.item()
        else:
            cleaned[key] = value
    return cleaned


def _ensure_unique_rows(rows: list[dict[str, Any]], key_columns: list[str]) -> None:
    seen: set[tuple[Any, ...]] = set()
    duplicates: list[tuple[Any, ...]] = []
    for row in rows:
        key = tuple(row.get(column) for column in key_columns)
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        sample = ", ".join(str(key) for key in duplicates[:5])
        raise ValueError(
            "duplicate stock_state_daily rows generated for "
            f"{key_columns}: {sample}; check sector membership context"
        )
