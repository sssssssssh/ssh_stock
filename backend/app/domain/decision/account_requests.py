from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.core.paper_config import PaperRiskConfig
from app.domain.decision.requests import Code, PaperRequest


class CreatePaperAccount(PaperRequest):
    name: str = Field(min_length=1, max_length=80)
    initial_cash: Decimal = Field(gt=0, max_digits=24, decimal_places=4)
    benchmark_code: Code = "000300.SH"
    first_trade_date: date | None = None
    risk: PaperRiskConfig | None = None

    @field_validator("initial_cash", mode="before")
    @classmethod
    def decimal_cash(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("cash must be a decimal string")
        return value

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class AdvancePaperAccount(PaperRequest):
    trade_date: date


class ReviewPaperAccount(PaperRequest):
    asof_date: date
    window_days: Literal[1, 5, 20] = 1
