from __future__ import annotations

import uuid
from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataCoverageInput(AgentDTO):
    start_date: Date
    end_date: Date

    @model_validator(mode="after")
    def validate_range(self) -> DataCoverageInput:
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        if (self.end_date - self.start_date).days > 365:
            raise ValueError("date range must not exceed 366 calendar days")
        return self


class MarketSnapshotInput(AgentDTO):
    trade_date: Date | None = None


class SectorTopInput(AgentDTO):
    trade_date: Date | None = None
    limit: int = Field(default=10, ge=1, le=20)


class ThemeTopInput(AgentDTO):
    trade_date: Date | None = None
    limit: int = Field(default=10, ge=1, le=20)


OpportunityStage = Literal[
    "LEFT_WATCH",
    "LEFT_REVERSAL",
    "RIGHT_SIDE_NEW",
    "RIGHT_SIDE",
    "TREND",
    "STRONG_TREND",
]


class OpportunityListInput(AgentDTO):
    trade_date: Date | None = None
    stage: OpportunityStage | None = None
    limit: int = Field(default=20, ge=1, le=30)


class BacktestSummaryInput(AgentDTO):
    run_id: uuid.UUID


class PerformanceSummaryInput(AgentDTO):
    run_id: uuid.UUID | None = None
    report_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_selector(self) -> PerformanceSummaryInput:
        if (self.run_id is None) == (self.report_id is None):
            raise ValueError("provide exactly one of run_id or report_id")
        return self


class WalkForwardSummaryInput(AgentDTO):
    study_id: uuid.UUID
    validation_id: uuid.UUID


class EvidenceRef(AgentDTO):
    evidence_id: str
    evidence_version: Literal["v1", "v2"] = "v2"
    layer: Literal["DATA", "FACTOR_TREND", "STRATEGY_VALIDATION"]
    source_type: Literal["dataset", "derived_record", "report"]
    entity_id: str
    trade_date: Date | None = None
    source_record_id: str | None = None
    calc_version: str | None = None
    algo_version: str | None = None
    config_hash: str | None = None
    source_hash: str | None = None
    report_id: str | None = None
    calc_run_id: str | None = None
    content_hash: str | None = None
    observed_at: datetime | None = None
    quality_status: Literal["PASS", "WARNING", "ERROR", "UNKNOWN"] = "UNKNOWN"
    limitations: list[str] = Field(default_factory=list)


class Readiness(AgentDTO):
    ready: bool
    code: str
    details: dict[str, Any] = Field(default_factory=dict)


class AgentToolResult(AgentDTO):
    tool_name: str
    tool_version: str = Field(default="1.0", pattern=r"^[1-9]\d*\.\d+$")
    status: str
    as_of_date: Date | None = None
    identity: dict[str, Any] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    readiness: Readiness


def json_safe(value: Any) -> Any:
    """Serialize precision-bearing values without leaking ORM instances."""
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, (Date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
