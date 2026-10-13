from pydantic import BaseModel, ConfigDict, Field


class AgentFrozenContractConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_contract_bytes: int = Field(default=131072, ge=1024, le=131072)
    max_turn_bytes: int = Field(default=1048576, ge=65536, le=1048576)
    max_contracts: int = Field(default=100, ge=1, le=800)
    max_trade_dates: int = Field(default=5000, ge=1, le=10000)
    verify_timeout_seconds: int = Field(default=5, ge=1, le=15)
