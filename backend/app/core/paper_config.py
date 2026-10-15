from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.core.portfolio_config import AllowedOpportunityStage


class StrictPaperModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class PaperRiskConfig(StrictPaperModel):
    max_positions: int = Field(default=10, ge=1, le=100, strict=True)
    max_single_position_weight: Decimal = Field(
        default=Decimal("0.10"), gt=0, le=1, max_digits=12, decimal_places=8
    )
    min_cash_ratio: Decimal = Field(
        default=Decimal("0.02"), ge=0, lt=1, max_digits=12, decimal_places=8
    )
    max_new_positions_per_day: int = Field(default=2, ge=1, le=100, strict=True)
    max_sector_weight: Decimal = Field(
        default=Decimal("0.30"), gt=0, le=1, max_digits=12, decimal_places=8
    )
    max_theme_weight: Decimal = Field(
        default=Decimal("0.30"), gt=0, le=1, max_digits=12, decimal_places=8
    )
    max_daily_turnover: Decimal = Field(
        default=Decimal("0.50"), gt=0, le=2, max_digits=12, decimal_places=8
    )

    @field_validator(
        "max_single_position_weight", "min_cash_ratio", "max_sector_weight",
        "max_theme_weight", "max_daily_turnover",
    )
    @classmethod
    def bounded_decimal_scale(cls, value):
        if value.as_tuple().exponent < -8:
            raise ValueError("risk limits support at most eight decimal places")
        return value

    @model_validator(mode="after")
    def consistent_limits(self):
        if self.max_single_position_weight > 1 - self.min_cash_ratio:
            raise ValueError("single position limit exceeds investable assets")
        if self.max_new_positions_per_day > self.max_positions:
            raise ValueError("new positions limit exceeds max_positions")
        return self


class PaperPolicyConfig(StrictPaperModel):
    version: Literal["m17-paper-policy-v1"] = "m17-paper-policy-v1"
    mode: Literal["PAPER"] = "PAPER"
    approval_mode: Literal["MANUAL_CONFIRM"] = "MANUAL_CONFIRM"
    market_data_mode: Literal["POST_EOD_SIMULATED_OPEN"] = "POST_EOD_SIMULATED_OPEN"
    pending_order_policy: Literal["REJECT_CONFLICTING_PENDING"] = "REJECT_CONFLICTING_PENDING"
    blocked_order_policy: Literal["SKIP_NO_RETRY"] = "SKIP_NO_RETRY"
    corporate_action_policy: Literal["FAIL_CLOSED"] = "FAIL_CLOSED"
    risk: PaperRiskConfig = Field(default_factory=PaperRiskConfig)


class DecisionConfig(StrictPaperModel):
    version: Literal["m17-decision-rule-v1"] = "m17-decision-rule-v1"
    daily_observation_enabled: StrictBool = False
    top_n: int = Field(default=20, ge=1, le=100)
    min_score: Decimal = Field(default=Decimal("70"), ge=0, le=100)
    allowed_stages: tuple[AllowedOpportunityStage, ...] = (
        "LEFT_WATCH",
        "LEFT_REVERSAL",
        "RIGHT_SIDE_NEW",
        "RIGHT_SIDE",
        "TREND",
        "STRONG_TREND",
    )
    max_source_rows: int = Field(default=20000, ge=100, le=100000)

    @model_validator(mode="after")
    def unique_stages(self):
        if not self.allowed_stages or len(set(self.allowed_stages)) != len(self.allowed_stages):
            raise ValueError("decision stages must be nonempty and unique")
        return self


class PaperRuntimeConfig(StrictPaperModel):
    enabled: StrictBool = False
    auto_advance: StrictBool = False
    auto_approve: Literal[False] = False
    scheduler_interval_seconds: int = Field(default=300, ge=60, le=3600)
    max_history_bytes: int = Field(default=32 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    policy: PaperPolicyConfig = Field(default_factory=PaperPolicyConfig)
    decision: DecisionConfig = Field(default_factory=DecisionConfig)

    @model_validator(mode="after")
    def enabled_before_automation(self):
        if not self.enabled and (self.auto_advance or self.decision.daily_observation_enabled):
            raise ValueError("paper must be enabled before enabling automation")
        return self
