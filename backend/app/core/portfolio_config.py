from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictPortfolioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateConfig(StrictPortfolioConfig):
    source: Literal["STOCK_OPPORTUNITY_DAILY"]
    allowed_stages: list[str] = Field(min_length=1)
    ranking_field: Literal["opportunity_score"]
    ranking_direction: Literal["DESC"]
    min_score: Decimal = Field(ge=0)
    top_n: int = Field(gt=0)


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
