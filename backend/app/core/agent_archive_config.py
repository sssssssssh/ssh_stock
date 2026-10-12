from pydantic import BaseModel, ConfigDict, Field


class AgentArchiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_payload_bytes: int = Field(default=65536, ge=1024, le=65536)
    max_turn_bytes: int = Field(default=655360, ge=65536, le=1048576)
    max_tool_calls: int = Field(default=8, ge=1, le=16)
    max_bindings: int = Field(default=64, ge=1, le=100)
    verify_timeout_seconds: int = Field(default=5, ge=1, le=15)
