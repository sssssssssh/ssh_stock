import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.naming import conv

from app.models.base import Base


def _check(name: str, expression: str):
    return CheckConstraint(expression, name=conv(name))


def record_constraints(table: str):
    return (
        UniqueConstraint("id", "owner_user_id", name=conv(f"uq_{table}_owner")),
        Index(f"idx_{table}_owner_created", "owner_user_id", "created_at", "id"),
        _check(f"ck_{table}_hash", "record_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            f"ck_{table}_json",
            "jsonb_typeof(record_json) = 'object' AND "
            "record_json->>'schema_version' = schema_version AND "
            "jsonb_typeof(record_json->'schema_version') = 'string' AND "
            "record_json ? 'schema_version' AND length(schema_version) > 0 AND "
            "octet_length(record_json::text) <= 131072",
        ),
    )


def account_constraints(table: str):
    return (
        *record_constraints(table),
        UniqueConstraint("id", "owner_user_id", "account_id", name=conv(f"uq_{table}_scope")),
        scoped_fk("account_id", "paper_account", account=False),
        Index(f"idx_{table}_account", "account_id", "created_at", "id"),
    )


def scoped_fk(column: str, parent: str, *, account: bool = True):
    local = [column, "owner_user_id"] + (["account_id"] if account else [])
    remote = [f"{parent}.id", f"{parent}.owner_user_id"]
    if account:
        remote.append(f"{parent}.account_id")
    return ForeignKeyConstraint(local, remote, ondelete="RESTRICT")


def day_fk():
    return ForeignKeyConstraint(
        ["day_run_id", "owner_user_id", "account_id", "trade_date"],
        [
            "paper_day_run.id",
            "paper_day_run.owner_user_id",
            "paper_day_run.account_id",
            "paper_day_run.trade_date",
        ],
        ondelete="RESTRICT",
    )


def finite_nonnegative(column: str):
    return f"{column} >= 0 AND {column} < 'Infinity'::numeric AND {column} <> 'NaN'::numeric"


