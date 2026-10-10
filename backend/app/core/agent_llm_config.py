from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class AgentLLMConfig(BaseModel):
    """Bounded runtime configuration for the optional M16.2 chat provider."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["openai_compatible"] = "openai_compatible"
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=128)
    base_url: AnyHttpUrl = "https://api.openai.com/v1"
    api_key_env: str = Field(
        default="OPENAI_API_KEY",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_]*$",
    )
    request_timeout_seconds: int = Field(default=20, ge=1, le=60)
    max_output_tokens: int = Field(default=1200, ge=1, le=8192)
    temperature: float = Field(default=0.1, ge=0, le=1)
    max_provider_retries: int = Field(default=1, ge=0, le=2)
    max_tool_rounds: int = Field(default=3, ge=1, le=5)
    max_tool_calls_total: int = Field(default=8, ge=1, le=16)
    max_tool_calls_per_round: int = Field(default=4, ge=1, le=8)
    max_context_messages: int = Field(default=12, ge=2, le=24)
    max_user_message_chars: int = Field(default=4000, ge=1, le=8000)
    max_answer_chars: int = Field(default=8000, ge=1, le=16_000)
    max_total_deadline_seconds: int = Field(default=45, ge=1, le=120)

    @model_validator(mode="after")
    def validate_budgets(self) -> "AgentLLMConfig":
        if self.max_tool_calls_per_round > self.max_tool_calls_total:
            raise ValueError("per-round tool limit must not exceed total tool limit")
        if self.request_timeout_seconds > self.max_total_deadline_seconds:
            raise ValueError("provider timeout must not exceed the total deadline")
        return self
