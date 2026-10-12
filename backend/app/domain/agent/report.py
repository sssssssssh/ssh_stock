from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.agent.chat import ChatCitation, RejectedClaim, StructuredClaim

ReportType = Literal["market_review", "opportunity_review", "strategy_review", "oos_review"]
ReportAnswerStatus = Literal["COMPLETED", "PARTIAL_VERIFIED"]
ComparisonState = Literal["COMPARABLE", "CONTEXT_REQUIRED", "INCOMPATIBLE"]
ChartType = Literal["line", "bar", "table"]
ComparisonIntent = Literal[
    "AUTO",
    "SAME_ENTITY_OVER_TIME",
    "CROSS_ENTITY_SAME_DATE",
    "INDEPENDENT_BACKTESTS",
    "TRAIN_VS_OOS",
]


class ReportDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportChart(ReportDTO):
    chart_id: str = Field(min_length=1, max_length=64)
    chart_type: ChartType
    title: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=32)
    columns: list[str] = Field(default_factory=list, max_length=16)
    rows: list[list[str]] = Field(default_factory=list)
    metric_id: str | None = None
    trade_date: date | None = None
    sample_role: str | None = None
    entity_kind: str | None = None


class ReportSection(ReportDTO):
    section_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    claim_ids: list[str] = Field(default_factory=list, max_length=50)
    items: list[str] = Field(default_factory=list, max_length=100)


class ReportEvidenceIdentity(ReportDTO):
    evidence_id: str
    evidence_version: Literal["v1", "v2"]
    tool_name: str
    entity_id: str
    as_of_date: date | None = None
    report_id: str | None = None
    calc_run_id: str | None = None
    calc_version: str | None = None
    algo_version: str | None = None
    config_hash: str | None = None
    source_hash: str | None = None
    content_hash: str | None = None


class ReportSourceContract(ReportDTO):
    snapshot_level: Literal["CLAIM_SNAPSHOT_ONLY"] = "CLAIM_SNAPSHOT_ONLY"
    report_version: str = "m16.4-v1"
    comparison_policy_version: str = "m16.2.2-comparison-v1"
    tool_names: list[str] = Field(default_factory=list, max_length=16)
    evidence_versions: list[str] = Field(default_factory=list, max_length=8)
    evidence_identities: list[ReportEvidenceIdentity] = Field(default_factory=list, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=16)


class ResearchReportSnapshot(ReportDTO):
    schema_version: str = "m16.4-report-snapshot-v1"
    snapshot_level: Literal["CLAIM_SNAPSHOT_ONLY"] = "CLAIM_SNAPSHOT_ONLY"
    report_type: ReportType
    title: str = Field(min_length=1, max_length=160)
    as_of_date: date | None = None
    source_answer_status: ReportAnswerStatus
    source_chat_id: uuid.UUID
    source_message_id: uuid.UUID
    source_turn_id: uuid.UUID | None = None
    claims: list[StructuredClaim] = Field(min_length=1, max_length=50)
    rejected_claims: list[RejectedClaim] = Field(default_factory=list, max_length=50)
    citations: list[ChatCitation] = Field(default_factory=list, max_length=100)
    sections: list[ReportSection] = Field(default_factory=list, max_length=12)
    charts: list[ReportChart] = Field(default_factory=list, max_length=8)
    warnings: list[str] = Field(default_factory=list, max_length=128)
    source_contract_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CreateResearchReport(ReportDTO):
    source_chat_id: uuid.UUID
    source_message_id: uuid.UUID
    report_type: ReportType
    request_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    parent_report_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("request_id must not be blank")
        return normalized


class ResearchReportView(ReportDTO):
    report_id: uuid.UUID
    report_type: ReportType
    report_version: str
    title: str
    as_of_date: date | None
    source_chat_id: uuid.UUID
    source_message_id: uuid.UUID
    source_turn_id: uuid.UUID | None
    parent_report_id: uuid.UUID | None
    source_answer_status: ReportAnswerStatus
    answer_status: ReportAnswerStatus
    snapshot_level: Literal["CLAIM_SNAPSHOT_ONLY"] = "CLAIM_SNAPSHOT_ONLY"
    read_only_research: bool = True
    snapshot_hash: str
    snapshot: ResearchReportSnapshot
    source_contract: ReportSourceContract
    archived_at: datetime | None
    created_at: datetime


class ResearchReportSummary(ReportDTO):
    report_id: uuid.UUID
    report_type: ReportType
    report_version: str
    title: str
    source_chat_id: uuid.UUID
    source_message_id: uuid.UUID
    as_of_date: date | None
    source_answer_status: ReportAnswerStatus
    snapshot_hash: str
    archived_at: datetime | None
    created_at: datetime


class CreateReportComparison(ReportDTO):
    left_report_id: uuid.UUID
    right_report_id: uuid.UUID
    request_id: str = Field(min_length=1, max_length=128)
    comparison_intent: ComparisonIntent = "AUTO"

    @field_validator("request_id")
    @classmethod
    def normalize_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("request_id must not be blank")
        return normalized

    @model_validator(mode="after")
    def reports_must_differ(self) -> CreateReportComparison:
        if self.left_report_id == self.right_report_id:
            raise ValueError("left and right reports must differ")
        return self


class ReportComparisonView(ReportDTO):
    comparison_id: uuid.UUID
    left_report_id: uuid.UUID
    right_report_id: uuid.UUID
    policy_version: str
    state: ComparisonState
    reason_codes: list[str] = Field(default_factory=list)
    result: dict[str, Any]
    left_snapshot_hash: str
    right_snapshot_hash: str
    comparison_hash: str
    created_at: datetime
    display_safety: dict[str, Any] | None = None
    display_result: dict[str, Any] | None = None