class PaperRecord:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    record_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AccountRecord(PaperRecord):
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class PaperAccount(PaperRecord, Base):
    __tablename__ = "paper_account"
    __table_args__ = (
        *record_constraints("paper_account"),
        UniqueConstraint("owner_user_id", "name", name=conv("uq_paper_account_name")),
        UniqueConstraint("owner_user_id", "request_id", name=conv("uq_paper_account_request")),
        _check("ck_paper_account_state", "state IN ('CREATED','ACTIVE','PAUSED','CLOSED')"),
        _check("ck_paper_account_mode", "mode = 'PAPER'"),
        _check(
            "ck_paper_account_cash", finite_nonnegative("initial_cash") + " AND initial_cash > 0"
        ),
        _check("ck_paper_account_request_hash", "request_hash ~ '^[0-9a-f]{64}$'"),
        _check("ck_paper_account_config_hash", "config_hash ~ '^[0-9a-f]{64}$'"),
        _check("ck_paper_account_version", "version >= 1"),
        _check("ck_paper_account_name", "length(trim(name)) > 0"),
        _check(
            "ck_paper_account_config",
            "jsonb_typeof(config_snapshot_json) = 'object' AND "
            "config_snapshot_json ? 'schema_version' AND "
            "octet_length(config_snapshot_json::text) <= 131072",
        ),
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="PAPER")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PAUSED")
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    benchmark_code: Mapped[str] = mapped_column(String(24), nullable=False)
    first_trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    config_version: Mapped[str] = mapped_column(String(64), nullable=False)
    config_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PaperAccountEvent(AccountRecord, Base):
    __tablename__ = "paper_account_event"
    __table_args__ = (
        *account_constraints("paper_account_event"),
        UniqueConstraint(
            "owner_user_id", "request_id", name=conv("uq_paper_account_event_request")
        ),
        _check("ck_paper_account_event_request_hash", "request_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_paper_account_event_state", "to_state IN ('CREATED','ACTIVE','PAUSED','CLOSED')"
        ),
    )
    from_state: Mapped[str | None] = mapped_column(String(16))
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DecisionObservation(PaperRecord, Base):
    __tablename__ = "decision_observation"
    __table_args__ = (
        *record_constraints("decision_observation"),
        UniqueConstraint(
            "owner_user_id", "request_id", name=conv("uq_decision_observation_request")
        ),
        _check("ck_decision_observation_request_hash", "request_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_decision_observation_identity_hash", "strategy_identity_hash ~ '^[0-9a-f]{64}$'"
        ),
        _check("ck_decision_observation_status", "source_status = 'READY'"),
        _check(
            "ck_decision_observation_cutoff",
            "ready_at <= asof_cutoff AND asof_cutoff <= created_at",
        ),
        Index("idx_decision_observation_date", "owner_user_id", "signal_date"),
    )
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_status: Mapped[str] = mapped_column(String(16), nullable=False)
    asof_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strategy_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DecisionProposal(AccountRecord, Base):
    __tablename__ = "decision_proposal"
    __table_args__ = (
        *account_constraints("decision_proposal"),
        scoped_fk("observation_id", "decision_observation", account=False),
        scoped_fk("supersedes_id", "decision_proposal"),
        UniqueConstraint("owner_user_id", "request_id", name=conv("uq_decision_proposal_request")),
        _check("ck_decision_proposal_request_hash", "request_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_decision_proposal_revision",
            "revision >= 1 AND version >= 1 AND id <> supersedes_id",
        ),
        _check(
            "ck_decision_proposal_state",
            "state IN ('DRAFT','PENDING_REVIEW','APPROVED','REJECTED','EXPIRED')",
        ),
        _check(
            "ck_decision_proposal_action",
            "action IN ('WATCH','PROPOSE_BUY','PROPOSE_REDUCE','PROPOSE_EXIT')",
        ),
        _check(
            "ck_decision_proposal_weight",
            finite_nonnegative("target_weight") + " AND target_weight <= 1",
        ),
        _check("ck_decision_proposal_score", finite_nonnegative("score")),
        _check("ck_decision_proposal_expiry", "expires_at > created_at"),
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DecisionApprovalEvent(AccountRecord, Base):
    __tablename__ = "decision_approval_event"
    __table_args__ = (
        *account_constraints("decision_approval_event"),
        scoped_fk("proposal_id", "decision_proposal"),
        ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="RESTRICT"),
        UniqueConstraint("proposal_id", name=conv("uq_decision_approval_event_proposal")),
        UniqueConstraint(
            "id",
            "owner_user_id",
            "account_id",
            "proposal_id",
            name=conv("uq_decision_approval_event_proposal_scope"),
        ),
        UniqueConstraint(
            "owner_user_id", "request_id", name=conv("uq_decision_approval_event_request")
        ),
        _check("ck_decision_approval_event_request_hash", "request_hash ~ '^[0-9a-f]{64}$'"),
        _check("ck_decision_approval_event_actor", "actor_user_id = owner_user_id"),
        _check("ck_decision_approval_event_decision", "decision IN ('APPROVED','REJECTED')"),
        _check(
            "ck_decision_approval_event_weight",
            finite_nonnegative("approved_target_weight") + " AND approved_target_weight <= 1",
        ),
    )
    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    approved_target_weight: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PaperDayRun(AccountRecord, Base):
    __tablename__ = "paper_day_run"
    __table_args__ = (
        *account_constraints("paper_day_run"),
        UniqueConstraint("account_id", "trade_date", "phase", name=conv("uq_paper_day_run_phase")),
        UniqueConstraint(
            "id", "owner_user_id", "account_id", "trade_date", name=conv("uq_paper_day_run_date")
        ),
        _check("ck_paper_day_run_phase", "phase IN ('EXECUTION','CLOSE','DAY_COMPLETED')"),
        _check(
            "ck_paper_day_run_status",
            "status IN ('QUEUED','RUNNING','SUCCESS','FAILED','CANCELLED','REVIEW_REQUIRED')",
        ),
        _check("ck_paper_day_run_generation", "generation >= 1"),
        _check(
            "ck_paper_day_run_hashes",
            "source_hash ~ '^[0-9a-f]{64}$' AND input_hash ~ '^[0-9a-f]{64}$' "
            "AND (result_hash IS NULL OR result_hash ~ '^[0-9a-f]{64}$')",
        ),
        _check("ck_paper_day_run_success", "status <> 'SUCCESS' OR result_hash IS NOT NULL"),
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    phase: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_run.id", ondelete="RESTRICT"),
    )
    error_code: Mapped[str | None] = mapped_column(String(64))


