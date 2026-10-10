from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    content_hash: str | None = None


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
    status: Literal["COMPLETED", "INSUFFICIENT_EVIDENCE"]
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_calls: list[ChatToolCallSummary] = Field(default_factory=list)
    usage: ChatUsage = Field(default_factory=ChatUsage)
    trace_id: uuid.UUID


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
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
