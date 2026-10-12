from pydantic import BaseModel, ConfigDict, Field


class AgentReportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_snapshot_bytes: int = Field(default=262_144, ge=16_384, le=1_048_576)
    max_claims: int = Field(default=50, ge=1, le=100)
    max_citations: int = Field(default=100, ge=1, le=256)
    max_sections: int = Field(default=12, ge=1, le=24)
    max_charts: int = Field(default=8, ge=0, le=16)
    max_points_per_chart: int = Field(default=300, ge=1, le=1_000)
    max_comparison_facts: int = Field(default=100, ge=1, le=500)