class PaperOrder(AccountRecord, Base):
    __tablename__ = "paper_order"
    __table_args__ = (
        *account_constraints("paper_order"),
        ForeignKeyConstraint(
            ["approval_id", "owner_user_id", "account_id", "proposal_id"],
            [
                "decision_approval_event.id",
                "decision_approval_event.owner_user_id",
                "decision_approval_event.account_id",
                "decision_approval_event.proposal_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("approval_id", name=conv("uq_paper_order_approval")),
        _check("ck_paper_order_type", "order_type = 'NEXT_OPEN' AND mode = 'PAPER'"),
        _check("ck_paper_order_side", "side IN ('BUY','SELL')"),
        _check("ck_paper_order_dates", "scheduled_date > signal_date"),
        _check("ck_paper_order_quantity", "quantity > 0"),
        _check(
            "ck_paper_order_weight", finite_nonnegative("target_weight") + " AND target_weight <= 1"
        ),
        _check("ck_paper_order_source_hash", "source_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_paper_order_state",
            "status IN ('ORDER_PENDING','FILLED','SKIPPED','CANCELLED','EXPIRED')",
        ),
        _check("ck_paper_order_version", "version >= 1"),
        Index("idx_paper_order_schedule", "account_id", "scheduled_date", "status"),
        Index(
            "uq_paper_order_pending_code",
            "account_id",
            "ts_code",
            unique=True,
            postgresql_where=text("status = 'ORDER_PENDING'"),
        ),
    )
    approval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default="NEXT_OPEN")
    mode: Mapped[str] = mapped_column(String(8), nullable=False, default="PAPER")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ORDER_PENDING")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))


class PaperOrderAttempt(AccountRecord, Base):
    __tablename__ = "paper_order_attempt"
    __table_args__ = (
        *account_constraints("paper_order_attempt"),
        scoped_fk("order_id", "paper_order"),
        UniqueConstraint("order_id", "trade_date", "attempt_no", name=conv("uq_paper_attempt_key")),
        UniqueConstraint(
            "id",
            "owner_user_id",
            "account_id",
            "order_id",
            "trade_date",
            name=conv("uq_paper_attempt_order_date"),
        ),
        _check("ck_paper_attempt_number", "attempt_no >= 1"),
        _check("ck_paper_attempt_outcome", "outcome IN ('FILLED','SKIPPED','CANCELLED','EXPIRED')"),
        _check("ck_paper_attempt_hash", "market_snapshot_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_paper_attempt_reason",
            "(outcome = 'FILLED' AND reason_code IS NULL) OR "
            "(outcome <> 'FILLED' AND reason_code IS NOT NULL)",
        ),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64))
    market_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)


