from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_version: str = "m16.1-v1"
    mode: Literal["tools_only"] = "tools_only"
    llm_enabled: Literal[False] = False
    max_output_bytes: int = Field(default=65_536, ge=1024, le=65_536)
    default_timeout_seconds: int = Field(default=5, ge=1, le=30)
    statement_timeout_ms: int = Field(default=5000, ge=100, le=30_000)
