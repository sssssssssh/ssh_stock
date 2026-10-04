from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

PERIOD_VERSION = "period_v1"
ANALYTICS_READ_SCHEMA_VERSION = "analytics_read_v1"


class PerformancePeriodConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["period_v1"]
    period_types: tuple[Literal["MONTH", "YEAR"], ...]
    excess_return_method: Literal["RELATIVE"]
    closed_episode_attribution: Literal["EXIT_DATE"]

    @field_validator("period_types")
    @classmethod
    def validate_period_types(
        cls, value: tuple[Literal["MONTH", "YEAR"], ...]
    ) -> tuple[Literal["MONTH", "YEAR"], ...]:
        if value != ("MONTH", "YEAR"):
            raise ValueError("period_v1 requires period_types [MONTH, YEAR] in order")
        return value
