from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RISK_VERSION = "risk_v1"


class PerformanceRiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["risk_v1"]
    risk_free_rate_annual: Decimal = Field(gt=-1)
    minimum_observations: int = Field(ge=2)
    short_sample_warning_trade_days: int = Field(gt=0)
    zero_denominator_epsilon: Decimal = Field(ge=0)
