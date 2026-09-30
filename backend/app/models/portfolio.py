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
        UniqueConstraint(
            "job_id", name=conv("uq_portfolio_backtest_run_job_id")
        ),
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
    accounting_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="accounting_v0_unimplemented"
    )
    accounting_config_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UNAVAILABLE"
    )
    backtest_engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_run.id", ondelete="SET NULL")
    )
    owner_worker_id: Mapped[str | None] = mapped_column(String(128))
    ownership_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortfolioBacktestCheckpoint(Base):
    __tablename__ = "portfolio_backtest_checkpoint"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('START_OF_DAY', 'OPEN', 'CLOSE', 'AFTER_CLOSE', "
            "'DAY_COMPLETED')",
            name=conv("ck_portfolio_backtest_checkpoint_phase"),
        ),
        CheckConstraint(
            "phase_status IN ('STARTED', 'COMPLETED', 'FAILED')",
            name=conv("ck_portfolio_backtest_checkpoint_status"),
        ),
        CheckConstraint(
            "attempt > 0", name=conv("ck_portfolio_backtest_checkpoint_attempt")
        ),
        CheckConstraint(
            "version > 0", name=conv("ck_portfolio_backtest_checkpoint_version")
        ),
        UniqueConstraint(
            "run_id",
            "trade_date",
            "phase",
            name=conv("uq_portfolio_backtest_checkpoint_run_date_phase"),
        ),
        Index(
            "idx_portfolio_backtest_checkpoint_run_status",
            "run_id",
            "phase_status",
            "trade_date",
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
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    phase_status: Mapped[str] = mapped_column(String(16), nullable=False)
    input_identity: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    result_identity: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(2048))
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    worker_owner: Mapped[str | None] = mapped_column(String(128))


