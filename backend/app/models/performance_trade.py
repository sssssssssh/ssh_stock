import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
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


class PortfolioPerformanceTradeReport(Base):
    __tablename__ = "portfolio_performance_trade_report"
    __table_args__ = (
        CheckConstraint("status = 'SUCCESS'", name=conv("ck_perf_trade_report_status")),
        CheckConstraint("trade_days > 0", name=conv("ck_perf_trade_report_days")),
        ForeignKeyConstraint(
            ("performance_id", "run_id"),
            ("portfolio_performance_report.id", "portfolio_performance_report.run_id"),
            name=conv("fk_perf_trade_report_performance_run"),
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "performance_id",
            "trade_version",
            "trade_config_hash",
            "trade_source_hash",
            name=conv("uq_perf_trade_report_identity"),
        ),
        UniqueConstraint("id", "performance_id", "run_id", name=conv("uq_perf_trade_report_owner")),
        Index(
            "idx_perf_trade_report_performance_calculated",
            "performance_id",
            "calculated_at",
        ),
        Index("idx_perf_trade_report_run_calculated", "run_id", "calculated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_version: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUCCESS", server_default=text("'SUCCESS'")
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    order_count: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sell_fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    sell_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    traded_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    commission_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    stamp_tax_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    transfer_fee_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    cash_fee_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    slippage_cost_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    total_execution_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    cash_fee_to_initial_capital: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    total_cost_to_initial_capital: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    total_cost_to_traded_amount: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    total_turnover: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    average_daily_turnover: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    annualized_turnover: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    closed_episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    open_episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_count: Mapped[int] = mapped_column(Integer, nullable=False)
    loss_count: Mapped[int] = mapped_column(Integer, nullable=False)
    breakeven_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    gross_profit: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    gross_loss_abs: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    profit_factor: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    average_win: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    average_loss_abs: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    payoff_ratio: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    best_episode_pnl: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    worst_episode_pnl: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    average_holding_trade_days: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    median_holding_trade_days: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    closed_realized_pnl: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    open_realized_pnl_end: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    open_unrealized_pnl_end: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    open_mark_to_market_pnl_end: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
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


class PortfolioPerformanceTradeDaily(Base):
    __tablename__ = "portfolio_performance_trade_daily"
    __table_args__ = (
        PrimaryKeyConstraint("trade_id", "trade_date"),
        ForeignKeyConstraint(
            ("trade_id", "performance_id", "run_id"),
            (
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ),
            name=conv("fk_perf_trade_daily_report_owner"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("performance_id", "trade_date"),
            (
                "portfolio_performance_daily.performance_id",
                "portfolio_performance_daily.trade_date",
            ),
            name=conv("fk_perf_trade_daily_base_date"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ("run_id", "trade_date"),
            ("portfolio_nav_daily.run_id", "portfolio_nav_daily.trade_date"),
            name=conv("fk_perf_trade_daily_nav_date"),
            ondelete="CASCADE",
        ),
        Index("idx_perf_trade_daily_run_date", "run_id", "trade_date"),
        Index("idx_perf_trade_daily_performance_date", "performance_id", "trade_date"),
    )

    trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    buy_fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sell_fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    sell_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    traded_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    stamp_tax: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    transfer_fee: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    cash_fee_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    slippage_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    total_execution_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    turnover_denominator: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    daily_turnover: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioPerformanceTradeEpisode(Base):
    __tablename__ = "portfolio_performance_trade_episode"
    __table_args__ = (
        PrimaryKeyConstraint("trade_id", "ts_code", "episode_no"),
        CheckConstraint("episode_no > 0", name=conv("ck_perf_trade_episode_no")),
        CheckConstraint("holding_trade_days > 0", name=conv("ck_perf_trade_episode_days")),
        CheckConstraint(
            "(status = 'CLOSED' AND exit_date IS NOT NULL AND ending_quantity = 0 "
            "AND classification IN ('WIN','LOSS','BREAKEVEN')) OR "
            "(status = 'OPEN' AND exit_date IS NULL AND ending_quantity > 0 "
            "AND classification IS NULL)",
            name=conv("ck_perf_trade_episode_state"),
        ),
        ForeignKeyConstraint(
            ("trade_id", "performance_id", "run_id"),
            (
                "portfolio_performance_trade_report.id",
                "portfolio_performance_trade_report.performance_id",
                "portfolio_performance_trade_report.run_id",
            ),
            name=conv("fk_perf_trade_episode_report_owner"),
            ondelete="CASCADE",
        ),
        Index("idx_perf_trade_episode_run_code", "run_id", "ts_code"),
        Index("idx_perf_trade_episode_performance_status", "performance_id", "status"),
    )

    trade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    performance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    episode_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    classification: Mapped[str | None] = mapped_column(String(16))
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_date: Mapped[date | None] = mapped_column(Date)
    holding_trade_days: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sell_fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fill_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_buy_quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_sell_quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ending_quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    buy_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    sell_gross_amount: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    buy_cash_fee_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    sell_cash_fee_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    commission: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    stamp_tax: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    transfer_fee: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    cash_fee_total: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    slippage_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    total_execution_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    unrealized_pnl_end: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    mark_to_market_pnl_end: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    total_buy_cash_cost: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    sell_net_proceeds: Mapped[Decimal] = mapped_column(Numeric(60, 18), nullable=False)
    episode_return: Mapped[Decimal | None] = mapped_column(Numeric(60, 18))
    first_fill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    last_fill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
