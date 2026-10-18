"""Durable candidate patches; current business tables remain the published slice."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.models.base import Base


class RowKeyJSON(TypeDecorator):
    impl = JSONB
    cache_ok = True
    hashable = True

    def process_result_value(self, value, dialect):
        return tuple(value) if value is not None else None


class DataPublication(Base):
    __tablename__ = "data_publication"
    __table_args__ = (
        CheckConstraint("state IN ('PREPARING','PUBLISHED','ABORTED')", name="publication_state"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_run.id", ondelete="RESTRICT"), primary_key=True
    )
    execution_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PREPARING")
    identity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    publish_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    row_counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class DataPublicationSource(Base):
    __tablename__ = "data_publication_source"
    __table_args__ = (Index("idx_publication_source_job", "source_job_id"),)

    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_publication.job_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_run.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class DataPublicationRow(Base):
    __tablename__ = "data_publication_row"
    __table_args__ = (
        Index("idx_publication_row_date", "publication_id", "table_name", "trade_date"),
        Index(
            "idx_publication_row_entity", "publication_id", "table_name", "entity_key", "trade_date"
        ),
        CheckConstraint(
            "(is_deleted AND row_data IS NULL) OR (NOT is_deleted AND row_data IS NOT NULL)",
            name="candidate_row_data",
        ),
    )

    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_publication.job_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    table_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    row_key: Mapped[tuple] = mapped_column(RowKeyJSON(), primary_key=True)
    row_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    base_row: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trade_date: Mapped[date | None] = mapped_column(Date)
    entity_key: Mapped[str | None] = mapped_column(String(64))


class DataPublicationPreimage(Base):
    __tablename__ = "data_publication_preimage"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_publication.job_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    table_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    row_key: Mapped[tuple] = mapped_column(RowKeyJSON(), primary_key=True)
    row_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class DataPublicationScope(Base):
    __tablename__ = "data_publication_scope"
    __table_args__ = (Index("idx_publication_scope", "publication_id", "table_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_publication.job_id", ondelete="RESTRICT")
    )
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
