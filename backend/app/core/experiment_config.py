from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["experiment_v1"]
    search_method: Literal["GRID"]
    max_trials: int = Field(gt=0)
    max_values_per_parameter: int = Field(gt=0)
