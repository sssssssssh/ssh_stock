from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.agent.chat_errors import AgentChatError


class LLMDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolCall(LLMDTO):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any]


class ChatMessage(LLMDTO):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_role_shape(self) -> ChatMessage:
        if self.role in {"system", "user"}:
            if not self.content or self.tool_call_id or self.tool_calls:
                raise ValueError(f"invalid {self.role} message")
        elif self.role == "tool":
            if self.content is None or not self.tool_call_id or self.tool_calls:
                raise ValueError("invalid tool message")
        elif bool(self.content) == bool(self.tool_calls):
            raise ValueError("assistant message requires exactly one of content or tool_calls")
        return self


class LLMTool(LLMDTO):
    name: str
    description: str
    parameters: dict[str, Any]


class LLMUsage(LLMDTO):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)


class LLMResponse(LLMDTO):
    final_text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    provider_request_id: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)

    @model_validator(mode="after")
    def validate_response_shape(self) -> LLMResponse:
        if bool(self.final_text) == bool(self.tool_calls):
            raise ValueError("LLM response requires exactly one of final_text or tool_calls")
        return self


class ProviderError(AgentChatError):
    pass


class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[LLMTool],
        *,
        timeout: float,
        request_id: str,
    ) -> LLMResponse: ...
