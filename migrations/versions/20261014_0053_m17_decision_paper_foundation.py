"""Independent PAPER foundation. Never materialize history from BACKTEST runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql.naming import conv

revision: str = "0053_m17_decision_paper_foundation"
down_revision: str | None = "0052_m16_6_frozen_research_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "paper_account",
    "paper_account_event",
    "decision_observation",
    "decision_proposal",
    "decision_approval_event",
    "paper_day_run",
    "paper_order",
    "paper_order_attempt",
    "paper_fill",
    "paper_ledger_entry",
    "paper_position_daily",
    "paper_nav_daily",
    "paper_outcome_review",
)
IMMUTABLE = (
    "paper_account_event",
    "decision_observation",
    "decision_approval_event",
    "paper_order_attempt",
    "paper_fill",
    "paper_ledger_entry",
    "paper_position_daily",
    "paper_nav_daily",
    "paper_outcome_review",
)


def _col(name, type_, *, nullable=False):
    return sa.Column(name, type_, nullable=nullable)


def _uuid(name, *, nullable=False):
    return _col(name, pg.UUID(as_uuid=True), nullable=nullable)


def _str(name, length=64, *, nullable=False):
    return _col(name, sa.String(length), nullable=nullable)


def _num(name, scale=4, *, nullable=False):
    return _col(name, sa.Numeric(24, scale), nullable=nullable)


def _check(name, expression):
    return sa.CheckConstraint(expression, name=conv(name))


def _uq(name, *columns):
    return sa.UniqueConstraint(*columns, name=conv(name))


def _finite(column):
    return f"{column} >= 0 AND {column} < 'Infinity'::numeric AND {column} <> 'NaN'::numeric"


def _fk(column, parent, *, account=True):
    return sa.ForeignKeyConstraint(
        [column, "owner_user_id"] + (["account_id"] if account else []),
        [f"{parent}.id", f"{parent}.owner_user_id"] + ([f"{parent}.account_id"] if account else []),
        ondelete="RESTRICT",
    )


def _date_fk(column, parent):
    return sa.ForeignKeyConstraint(
        [column, "owner_user_id", "account_id", "trade_date"],
        [f"{parent}.id", f"{parent}.owner_user_id", f"{parent}.account_id", f"{parent}.trade_date"],
        ondelete="RESTRICT",
    )


def _request(table):
    return (
        _str("request_id", 128),
        _str("request_hash"),
        _uq(f"uq_{table}_request", "owner_user_id", "request_id"),
        _check(f"ck_{table}_request_hash", "request_hash ~ '^[0-9a-f]{64}$'"),
    )


def _table(table, *elements, account=True):
    columns = [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _uuid("owner_user_id"),
        _str("schema_version"),
        _col("record_json", pg.JSONB()),
        _str("record_hash"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="RESTRICT"),
        _uq(f"uq_{table}_owner", "id", "owner_user_id"),
        _check(f"ck_{table}_hash", "record_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            f"ck_{table}_json",
            "jsonb_typeof(record_json) = 'object' AND "
            "record_json->>'schema_version' = schema_version AND "
            "jsonb_typeof(record_json->'schema_version') = 'string' AND "
            "record_json ? 'schema_version' AND length(schema_version) > 0 AND "
            "octet_length(record_json::text) <= 131072",
        ),
    ]
    if account:
        columns.extend(
            [
                _uuid("account_id"),
                _fk("account_id", "paper_account", account=False),
                _uq(f"uq_{table}_scope", "id", "owner_user_id", "account_id"),
            ]
        )
    op.create_table(table, *columns, *elements)
    op.create_index(f"idx_{table}_owner_created", table, ["owner_user_id", "created_at", "id"])
    if account:
        op.create_index(f"idx_{table}_account", table, ["account_id", "created_at", "id"])


def upgrade() -> None:
    _table(
        "paper_account",
        _str("name", 80),
        _str("mode", 8),
        _str("state", 16),
        _num("initial_cash"),
        _str("benchmark_code", 24),
        _col("first_trade_date", sa.Date()),
        _str("config_version"),
        _col("config_snapshot_json", pg.JSONB()),
        _str("config_hash"),
        _col("activated_at", sa.DateTime(timezone=True), nullable=True),
        _col("version", sa.Integer()),
        *_request("paper_account"),
        _uq("uq_paper_account_name", "owner_user_id", "name"),
        _check("ck_paper_account_state", "state IN ('CREATED','ACTIVE','PAUSED','CLOSED')"),
        _check("ck_paper_account_mode", "mode = 'PAPER'"),
        _check("ck_paper_account_cash", _finite("initial_cash") + " AND initial_cash > 0"),
        _check("ck_paper_account_config_hash", "config_hash ~ '^[0-9a-f]{64}$'"),
        _check("ck_paper_account_version", "version >= 1"),
        _check("ck_paper_account_name", "length(trim(name)) > 0"),
        _check(
            "ck_paper_account_config",
            "jsonb_typeof(config_snapshot_json) = 'object' AND "
            "config_snapshot_json ? 'schema_version' AND "
            "octet_length(config_snapshot_json::text) <= 131072",
        ),
        account=False,
    )
    _table(
        "paper_account_event",
        _str("from_state", 16, nullable=True),
        _str("to_state", 16),
        *_request("paper_account_event"),
        _check(
            "ck_paper_account_event_state", "to_state IN ('CREATED','ACTIVE','PAUSED','CLOSED')"
        ),
    )
    _table(
        "decision_observation",
        _col("signal_date", sa.Date()),
        _str("source_status", 16),
        _col("asof_cutoff", sa.DateTime(timezone=True)),
        _col("ready_at", sa.DateTime(timezone=True)),
        _str("strategy_identity_hash"),
        *_request("decision_observation"),
        _check(
            "ck_decision_observation_identity_hash", "strategy_identity_hash ~ '^[0-9a-f]{64}$'"
        ),
        _check("ck_decision_observation_status", "source_status = 'READY'"),
        _check(
            "ck_decision_observation_cutoff",
            "ready_at <= asof_cutoff AND asof_cutoff <= created_at",
        ),
        account=False,
    )
    op.create_index(
        "idx_decision_observation_date", "decision_observation", ["owner_user_id", "signal_date"]
    )
    _table(
        "decision_proposal",
        _uuid("observation_id"),
        _uuid("supersedes_id", nullable=True),
        _str("ts_code", 16),
        _str("action", 24),
        _col("target_weight", sa.Numeric(12, 8)),
        _str("stage", 24),
        _col("score", sa.Numeric(16, 8)),
        _col("revision", sa.Integer()),
        _col("version", sa.Integer()),
        _str("state", 24),
        _col("expires_at", sa.DateTime(timezone=True)),
        *_request("decision_proposal"),
        _fk("observation_id", "decision_observation", account=False),
        _fk("supersedes_id", "decision_proposal"),
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
        _check("ck_decision_proposal_weight", _finite("target_weight") + " AND target_weight <= 1"),
        _check("ck_decision_proposal_score", _finite("score")),
        _check("ck_decision_proposal_expiry", "expires_at > created_at"),
    )
    _table(
        "decision_approval_event",
        _uuid("proposal_id"),
        _uuid("actor_user_id"),
        _str("decision", 16),
        _col("approved_target_weight", sa.Numeric(12, 8)),
        _col("event_at", sa.DateTime(timezone=True)),
        *_request("decision_approval_event"),
        _fk("proposal_id", "decision_proposal"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="RESTRICT"),
        _uq("uq_decision_approval_event_proposal", "proposal_id"),
        _uq(
            "uq_decision_approval_event_proposal_scope",
            "id",
            "owner_user_id",
            "account_id",
            "proposal_id",
        ),
        _check("ck_decision_approval_event_actor", "actor_user_id = owner_user_id"),
        _check("ck_decision_approval_event_decision", "decision IN ('APPROVED','REJECTED')"),
        _check(
            "ck_decision_approval_event_weight",
            _finite("approved_target_weight") + " AND approved_target_weight <= 1",
        ),
    )
    _table(
        "paper_day_run",
        _col("trade_date", sa.Date()),
        _str("phase", 24),
        _str("status", 24),
        _str("source_hash"),
        _str("input_hash"),
        _str("result_hash", nullable=True),
        _col("generation", sa.Integer()),
        _str("lease_owner", 128, nullable=True),
        _col("lease_until", sa.DateTime(timezone=True), nullable=True),
        _uuid("job_id", nullable=True),
        _str("error_code", nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["job_run.id"], ondelete="RESTRICT"),
        _uq("uq_paper_day_run_phase", "account_id", "trade_date", "phase"),
        _uq("uq_paper_day_run_date", "id", "owner_user_id", "account_id", "trade_date"),
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
    _table(
        "paper_order",
        _uuid("approval_id"),
        _uuid("proposal_id"),
        _col("signal_date", sa.Date()),
        _col("scheduled_date", sa.Date()),
        _str("ts_code", 16),
        _str("side", 8),
        _col("quantity", sa.Integer()),
        _col("target_weight", sa.Numeric(12, 8)),
        _str("order_type", 16),
        _str("mode", 8),
        _str("status", 24),
        _col("version", sa.Integer()),
        _str("source_hash"),
        _str("reason_code", nullable=True),
        sa.ForeignKeyConstraint(
            ["approval_id", "owner_user_id", "account_id", "proposal_id"],
            [
                "decision_approval_event.id",
                "decision_approval_event.owner_user_id",
                "decision_approval_event.account_id",
                "decision_approval_event.proposal_id",
            ],
            ondelete="RESTRICT",
        ),
        _uq("uq_paper_order_approval", "approval_id"),
        _check("ck_paper_order_type", "order_type = 'NEXT_OPEN' AND mode = 'PAPER'"),
        _check("ck_paper_order_side", "side IN ('BUY','SELL')"),
        _check("ck_paper_order_dates", "scheduled_date > signal_date"),
        _check("ck_paper_order_quantity", "quantity > 0"),
        _check("ck_paper_order_weight", _finite("target_weight") + " AND target_weight <= 1"),
        _check("ck_paper_order_hash", "source_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_paper_order_state",
            "status IN ('ORDER_PENDING','FILLED','SKIPPED','CANCELLED','EXPIRED')",
        ),
        _check("ck_paper_order_version", "version >= 1"),
    )
    op.create_index(
        "idx_paper_order_schedule", "paper_order", ["account_id", "scheduled_date", "status"]
    )
    op.create_index(
        "uq_paper_order_pending_code",
        "paper_order",
        ["account_id", "ts_code"],
        unique=True,
        postgresql_where=sa.text("status = 'ORDER_PENDING'"),
    )
    _table(
        "paper_order_attempt",
        _uuid("order_id"),
        _col("trade_date", sa.Date()),
        _col("attempt_no", sa.Integer()),
        _str("outcome", 24),
        _str("reason_code", nullable=True),
        _str("market_snapshot_hash"),
        _str("execution_policy_version"),
        _fk("order_id", "paper_order"),
        _uq("uq_paper_attempt_key", "order_id", "trade_date", "attempt_no"),
        _uq(
            "uq_paper_attempt_order_date",
            "id",
            "owner_user_id",
            "account_id",
            "order_id",
            "trade_date",
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
    _table(
        "paper_fill",
        _uuid("order_id"),
        _uuid("attempt_id"),
        _col("trade_date", sa.Date()),
        _str("ts_code", 16),
        _str("side", 8),
        _col("quantity", sa.Integer()),
        *(
            _num(c)
            for c in (
                "ref_open_price",
                "simulated_price",
                "gross_amount",
                "cash_fee_total",
                "total_cost",
                "cash_delta",
            )
        ),
        _col("fee_json", pg.JSONB()),
        sa.ForeignKeyConstraint(
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
        _uq("uq_paper_fill_attempt", "attempt_id"),
        _uq("uq_paper_fill_date", "id", "owner_user_id", "account_id", "trade_date"),
        _check("ck_paper_fill_quantity", "quantity > 0 AND side IN ('BUY','SELL')"),
        _check(
            "ck_paper_fill_price",
            _finite("ref_open_price")
            + " AND ref_open_price > 0 AND "
            + _finite("simulated_price")
            + " AND simulated_price > 0",
        ),
        _check(
            "ck_paper_fill_amounts",
            _finite("cash_fee_total")
            + " AND "
            + _finite("total_cost")
            + " AND total_cost >= cash_fee_total AND "
            + _finite("gross_amount")
            + " AND gross_amount > 0 AND "
            "cash_delta = CASE WHEN side = 'BUY' THEN -gross_amount - cash_fee_total "
            "ELSE gross_amount - cash_fee_total END",
        ),
        _check(
            "ck_paper_fill_json",
            "jsonb_typeof(fee_json) = 'object' AND fee_json ? 'schema_version' "
            "AND octet_length(fee_json::text) <= 4096",
        ),
    )
    _table(
        "paper_ledger_entry",
        _uuid("day_run_id", nullable=True),
        _uuid("fill_id", nullable=True),
        _col("trade_date", sa.Date()),
        _str("business_key", 160),
        _str("entry_type", 24),
        _num("cash_delta"),
        _col("quantity_delta", sa.Integer()),
        _str("instrument", 16, nullable=True),
        _date_fk("day_run_id", "paper_day_run"),
        _date_fk("fill_id", "paper_fill"),
        _uq("uq_paper_ledger_key", "account_id", "business_key"),
        _uq("uq_paper_ledger_fill", "fill_id"),
        _check(
            "ck_paper_ledger_entry",
            "(entry_type = 'INITIAL_CASH' AND fill_id IS NULL AND day_run_id IS NULL "
            "AND cash_delta > 0 AND quantity_delta = 0 AND instrument IS NULL) OR "
            "(entry_type = 'FILL' AND fill_id IS NOT NULL AND day_run_id IS NOT NULL "
            "AND instrument IS NOT NULL AND quantity_delta <> 0)",
        ),
        _check(
            "ck_paper_ledger_finite",
            "cash_delta > '-Infinity'::numeric AND cash_delta < 'Infinity'::numeric "
            "AND cash_delta <> 'NaN'::numeric",
        ),
    )
    op.create_index(
        "uq_paper_ledger_initial",
        "paper_ledger_entry",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("entry_type = 'INITIAL_CASH'"),
    )
    _table(
        "paper_position_daily",
        _uuid("day_run_id"),
        _col("trade_date", sa.Date()),
        _str("ts_code", 16),
        _col("quantity", sa.Integer()),
        _col("available_quantity", sa.Integer()),
        _num("avg_cost", 8),
        *(_num(c) for c in ("close_price", "market_value", "unrealized_pnl", "realized_pnl")),
        _num("adj_factor", 10),
        _str("valuation_source", 24),
        _str("source_hash"),
        _date_fk("day_run_id", "paper_day_run"),
        _uq("uq_paper_position_date_code", "account_id", "trade_date", "ts_code"),
        _check(
            "ck_paper_position_quantity",
            "quantity > 0 AND available_quantity BETWEEN 0 AND quantity",
        ),
        _check(
            "ck_paper_position_prices",
            _finite("avg_cost")
            + " AND "
            + _finite("close_price")
            + " AND close_price > 0 AND "
            + _finite("market_value")
            + " AND "
            + _finite("adj_factor")
            + " AND adj_factor > 0",
        ),
        _check("ck_paper_position_hash", "source_hash ~ '^[0-9a-f]{64}$'"),
        _check(
            "ck_paper_position_pnl",
            "unrealized_pnl > '-Infinity'::numeric AND unrealized_pnl < 'Infinity'::numeric "
            "AND realized_pnl > '-Infinity'::numeric AND realized_pnl < 'Infinity'::numeric",
        ),
    )
    _table(
        "paper_nav_daily",
        _uuid("day_run_id"),
        _col("trade_date", sa.Date()),
        *(_num(c) for c in ("cash", "market_value", "total_assets")),
        _num("nav", 8),
        _num("benchmark_nav", 8, nullable=True),
        _str("benchmark_status", 32),
        _num("trading_cost"),
        _col("position_count", sa.Integer()),
        _str("source_hash"),
        _str("status", 16),
        _date_fk("day_run_id", "paper_day_run"),
        _uq("uq_paper_nav_date", "account_id", "trade_date"),
        _check(
            "ck_paper_nav_amounts",
            " AND ".join(
                _finite(c) for c in ("cash", "market_value", "total_assets", "nav", "trading_cost")
            )
            + " AND total_assets = cash + market_value",
        ),
        _check(
            "ck_paper_nav_benchmark", "benchmark_nav IS NULL OR (" + _finite("benchmark_nav") + ")"
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
    _table(
        "paper_outcome_review",
        _uuid("proposal_id"),
        _col("asof_date", sa.Date()),
        _col("window_days", sa.Integer()),
        _str("eval_version"),
        _str("source_snapshot_hash"),
        _str("status", 16),
        _fk("proposal_id", "decision_proposal"),
        _uq("uq_paper_review_window", "proposal_id", "asof_date", "window_days", "eval_version"),
        _check("ck_paper_review_window", "window_days > 0"),
        _check("ck_paper_review_hash", "source_snapshot_hash ~ '^[0-9a-f]{64}$'"),
        _check("ck_paper_review_status", "status IN ('READY','PENDING','UNAVAILABLE')"),
    )
    _install_guards()


def _install_guards():
    op.execute("""
    CREATE FUNCTION prevent_m17_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'M17_APPEND_ONLY';
    END $$;
    """)
    for table in IMMUTABLE:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_m17_rewrite()"
        )
    op.execute("""
    CREATE FUNCTION guard_m17_transition() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE allowed text[]; before_state text; after_state text; legal boolean := false;
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'M17_APPEND_ONLY'; END IF;
      IF TG_TABLE_NAME = 'paper_day_run' THEN
        allowed := ARRAY['status','result_hash','generation','lease_owner',
                         'lease_until','job_id','error_code'];
        IF (OLD.status IN ('SUCCESS','REVIEW_REQUIRED') AND
            ((to_jsonb(NEW)-ARRAY['status','error_code']) IS DISTINCT FROM
             (to_jsonb(OLD)-ARRAY['status','error_code']) OR NEW.status <> 'REVIEW_REQUIRED')) THEN
          RAISE EXCEPTION 'M17_SEALED_DAY';
        END IF;
        IF NEW.status <> OLD.status AND NOT (
          (OLD.status = 'QUEUED' AND NEW.status IN ('RUNNING','CANCELLED')) OR
          (OLD.status = 'RUNNING' AND NEW.status IN ('SUCCESS','FAILED','CANCELLED')) OR
          (OLD.status = 'FAILED' AND NEW.status = 'RUNNING') OR
          (OLD.status = 'SUCCESS' AND NEW.status = 'REVIEW_REQUIRED')
        ) THEN RAISE EXCEPTION 'M17_INVALID_STATE_TRANSITION'; END IF;
      ELSE
        IF TG_TABLE_NAME = 'paper_account' THEN
          allowed := ARRAY['state','version','activated_at'];
          before_state := OLD.state; after_state := NEW.state;
          legal := (before_state = 'CREATED' AND after_state IN ('ACTIVE','PAUSED','CLOSED')) OR
                   (before_state = 'ACTIVE' AND after_state IN ('PAUSED','CLOSED')) OR
                   (before_state = 'PAUSED' AND after_state IN ('ACTIVE','CLOSED'));
          IF OLD.activated_at IS NOT NULL AND
             NEW.activated_at IS DISTINCT FROM OLD.activated_at THEN
            RAISE EXCEPTION 'M17_FROZEN_ACTIVATION';
          END IF;
        ELSIF TG_TABLE_NAME = 'decision_proposal' THEN
          allowed := ARRAY['state','version'];
          before_state := OLD.state; after_state := NEW.state;
          legal := (before_state = 'DRAFT' AND after_state IN ('PENDING_REVIEW','EXPIRED')) OR
                   (before_state = 'PENDING_REVIEW' AND
                    after_state IN ('APPROVED','REJECTED','EXPIRED'));
        ELSE
          allowed := ARRAY['status','version','reason_code'];
          before_state := OLD.status; after_state := NEW.status;
          legal := before_state = 'ORDER_PENDING' AND
                   after_state IN ('FILLED','SKIPPED','CANCELLED','EXPIRED');
        END IF;
        IF NOT legal OR NEW.version <> OLD.version + 1 THEN
          RAISE EXCEPTION 'M17_INVALID_STATE_TRANSITION';
        END IF;
      END IF;
      IF (to_jsonb(NEW)-allowed) IS DISTINCT FROM (to_jsonb(OLD)-allowed) THEN
        RAISE EXCEPTION 'M17_FROZEN_IDENTITY';
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in ("paper_account", "decision_proposal", "paper_order", "paper_day_run"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_transition BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION guard_m17_transition()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table in TABLES:
        if connection.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("refusing to downgrade M17 while decision or PAPER records exist")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION guard_m17_transition()")
    op.execute("DROP FUNCTION prevent_m17_rewrite()")