class PaperFill(AccountRecord, Base):
    __tablename__ = "paper_fill"
    __table_args__ = (
        *account_constraints("paper_fill"),
        ForeignKeyConstraint(
            ["attempt_id", "owner_user_id", "account_id", "order_id", "trade_date"],
            [
                "paper_order_attempt.id",
                "paper_order_attempt.owner_user_id",
                "paper_order_attempt.account_id",
                "paper_order_attempt.order_id",
                "paper_order_attempt.trade_date",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("attempt_id", name=conv("uq_paper_fill_attempt")),
        UniqueConstraint(
            "id", "owner_user_id", "account_id", "trade_date", name=conv("uq_paper_fill_date")
        ),
        _check("ck_paper_fill_quantity", "quantity > 0 AND side IN ('BUY','SELL')"),
        _check(
            "ck_paper_fill_price",
            finite_nonnegative("ref_open_price")
            + " AND ref_open_price > 0 AND "
            + finite_nonnegative("simulated_price")
            + " AND simulated_price > 0",
        ),
        _check(
            "ck_paper_fill_amounts",
            finite_nonnegative("cash_fee_total")
            + " AND "
            + finite_nonnegative("total_cost")
            + " AND total_cost >= cash_fee_total AND "
            + finite_nonnegative("gross_amount")
            + " AND gross_amount > 0 AND "
            "cash_delta = CASE WHEN side = 'BUY' THEN -gross_amount - cash_fee_total "
            "ELSE gross_amount - cash_fee_total END",
        ),
        _check(
            "ck_paper_fill_fee_json",
            "jsonb_typeof(fee_json) = 'object' AND fee_json ? 'schema_version' "
            "AND octet_length(fee_json::text) <= 4096",
        ),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_open_price: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    simulated_price: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    cash_fee_total: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    fee_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PaperLedgerEntry(AccountRecord, Base):
    __tablename__ = "paper_ledger_entry"
    __table_args__ = (
        *account_constraints("paper_ledger_entry"),
        ForeignKeyConstraint(
            ["day_run_id", "owner_user_id", "account_id", "trade_date"],
            [
                "paper_day_run.id",
                "paper_day_run.owner_user_id",
                "paper_day_run.account_id",
                "paper_day_run.trade_date",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["fill_id", "owner_user_id", "account_id", "trade_date"],
            [
                "paper_fill.id",
                "paper_fill.owner_user_id",
                "paper_fill.account_id",
                "paper_fill.trade_date",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("account_id", "business_key", name=conv("uq_paper_ledger_key")),
        UniqueConstraint("fill_id", name=conv("uq_paper_ledger_fill")),
        Index(
            "uq_paper_ledger_initial",
            "account_id",
            unique=True,
            postgresql_where=text("entry_type = 'INITIAL_CASH'"),
        ),
        _check(
            "ck_paper_ledger_entry",
            "(entry_type = 'INITIAL_CASH' AND fill_id IS NULL AND day_run_id IS NULL "
            "AND cash_delta > 0 AND quantity_delta = 0 AND instrument IS NULL) OR "
            "(entry_type = 'FILL' AND fill_id IS NOT NULL AND day_run_id IS NOT NULL AND "
            "instrument IS NOT NULL AND quantity_delta <> 0)",
        ),
        _check(
            "ck_paper_ledger_finite",
            "cash_delta > '-Infinity'::numeric AND cash_delta < 'Infinity'::numeric "
            "AND cash_delta <> 'NaN'::numeric",
        ),
    )
    day_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    fill_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    business_key: Mapped[str] = mapped_column(String(160), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    instrument: Mapped[str | None] = mapped_column(String(16))


class PaperPositionDaily(AccountRecord, Base):
    __tablename__ = "paper_position_daily"
    __table_args__ = (
        *account_constraints("paper_position_daily"),
        day_fk(),
        UniqueConstraint(
            "account_id", "trade_date", "ts_code", name=conv("uq_paper_position_date_code")
        ),
        _check(
            "ck_paper_position_quantity",
            "quantity > 0 AND available_quantity BETWEEN 0 AND quantity",
        ),
        _check(
            "ck_paper_position_prices",
            finite_nonnegative("avg_cost")
            + " AND "
            + finite_nonnegative("close_price")
            + " AND close_price > 0 AND "
            + finite_nonnegative("market_value")
            + " AND "
            + finite_nonnegative("adj_factor")
            + " AND adj_factor > 0",
        ),
        _check("ck_paper_position_hash", "source_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_paper_position_pnl",
            "unrealized_pnl > '-Infinity'::numeric AND unrealized_pnl < 'Infinity'::numeric "
            "AND realized_pnl > '-Infinity'::numeric AND realized_pnl < 'Infinity'::numeric",
        ),
    )
    day_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    ts_code: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    adj_factor: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    valuation_source: Mapped[str] = mapped_column(String(24), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class PaperNavDaily(AccountRecord, Base):
    __tablename__ = "paper_nav_daily"
    __table_args__ = (
        *account_constraints("paper_nav_daily"),
        day_fk(),
        UniqueConstraint("account_id", "trade_date", name=conv("uq_paper_nav_date")),
        _check(
            "ck_paper_nav_amounts",
            " AND ".join(
                finite_nonnegative(c)
                for c in ("cash", "market_value", "total_assets", "nav", "trading_cost")
            )
            + " AND total_assets = cash + market_value",
        ),
        _check(
            "ck_paper_nav_benchmark",
            "benchmark_nav IS NULL OR (" + finite_nonnegative("benchmark_nav") + ")",
        ),
        _check(
            "ck_paper_nav_status",
            "status = 'FROZEN' AND benchmark_status IN ('READY','BENCHMARK_UNAVAILABLE') "
            "AND ((benchmark_status = 'READY' AND benchmark_nav IS NOT NULL) OR "
            "(benchmark_status = 'BENCHMARK_UNAVAILABLE' AND benchmark_nav IS NULL))",
        ),
        _check("ck_paper_nav_position_count", "position_count >= 0"),
        _check("ck_paper_nav_hash", "source_hash ~ '^[0-9a-f]{64}$'"),
    )
    day_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    benchmark_nav: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    benchmark_status: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_cost: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="FROZEN")


class PaperOutcomeReview(AccountRecord, Base):
    __tablename__ = "paper_outcome_review"
    __table_args__ = (
        *account_constraints("paper_outcome_review"),
        scoped_fk("proposal_id", "decision_proposal"),
        UniqueConstraint(
            "proposal_id",
            "asof_date",
            "window_days",
            "eval_version",
            name=conv("uq_paper_review_window"),
        ),
        _check("ck_paper_review_window", "window_days > 0"),
        _check("ck_paper_review_hash", "source_snapshot_hash ~ '^[0-9a-f]{64}$'"),
        _check("ck_paper_review_status", "status IN ('READY','PENDING','UNAVAILABLE')"),
    )
    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    eval_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
