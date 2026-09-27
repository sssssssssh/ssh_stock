from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TradingCostConfig(StrictExecutionConfig):
    commission_rate: Decimal = Field(ge=0)
    minimum_commission_cny: Decimal = Field(ge=0)
    stamp_tax_sell_rate: Decimal = Field(ge=0)
    slippage_bps: Decimal = Field(ge=0)


class ExecutionConfig(StrictExecutionConfig):
    version: Literal["execution_v1"]
    mode: Literal["SIMULATED"]
    signal_time: Literal["CLOSE"]
    entry_basis: Literal["NEXT_OPEN"]
    exit_basis: Literal["NEXT_OPEN"]
    board_lot: int = Field(gt=0)
    t_plus_one: bool
    pending_order_max_trade_days: int = Field(gt=0)
    trading_cost: TradingCostConfig
