from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatCitation(ChatDTO):
    marker: str
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
    observed_at: datetime | None = None


ClaimType = Literal["FACT", "INFERENCE", "COMPARISON"]
AnswerStatus = Literal["COMPLETED", "PARTIAL_VERIFIED", "INSUFFICIENT_EVIDENCE"]
ComparisonType = Literal[
    "SAME_DATE_RANKING",
    "ENTITY_OVER_TIME",
    "INDEPENDENT_BACKTESTS",
    "TRAIN_VS_OOS",
]
SampleRole = Literal["TRAIN", "OOS", "LIVE", "UNKNOWN"]
ComparisonState = Literal["COMPARABLE", "CONTEXT_REQUIRED", "INCOMPATIBLE"]
LineageStatus = Literal["VERIFIED", "UNVERIFIABLE", "MISMATCH"]
InferenceHypothesis = Literal[
    "POSSIBLE_ASSOCIATION",
    "POSSIBLE_REGIME_SENSITIVITY",
    "POSSIBLE_COST_SENSITIVITY",
    "POSSIBLE_STABILITY_CONCERN",
]
InferenceUncertainty = Literal[
    "CAUSALITY_NOT_ESTABLISHED",
    "SAMPLE_SCOPE_LIMITED",
    "MARKET_REGIME_MAY_DIFFER",
    "UNOBSERVED_FACTORS_REMAIN",
]
InferenceLimitation = Literal[
    "HISTORICAL_EVIDENCE_ONLY",
    "NOT_A_RETURN_GUARANTEE",
    "NOT_A_TRADING_RECOMMENDATION",
    "COMPARISON_CONTEXT_REQUIRED",
]


class LineageDecision(ChatDTO):
    status: LineageStatus
    study_id: str | None = None
    window_no: int | None = Field(default=None, ge=1)
    train_run_id: str | None = None
    oos_run_id: str | None = None
    validation_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list, max_length=16)
    policy_version: str = "m16.2.2-lineage-v1"


class StructuredInference(ChatDTO):
    hypothesis: InferenceHypothesis
    supporting_claim_ids: list[str] = Field(min_length=1, max_length=8)
    uncertainties: list[InferenceUncertainty] = Field(min_length=1, max_length=8)
    limitations: list[InferenceLimitation] = Field(min_length=1, max_length=8)


class StructuredFact(ChatDTO):
    path: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^records\.\d+(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|\d+))+$",
    )
    value: str | int | float
    unit: str = Field(min_length=1, max_length=32)
    trade_date: date
    entity: str = Field(min_length=1, max_length=160)
    sample_role: SampleRole = "UNKNOWN"

    @field_validator("value")
    @classmethod
    def reject_boolean_value(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("structured fact value must not be boolean")
        return value


class StructuredClaim(ChatDTO):
    claim_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    claim_type: ClaimType
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=16)
    structured_facts: list[StructuredFact] = Field(default_factory=list, max_length=24)
    quality_status: Literal["PASS", "WARNING", "UNKNOWN"] = "UNKNOWN"
    comparison_type: ComparisonType | None = None
    inference: StructuredInference | None = None
    lineage_decision: LineageDecision | None = None
    comparison_state: ComparisonState | None = None
    reason_codes: list[str] = Field(default_factory=list, max_length=24)
    verified_fact_refs: list[str] = Field(default_factory=list, max_length=24)
    policy_version: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_claim_shape(self) -> StructuredClaim:
        if self.claim_type == "COMPARISON" and self.comparison_type is None:
            raise ValueError("comparison claim requires comparison_type")
        if self.claim_type != "COMPARISON" and self.comparison_type is not None:
            raise ValueError("comparison_type is only valid for comparison claims")
        if self.claim_type != "INFERENCE" and self.inference is not None:
            raise ValueError("inference payload is only valid for inference claims")
        return self


class RejectedClaim(ChatDTO):
    claim_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    claim_type: ClaimType
    reason_codes: list[str] = Field(min_length=1, max_length=24)
    comparison_state: ComparisonState | None = None
    policy_version: str | None = Field(default=None, max_length=64)


class ChatToolCallSummary(ChatDTO):
    tool_call_id: str
    tool_name: str
    status: str
    duration_ms: int = Field(ge=0)
    error_code: str | None = None
    cache_reused: bool = False


class ChatUsage(ChatDTO):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    provider_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)

    def add_provider_usage(
        self, prompt_tokens: int | None, completion_tokens: int | None
    ) -> None:
        self.provider_calls += 1
        self.prompt_tokens += max(0, prompt_tokens or 0)
        self.completion_tokens += max(0, completion_tokens or 0)


class ChatAnswer(ChatDTO):
    chat_id: uuid.UUID
    message_id: uuid.UUID
    status: AnswerStatus = "COMPLETED"
    answer_status: AnswerStatus = "COMPLETED"
    answer: str
    claims: list[StructuredClaim] = Field(default_factory=list)
    verified_claims: list[StructuredClaim] = Field(default_factory=list)
    rejected_claims: list[RejectedClaim] = Field(default_factory=list)
    needs_clarification: bool = False
    citations: list[ChatCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_calls: list[ChatToolCallSummary] = Field(default_factory=list)
    usage: ChatUsage = Field(default_factory=ChatUsage)
    trace_id: uuid.UUID

    @model_validator(mode="after")
    def normalize_compatibility_fields(self) -> ChatAnswer:
        if "answer_status" not in self.model_fields_set:
            self.answer_status = self.status
        elif "status" not in self.model_fields_set:
            self.status = self.answer_status
        elif self.status != self.answer_status:
            raise ValueError("status and answer_status must match")
        if "verified_claims" not in self.model_fields_set:
            self.verified_claims = list(self.claims)
        elif "claims" not in self.model_fields_set:
            self.claims = list(self.verified_claims)
        return self


class ChatSessionSummary(ChatDTO):
    chat_id: uuid.UUID
    title: str
    status: Literal["ACTIVE", "ARCHIVED"]
    created_at: datetime
    updated_at: datetime


class ChatMessageView(ChatDTO):
    message_id: uuid.UUID
    role: Literal["USER", "ASSISTANT"]
    content: str
    status: Literal["COMPLETED", "FAILED"]
    sequence_no: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class StructuredAnswerDraft(ChatDTO):
    answer: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    claims: list[StructuredClaim] | None = Field(default=None, max_length=32)
    warnings: list[str] = Field(default_factory=list, max_length=128)
    needs_clarification: bool = False
