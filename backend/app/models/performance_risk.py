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


class PortfolioPerformanceRiskReport(Base):
    __tablename__ = "portfolio_performance_risk_report"
    __table_args__ = (
        CheckConstraint("status = 'SUCCESS'", name=conv("ck_perf_risk_report_status")),
        CheckConstraint("trade_days > 0", name=conv("ck_perf_risk_report_trade_days")),
        ForeignKeyConstraint(
            ("performance_id", "run_id"),
            ("portfolio_performance_report.id", "portfolio_performance_report.run_id"),
            name=conv("fk_perf_risk_report_performance_run"),
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "performance_id",
            "risk_version",
            "risk_config_hash",
            "benchmark_source_hash",
            name=conv("uq_perf_risk_report_identity"),
        ),
        UniqueConstraint(
            "id",
            "performance_id",
            "run_id",
            name=conv("uq_perf_risk_report_owner"),
        ),
        Index(
            "idx_perf_risk_report_performance_calculated",
            "performance_id",
            "calculated_at",
        ),
        Index("idx_perf_risk_report_run_calculated", "run_id", "calculated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    risk_version: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    benchmark_code: Mapped[str] = mapped_column(String(16), nullable=False)
    benchmark_source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUCCESS", server_default=text("'SUCCESS'")
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_free_rate_annual: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    benchmark_initial_nav: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    benchmark_final_nav: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    benchmark_cumulative_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    benchmark_annualized_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    excess_cumulative_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    relative_nav_final: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    strategy_annualized_volatility: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    benchmark_annualized_volatility: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    downside_deviation_annualized: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    sortino_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    calmar_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    tracking_error: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    information_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    alpha_daily: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    alpha_annualized: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    beta: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    correlation: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
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


class PortfolioPerformanceRiskDaily(Base):
    __tablename__ = "portfolio_performance_risk_daily"
    __table_args__ = (
        PrimaryKeyConstraint("risk_id", "trade_date"),
        ForeignKeyConstraint(
            ("risk_id", "performance_id", "run_id"),
            (
                "portfolio_performance_risk_report.id",
                "portfolio_performance_risk_report.performance_id",
                "portfolio_performance_risk_report.run_id",
            ),
            name=conv("fk_perf_risk_daily_report_owner"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("performance_id", "trade_date"),
            (
                "portfolio_performance_daily.performance_id",
                "portfolio_performance_daily.trade_date",
            ),
            name=conv("fk_perf_risk_daily_base_date"),
            ondelete="CASCADE",
        ),
        Index("idx_perf_risk_daily_run_date", "run_id", "trade_date"),
        Index(
            "idx_perf_risk_daily_performance_date",
            "performance_id",
            "trade_date",
        ),
    )

    risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    benchmark_reference_close: Mapped[Decimal] = mapped_column(
        Numeric(30, 12), nullable=False
    )
    benchmark_close: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    benchmark_daily_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    benchmark_nav: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    active_return: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    relative_nav: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    excess_cumulative_return: Mapped[Decimal] = mapped_column(
        Numeric(60, 18), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
