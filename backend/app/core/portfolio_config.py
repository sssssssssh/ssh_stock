from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AllowedOpportunityStage = Literal[
    "LEFT_WATCH",
    "LEFT_REVERSAL",
    "RIGHT_SIDE_NEW",
    "RIGHT_SIDE",
    "TREND",
    "STRONG_TREND",
]


class StrictPortfolioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateConfig(StrictPortfolioConfig):
    source: Literal["STOCK_OPPORTUNITY_DAILY"]
    allowed_stages: list[AllowedOpportunityStage] = Field(min_length=1)
    ranking_field: Literal["opportunity_score"]
    ranking_direction: Literal["DESC"]
    min_score: Decimal = Field(ge=0)
    top_n: int = Field(gt=0)

    @field_validator("allowed_stages")
    @classmethod
    def validate_unique_stages(
        cls, value: list[AllowedOpportunityStage]
    ) -> list[AllowedOpportunityStage]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_stages must not contain duplicates")
        return value


class PortfolioConstructionConfig(StrictPortfolioConfig):
    weighting: Literal["EQUAL"]
    max_positions: int = Field(gt=0)
    max_single_position_weight: Decimal = Field(gt=0, le=1)
    min_cash_ratio: Decimal = Field(ge=0, lt=1)
    max_new_positions_per_day: int = Field(gt=0)
    rebalance_frequency: Literal["DAILY"]


class PortfolioConfig(StrictPortfolioConfig):
    version: Literal["portfolio_v1"]
    account_mode: Literal["BACKTEST", "PAPER", "LIVE"]
    initial_cash_cny: Decimal = Field(gt=0)
    benchmark_code: str = Field(min_length=1)
    candidate: CandidateConfig
    construction: PortfolioConstructionConfig
