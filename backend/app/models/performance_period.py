import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.base import Base


class PortfolioPerformancePeriodReport(Base):
    __tablename__ = "portfolio_performance_period_report"
    __table_args__ = (
        CheckConstraint("status = 'SUCCESS'", name=conv("ck_perf_period_report_status")),
        CheckConstraint("trade_days > 0", name=conv("ck_perf_period_report_days")),
        CheckConstraint("month_count > 0", name=conv("ck_perf_period_report_months")),
        CheckConstraint("year_count > 0", name=conv("ck_perf_period_report_years")),
        ForeignKeyConstraint(
            ("performance_id", "run_id"),
            ("portfolio_performance_report.id", "portfolio_performance_report.run_id"),
            name=conv("fk_perf_period_report_performance"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("risk_id", "performance_id", "run_id"),
            (
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ),
            name=conv("fk_perf_period_report_risk"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("trade_id", "performance_id", "run_id"),
            (
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ),
            name=conv("fk_perf_period_report_trade"),
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "performance_id",
            "risk_id",
            "trade_id",
            "period_version",
            "period_config_hash",
            "period_source_hash",
            name=conv("uq_perf_period_report_identity"),
        ),
        UniqueConstraint(
            "id",
            "performance_id",
            "risk_id",
            "trade_id",
            "run_id",
            name=conv("uq_perf_period_report_owner"),
        ),
        Index("idx_perf_period_report_bundle", "performance_id", "risk_id", "trade_id"),
        Index("idx_perf_period_report_run_calculated", "run_id", "calculated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_version: Mapped[str] = mapped_column(String(32), nullable=False)
    period_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    period_source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUCCESS", server_default=text("'SUCCESS'")
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    month_count: Mapped[int] = mapped_column(Integer, nullable=False)
    year_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PortfolioPerformancePeriod(Base):
    __tablename__ = "portfolio_performance_period"
    __table_args__ = (
        PrimaryKeyConstraint("period_id", "period_type", "period_key"),
        CheckConstraint(
            "period_type IN ('MONTH','YEAR')", name=conv("ck_perf_period_type")
        ),
        CheckConstraint("trade_days > 0", name=conv("ck_perf_period_days")),
        CheckConstraint("closed_episode_count >= 0", name=conv("ck_perf_period_closed")),
        CheckConstraint(
            "win_count >= 0 AND loss_count >= 0 AND breakeven_count >= 0",
            name=conv("ck_perf_period_class_counts"),
        ),
        CheckConstraint(
            "win_count + loss_count + breakeven_count = closed_episode_count",
            name=conv("ck_perf_period_class_total"),
        ),
        CheckConstraint(
            "win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 1)",
            name=conv("ck_perf_period_win_rate"),
        ),
        ForeignKeyConstraint(
            ("period_id", "performance_id", "risk_id", "trade_id", "run_id"),
            (
                "portfolio_performance_period_report.id",
                "portfolio_performance_period_report.performance_id",
                "portfolio_performance_period_report.risk_id",
                "portfolio_performance_period_report.trade_id",
                "portfolio_performance_period_report.run_id",
            ),
            name=conv("fk_perf_period_row_report_owner"),
            ondelete="CASCADE",
        ),
        Index("idx_perf_period_row_run_type_key", "run_id", "period_type", "period_key"),
    )

    period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(8), nullable=False)
    period_key: Mapped[str] = mapped_column(String(7), nullable=False)
    period_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    benchmark_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    relative_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    return_spread: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    period_turnover: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    traded_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    stamp_tax: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    transfer_fee: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    cash_fee_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    slippage_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    total_execution_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    closed_episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False)
    loss_count: Mapped[int] = mapped_column(Integer, nullable=False)
    breakeven_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    closed_realized_pnl: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
