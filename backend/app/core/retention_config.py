from pydantic import BaseModel, ConfigDict, Field


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_deletion_enabled: bool = False
    max_candidate_rows: int = Field(default=10000, ge=1, le=100000)
    candidate_warning_percent: int = Field(default=80, ge=1, le=100)
    max_missing_references: int = Field(default=1000, ge=1, le=10000)
    diagnostic_limit: int = Field(default=20, ge=0, le=100)
    lock_timeout_ms: int = Field(default=1000, ge=1, le=5000)
    statement_timeout_ms: int = Field(default=3000, ge=1, le=30000)
    max_duration_ms: int = Field(default=15000, ge=1, le=60000)