class PortfolioRebalancePlan(Base):
    __tablename__ = "portfolio_rebalance_plan"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "signal_trade_date",
            name=conv("uq_portfolio_rebalance_plan_run_signal_date"),
        ),
        UniqueConstraint(
            "id", "run_id", name=conv("uq_portfolio_rebalance_plan_id_run_id")
        ),
        CheckConstraint(
            "portfolio_version <> 'portfolio_v3' OR input_hash IS NOT NULL",
            name=conv("ck_portfolio_rebalance_plan_v3_input_hash"),
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
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    portfolio_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    target_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    account_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioOrder(Base):
    __tablename__ = "portfolio_order"
    __table_args__ = (
        CheckConstraint(
            "side IN ('BUY', 'SELL')", name=conv("ck_portfolio_order_side")
        ),
        CheckConstraint(
            "order_type = 'NEXT_OPEN'",
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
            "target_quantity IS NULL OR target_quantity > 0",
            name=conv("ck_portfolio_order_target_quantity"),
        ),
        CheckConstraint(
            "attempt_count >= 0", name=conv("ck_portfolio_order_attempt_count")
        ),
        CheckConstraint(
            "child_index IS NULL OR child_index > 0",
            name=conv("ck_portfolio_order_child_index"),
        ),
        CheckConstraint(
            "(rebalance_plan_id IS NULL AND child_index IS NULL) OR "
            "(rebalance_plan_id IS NOT NULL AND child_index IS NOT NULL)",
            name=conv("ck_portfolio_order_plan_child_pair"),
        ),
        ForeignKeyConstraint(
            ["rebalance_plan_id", "run_id"],
            ["portfolio_rebalance_plan.id", "portfolio_rebalance_plan.run_id"],
            name=conv("fk_portfolio_order_plan_run_portfolio_rebalance_plan"),
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id", "run_id", name=conv("uq_portfolio_order_id_run_id")
        ),
        UniqueConstraint(
            "rebalance_plan_id",
            "ts_code",
            "side",
            "child_index",
            name=conv("uq_portfolio_order_plan_code_side_child"),
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
    rebalance_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    child_index: Mapped[int | None] = mapped_column(Integer)
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


class PortfolioOrderAttempt(Base):
    __tablename__ = "portfolio_order_attempt"
    __table_args__ = (
        CheckConstraint(
            "attempt_no > 0", name=conv("ck_portfolio_order_attempt_attempt_no")
        ),
        CheckConstraint(
            "outcome IN ('RETRY', 'EXECUTED', 'REJECTED', 'EXPIRED')",
            name=conv("ck_portfolio_order_attempt_outcome"),
        ),
        CheckConstraint(
            "requested_quantity >= 0",
            name=conv("ck_portfolio_order_attempt_requested_quantity"),
        ),
        CheckConstraint(
            "requested_quantity > 0 OR "
            "(requested_quantity = 0 AND outcome = 'REJECTED' "
            "AND reason_code = 'INVALID_QUANTITY')",
            name=conv("ck_portfolio_order_attempt_quantity_validity"),
        ),
        CheckConstraint(
            "fill_quantity >= 0",
            name=conv("ck_portfolio_order_attempt_fill_quantity"),
        ),
        CheckConstraint(
            "fill_quantity <= requested_quantity",
            name=conv("ck_portfolio_order_attempt_fill_lte_requested"),
        ),
        CheckConstraint(
            "reference_price IS NULL OR reference_price > 0",
            name=conv("ck_portfolio_order_attempt_reference_price"),
        ),
        CheckConstraint(
            "fill_price IS NULL OR fill_price > 0",
            name=conv("ck_portfolio_order_attempt_fill_price"),
        ),
        CheckConstraint(
            "gross_amount >= 0", name=conv("ck_portfolio_order_attempt_gross_amount")
        ),
        CheckConstraint(
            "commission >= 0", name=conv("ck_portfolio_order_attempt_commission")
        ),
        CheckConstraint(
            "stamp_tax >= 0", name=conv("ck_portfolio_order_attempt_stamp_tax")
        ),
        CheckConstraint(
            "transfer_fee >= 0", name=conv("ck_portfolio_order_attempt_transfer_fee")
        ),
        CheckConstraint(
            "cash_fee_total >= 0",
            name=conv("ck_portfolio_order_attempt_cash_fee_total"),
        ),
        CheckConstraint(
            "slippage_cost >= 0",
            name=conv("ck_portfolio_order_attempt_slippage_cost"),
        ),
        CheckConstraint(
            "total_cost >= 0", name=conv("ck_portfolio_order_attempt_total_cost")
        ),
        CheckConstraint(
            "(outcome = 'EXECUTED' AND reason_code IS NULL) OR "
            "(outcome <> 'EXECUTED' AND reason_code IS NOT NULL)",
            name=conv("ck_portfolio_order_attempt_outcome_reason"),
        ),
        CheckConstraint(
            "outcome <> 'EXECUTED' OR "
            "(fill_quantity = requested_quantity AND requested_quantity > 0 "
            "AND reference_price IS NOT NULL AND fill_price IS NOT NULL "
            "AND gross_amount > 0)",
            name=conv("ck_portfolio_order_attempt_executed_consistency"),
        ),
        CheckConstraint(
            "outcome = 'EXECUTED' OR "
            "(fill_quantity = 0 AND fill_price IS NULL AND gross_amount = 0 "
            "AND commission = 0 AND stamp_tax = 0 AND transfer_fee = 0 "
            "AND cash_fee_total = 0 AND slippage_cost = 0 AND total_cost = 0)",
            name=conv("ck_portfolio_order_attempt_non_executed_consistency"),
        ),
        CheckConstraint(
            "cash_fee_total = commission + stamp_tax + transfer_fee",
            name=conv("ck_portfolio_order_attempt_cash_fee_components"),
        ),
        CheckConstraint(
            "total_cost = cash_fee_total + slippage_cost",
            name=conv("ck_portfolio_order_attempt_total_cost_components"),
        ),
        ForeignKeyConstraint(
            ["order_id", "run_id"],
            ["portfolio_order.id", "portfolio_order.run_id"],
            name=conv("fk_portfolio_order_attempt_order_run_portfolio_order"),
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id", "run_id", name=conv("uq_portfolio_order_attempt_id_run_id")
        ),
        UniqueConstraint(
            "order_id", "attempt_no", name=conv("uq_portfolio_order_attempt_order_no")
        ),
        UniqueConstraint(
            "order_id",
            "attempt_trade_date",
            name=conv("uq_portfolio_order_attempt_order_date"),
        ),
        Index(
            "idx_portfolio_order_attempt_run_date", "run_id", "attempt_trade_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt_trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    requested_quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fill_quantity: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    commission: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    stamp_tax: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    transfer_fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    cash_fee_total: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    slippage_cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    market_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    account_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
            "transfer_fee >= 0", name=conv("ck_portfolio_fill_transfer_fee")
        ),
        CheckConstraint(
            "cash_fee_total >= 0", name=conv("ck_portfolio_fill_cash_fee_total")
        ),
        CheckConstraint(
            "slippage_cost >= 0", name=conv("ck_portfolio_fill_slippage_cost")
        ),
        CheckConstraint("total_cost >= 0", name=conv("ck_portfolio_fill_total_cost")),
        CheckConstraint(
            "cash_fee_total = commission + stamp_tax + transfer_fee",
            name=conv("ck_portfolio_fill_cash_fee_components"),
        ),
        CheckConstraint(
            "total_cost = cash_fee_total + slippage_cost",
            name=conv("ck_portfolio_fill_total_cost_components"),
        ),
        ForeignKeyConstraint(
            ["order_id", "run_id"],
            ["portfolio_order.id", "portfolio_order.run_id"],
            name=conv("fk_portfolio_fill_order_run_portfolio_order"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["attempt_id", "run_id"],
            ["portfolio_order_attempt.id", "portfolio_order_attempt.run_id"],
            name=conv("fk_portfolio_fill_attempt_run_portfolio_order_attempt"),
            ondelete="CASCADE",
        ),
        Index("idx_portfolio_fill_run_date", "run_id", "trade_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
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
    reference_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    commission: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    stamp_tax: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    transfer_fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=0, server_default=text("0")
    )
    cash_fee_total: Mapped[Decimal] = mapped_column(
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
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    valuation_source: Mapped[str | None] = mapped_column(String(24))
    adj_factor: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
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
