from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TRADE_VERSION = "trade_v1"


class PerformanceTradeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["trade_v1"]
    pnl_zero_epsilon_cny: Decimal = Field(ge=0)
    short_sample_warning_trade_days: int = Field(gt=0)
