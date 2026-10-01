import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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


class PortfolioPerformanceReport(Base):
    __tablename__ = "portfolio_performance_report"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCESS', 'FAILED')",
            name=conv("ck_portfolio_performance_report_status"),
        ),
        CheckConstraint("trade_days > 0", name=conv("ck_portfolio_performance_trade_days")),
        UniqueConstraint(
            "run_id",
            "performance_version",
            "performance_config_hash",
            "source_hash",
            name=conv("uq_portfolio_performance_report_identity"),
        ),
        Index("idx_portfolio_performance_report_run_calculated", "run_id", "calculated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    performance_version: Mapped[str] = mapped_column(String(32), nullable=False)
    performance_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUCCESS", server_default=text("'SUCCESS'")
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    final_nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    cumulative_return: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    annualized_return: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    max_drawdown_peak_date: Mapped[date | None] = mapped_column(Date)
    max_drawdown_trough_date: Mapped[date | None] = mapped_column(Date)
    max_drawdown_recovery_date: Mapped[date | None] = mapped_column(Date)
    max_drawdown_duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_days: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_days: Mapped[int] = mapped_column(Integer, nullable=False)
    flat_days: Mapped[int] = mapped_column(Integer, nullable=False)
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


class PortfolioPerformanceDaily(Base):
    __tablename__ = "portfolio_performance_daily"
    __table_args__ = (
        PrimaryKeyConstraint("performance_id", "trade_date"),
        Index("idx_portfolio_performance_daily_run_date", "run_id", "trade_date"),
    )

    performance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_performance_report.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    daily_return: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    cumulative_return: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    running_peak_nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    drawdown: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    drawdown_duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    cash_ratio: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    gross_exposure: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    net_exposure: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trading_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
