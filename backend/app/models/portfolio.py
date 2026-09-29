import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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


class PortfolioBacktestRun(Base):
    __tablename__ = "portfolio_backtest_run"
    __table_args__ = (
        CheckConstraint(
            "account_mode IN ('BACKTEST', 'PAPER', 'LIVE')",
            name=conv("ck_portfolio_backtest_run_account_mode"),
        ),
        CheckConstraint(
            "status IN ('CREATED', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED')",
            name=conv("ck_portfolio_backtest_run_status"),
        ),
        CheckConstraint(
            "end_date >= start_date", name=conv("ck_portfolio_backtest_run_dates")
        ),
        CheckConstraint(
            "initial_cash > 0", name=conv("ck_portfolio_backtest_run_initial_cash")
        ),
        Index("idx_portfolio_backtest_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(128))
    account_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="CREATED", server_default=text("'CREATED'")
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    benchmark_code: Mapped[str] = mapped_column(String(16), nullable=False)
    algo_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_strategy_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    opportunity_calc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    opportunity_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    portfolio_version: Mapped[str] = mapped_column(String(32), nullable=False)
    portfolio_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_version: Mapped[str] = mapped_column(String(32), nullable=False)
    execution_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    backtest_engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_run.id", ondelete="SET NULL")
    )
    error_message: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortfolioOrder(Base):
    __tablename__ = "portfolio_order"
    __table_args__ = (
        CheckConstraint(
            "side IN ('BUY', 'SELL')", name=conv("ck_portfolio_order_side")
        ),
        CheckConstraint(
            "order_type IN ('NEXT_OPEN', 'MARKET_ON_OPEN')",
            name=conv("ck_portfolio_order_type"),
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PARTIAL', 'EXECUTED', 'REJECTED', 'CANCELLED')",
            name=conv("ck_portfolio_order_status"),
        ),
        CheckConstraint(
            "target_weight IS NULL OR (target_weight >= 0 AND target_weight <= 1)",
            name=conv("ck_portfolio_order_target_weight"),
        ),
        CheckConstraint(
            "target_quantity IS NULL OR target_quantity >= 0",
            name=conv("ck_portfolio_order_target_quantity"),
        ),
        CheckConstraint(
            "attempt_count >= 0", name=conv("ck_portfolio_order_attempt_count")
        ),
        UniqueConstraint(
            "id", "run_id", name=conv("uq_portfolio_order_id_run_id")
        ),
        Index(
            "idx_portfolio_order_run_schedule_status",
            "run_id",
            "scheduled_trade_date",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    target_quantity: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    reason_code: Mapped[str | None] = mapped_column(String(64))
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PortfolioFill(Base):
    __tablename__ = "portfolio_fill"
    __table_args__ = (
        CheckConstraint(
            "side IN ('BUY', 'SELL')", name=conv("ck_portfolio_fill_side")
        ),
        CheckConstraint("quantity > 0", name=conv("ck_portfolio_fill_quantity")),
        CheckConstraint("price > 0", name=conv("ck_portfolio_fill_price")),
        CheckConstraint(
            "gross_amount >= 0", name=conv("ck_portfolio_fill_gross_amount")
        ),
        CheckConstraint("commission >= 0", name=conv("ck_portfolio_fill_commission")),
        CheckConstraint("stamp_tax >= 0", name=conv("ck_portfolio_fill_stamp_tax")),
        CheckConstraint(
            "slippage_cost >= 0", name=conv("ck_portfolio_fill_slippage_cost")
        ),
        CheckConstraint("total_cost >= 0", name=conv("ck_portfolio_fill_total_cost")),
        ForeignKeyConstraint(
            ["order_id", "run_id"],
            ["portfolio_order.id", "portfolio_order.run_id"],
            name=conv("fk_portfolio_fill_order_run_portfolio_order"),
            ondelete="CASCADE",
        ),
        Index("idx_portfolio_fill_run_date", "run_id", "trade_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    commission: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    stamp_tax: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    slippage_cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioPositionDaily(Base):
    __tablename__ = "portfolio_position_daily"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "trade_date", "ts_code"),
        CheckConstraint("quantity >= 0", name=conv("ck_portfolio_position_quantity")),
        CheckConstraint(
            "available_quantity >= 0",
            name=conv("ck_portfolio_position_available_quantity"),
        ),
        CheckConstraint(
            "available_quantity <= quantity",
            name=conv("ck_portfolio_position_available_lte_quantity"),
        ),
        CheckConstraint("avg_cost >= 0", name=conv("ck_portfolio_position_avg_cost")),
        CheckConstraint(
            "close_price IS NULL OR close_price >= 0",
            name=conv("ck_portfolio_position_close_price"),
        ),
        CheckConstraint(
            "market_value >= 0", name=conv("ck_portfolio_position_market_value")
        ),
        CheckConstraint(
            "weight >= 0 AND weight <= 1",
            name=conv("ck_portfolio_position_weight"),
        ),
        Index("idx_portfolio_position_run_date", "run_id", "trade_date"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    available_quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioNavDaily(Base):
    __tablename__ = "portfolio_nav_daily"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "trade_date"),
        CheckConstraint("cash >= 0", name=conv("ck_portfolio_nav_cash")),
        CheckConstraint(
            "market_value >= 0", name=conv("ck_portfolio_nav_market_value")
        ),
        CheckConstraint(
            "total_assets >= 0", name=conv("ck_portfolio_nav_total_assets")
        ),
        CheckConstraint("nav >= 0", name=conv("ck_portfolio_nav_nav")),
        CheckConstraint(
            "gross_exposure >= 0", name=conv("ck_portfolio_nav_gross_exposure")
        ),
        CheckConstraint(
            "net_exposure >= 0", name=conv("ck_portfolio_nav_net_exposure")
        ),
        CheckConstraint(
            "position_count >= 0", name=conv("ck_portfolio_nav_position_count")
        ),
        CheckConstraint(
            "trading_cost >= 0", name=conv("ck_portfolio_nav_trading_cost")
        ),
        Index("idx_portfolio_nav_run_date", "run_id", "trade_date"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_backtest_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    benchmark_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    benchmark_daily_return: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    gross_exposure: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    net_exposure: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    trading_cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
