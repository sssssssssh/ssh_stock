import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobRun(Base):
    __tablename__ = "job_run"
    __table_args__ = (
        Index("idx_job_run_type_date_status", "job_type", "target_trade_date", "status"),
        Index("idx_job_run_retention", "status", "finished_at", "id"),
        Index("idx_job_data_queue", "status", "started_at", "id"),
        Index("idx_job_parent", "parent_job_id"),
        Index("idx_job_dependency", "depends_on_job_id"),
        Index("uq_job_active_fingerprint", "request_fingerprint", unique=True,
              postgresql_where=text(
                  "status IN ('QUEUED','RUNNING') AND request_fingerprint IS NOT NULL")),
        CheckConstraint("depends_on_job_id <> id", name="job_no_self_dependency"),
        CheckConstraint("parent_job_id <> id", name="job_no_self_parent"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_trade_date: Mapped[date | None] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING")
    step: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2048))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_progress_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_fingerprint: Mapped[str | None] = mapped_column(String(128))
    depends_on_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_run.id", ondelete="RESTRICT"),
    )
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_run.id", ondelete="RESTRICT"),
    )
    job_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ProviderApiLog(Base):
    __tablename__ = "provider_api_log"
    __table_args__ = (
        Index("idx_provider_api_log_date_name", "trade_date", "api_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    api_name: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_date: Mapped[date | None] = mapped_column(Date)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    row_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeat"
    __table_args__ = (
        UniqueConstraint("service_name", "instance_id", name="uq_service_heartbeat_instance"),
        Index("idx_service_heartbeat_name_time", "service_name", "heartbeat_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name: Mapped[str] = mapped_column(String(32), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(160), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UP")
    service_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
