from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WALK_FORWARD_VERSION = "walk_forward_v1"


class WalkForwardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["walk_forward_v1"]
    exchange: str
    minimum_windows: int = Field(ge=2)
    max_windows: int = Field(ge=2)
    max_actions_per_advance: int = Field(gt=0)
    minimum_stitched_oos_observations: int = Field(ge=2)
    short_oos_warning_trade_days: int = Field(gt=0)

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("exchange must be nonempty")
        return normalized

    @model_validator(mode="after")
    def validate_window_limits(self) -> "WalkForwardConfig":
        if self.max_windows < self.minimum_windows:
            raise ValueError("max_windows must be at least minimum_windows")
        return self
