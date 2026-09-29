from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.execution import (
    ExecutionMarketBatch,
    MarketExecutionSnapshot,
    OrderIntent,
)
from app.models.market_data import (
    StockBasic,
    StockDaily,
    StockLimitDaily,
    StockTradeStatusDaily,
)
from app.services.analysis_identity import (
    TRADE_STATUS_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.execution.contracts import ExecutionSourceStatus
from app.services.execution.price import is_positive_price, to_decimal


class ExecutionMarketDataProvider:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def load(
        self,
        trade_date: date,
        intents: Sequence[OrderIntent],
    ) -> ExecutionMarketBatch:
        codes = tuple(sorted({intent.ts_code for intent in intents}))
        if not codes:
            return ExecutionMarketBatch(
                trade_date=trade_date,
                source_status=ExecutionSourceStatus.READY.value,
                source_reason=None,
                snapshots=(),
            )

        raw_rows = self._rows_by_code(
            select(StockDaily).where(
                StockDaily.trade_date == trade_date,
                StockDaily.ts_code.in_(codes),
            )
        )
        strategy_hash = analysis_strategy_hash(self.settings.strategy)
        status_rows = self._rows_by_code(
            select(StockTradeStatusDaily).where(
                StockTradeStatusDaily.trade_date == trade_date,
                StockTradeStatusDaily.ts_code.in_(codes),
                StockTradeStatusDaily.calc_version == TRADE_STATUS_CALC_VERSION,
                StockTradeStatusDaily.config_hash == strategy_hash,
            )
        )
        limit_rows = self._rows_by_code(
            select(StockLimitDaily).where(
                StockLimitDaily.trade_date == trade_date,
                StockLimitDaily.ts_code.in_(codes),
            )
        )
        basic_rows = self._rows_by_code(
            select(StockBasic).where(StockBasic.ts_code.in_(codes))
        )

        missing: dict[str, list[str]] = {
            "stock_daily": [],
            "trade_status": [],
            "stock_limit": [],
            "stock_basic": [],
        }
        snapshots: list[MarketExecutionSnapshot] = []
        for code in codes:
            raw = raw_rows.get(code)
            status = status_rows.get(code)
            limit = limit_rows.get(code)
            basic = basic_rows.get(code)
            open_price = to_decimal(raw.open) if raw is not None else None
            if raw is None or not is_positive_price(open_price):
                missing["stock_daily"].append(code)
            if status is None:
                missing["trade_status"].append(code)
            if limit is None:
                missing["stock_limit"].append(code)
            if (
                basic is None
                or not basic.exchange
                or not basic.market
            ):
                missing["stock_basic"].append(code)
            snapshots.append(
                MarketExecutionSnapshot(
                    trade_date=trade_date,
                    ts_code=code,
                    exchange=basic.exchange if basic is not None else None,
                    market=basic.market if basic is not None else None,
                    basic_present=basic is not None,
                    raw_present=raw is not None,
                    open_price=open_price,
                    close_price=to_decimal(raw.close) if raw is not None else None,
                    status_present=status is not None,
                    is_active=status.is_active if status is not None else None,
                    is_suspended=(
                        status.is_suspended if status is not None else None
                    ),
                    tradable=status.tradable if status is not None else None,
                    limit_present=limit is not None,
                    up_limit=(
                        to_decimal(limit.up_limit) if limit is not None else None
                    ),
                    down_limit=(
                        to_decimal(limit.down_limit) if limit is not None else None
                    ),
                )
            )
        missing_by_layer = {
            layer: tuple(values) for layer, values in missing.items() if values
        }
        ready = not missing_by_layer
        return ExecutionMarketBatch(
            trade_date=trade_date,
            source_status=(
                ExecutionSourceStatus.READY.value
                if ready
                else ExecutionSourceStatus.INCOMPLETE.value
            ),
            source_reason=None if ready else "EXECUTION_SOURCE_INCOMPLETE",
            snapshots=tuple(snapshots),
            missing_by_layer=missing_by_layer,
        )

    def _rows_by_code(self, statement) -> dict[str, object]:
        rows = self.db.execute(statement).scalars().all()
        return {row.ts_code: row for row in rows}
