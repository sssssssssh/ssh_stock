from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.agent_llm_config import AgentLLMConfig


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_version: str = "m16.1-v1"
    mode: Literal["tools_only", "llm_chat"] = "tools_only"
    llm_enabled: bool = False
    llm: AgentLLMConfig = Field(default_factory=AgentLLMConfig)
    max_output_bytes: int = Field(default=65_536, gt=0, le=65_536)
    max_coverage_datasets: int = Field(default=32, gt=0, le=128)
    max_evidence_refs: int = Field(default=64, gt=0, le=256)
    max_warnings: int = Field(default=128, gt=0, le=512)
    default_timeout_seconds: int = Field(default=5, gt=0, le=30)
    max_tool_timeout_seconds: int = Field(default=30, gt=0, le=300)
    statement_timeout_ms: int = Field(default=5000, gt=0, le=30_000)

    @model_validator(mode="after")
    def validate_resource_budgets(self) -> "AgentConfig":
        expected_mode = "llm_chat" if self.llm_enabled else "tools_only"
        if self.mode != expected_mode:
            raise ValueError(
                f"agent mode must be {expected_mode!r} when llm_enabled={self.llm_enabled}"
            )
        if self.default_timeout_seconds > self.max_tool_timeout_seconds:
            raise ValueError("default tool timeout must not exceed the global timeout cap")
        if self.statement_timeout_ms > self.default_timeout_seconds * 1000:
            raise ValueError(
                "database statement timeout must not exceed the default tool budget"
            )
        if self.max_evidence_refs < self.max_coverage_datasets:
            raise ValueError(
                "evidence limit must cover one reference per coverage dataset"
            )
        return self
