from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PERFORMANCE_VERSION = "performance_v1"


class PerformanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["performance_v1"]
    annualization_trade_days: int = Field(gt=0)
    short_sample_warning_trade_days: int = Field(gt=0)
    zero_return_epsilon: Decimal = Field(ge=0)
