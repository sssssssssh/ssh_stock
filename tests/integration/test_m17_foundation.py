import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from app.domain.decision.contracts import checked_snapshot
from app.models.auth import AppUser
from app.models.base import Base
from app.models.paper import (
    DecisionApprovalEvent,
    DecisionObservation,
    DecisionProposal,
    PaperAccount,
    PaperAccountEvent,
    PaperDayRun,
    PaperFill,
    PaperLedgerEntry,
    PaperNavDaily,
    PaperOrder,
    PaperOrderAttempt,
    PaperOutcomeReview,
    PaperPositionDaily,
)
from m16_6_support import isolated_contract_database
from sqlalchemy.exc import DBAPIError
from test_m16_4_research_reports import _source, _user

HEAD = "0053_m17_decision_paper_foundation"
PARENT = "0052_m16_6_frozen_research_contracts"
MODELS = (
    PaperAccount,
    PaperAccountEvent,
    DecisionObservation,
    DecisionProposal,
    DecisionApprovalEvent,
    PaperDayRun,
    PaperOrder,
    PaperOrderAttempt,
    PaperFill,
    PaperLedgerEntry,
    PaperPositionDaily,
    PaperNavDaily,
    PaperOutcomeReview,
)
IMMUTABLE = (
    PaperAccountEvent,
    DecisionObservation,
    DecisionApprovalEvent,
    PaperOrderAttempt,
    PaperFill,
    PaperLedgerEntry,
    PaperPositionDaily,
    PaperNavDaily,
    PaperOutcomeReview,
)
DAY = date(2026, 10, 15)
NOW = datetime(2026, 10, 14, 10, tzinfo=UTC)


@pytest.fixture
def database(monkeypatch):
    with isolated_contract_database(monkeypatch) as resources:
        yield resources


def record(owner, **values):
    snapshot, digest = checked_snapshot({"schema_version": "m17-test-v1", "fixture": "synthetic"})
    return {
        "id": uuid.uuid4(),
        "owner_user_id": owner.id,
        "schema_version": "m17-test-v1",
        "record_json": snapshot,
        "record_hash": digest,
        "created_at": NOW,
        **values,
    }


def graph(db):
    owner = AppUser(
        id=uuid.uuid4(),
        username=uuid.uuid4().hex,
        password_hash="synthetic",
        is_active=True,
        must_change_password=False,
    )
    other = AppUser(
        id=uuid.uuid4(),
        username=uuid.uuid4().hex,
        password_hash="synthetic",
        is_active=True,
        must_change_password=False,
    )
    db.add_all([owner, other])
    db.flush()
    account = PaperAccount(
        **record(
            owner,
            name="synthetic",
            mode="PAPER",
            state="PAUSED",
            initial_cash=Decimal("10000"),
            benchmark_code="000300.SH",
            first_trade_date=DAY,
            config_version="m17-paper-policy-v1",
            config_snapshot_json={"schema_version": "m17-paper-policy-v1"},
            config_hash="a" * 64,
            version=1,
            request_id="create",
            request_hash="b" * 64,
        )
    )
    db.add(account)
    db.flush()
    scope = {"account_id": account.id}
    event = PaperAccountEvent(
        **record(
            owner,
            **scope,
            from_state=None,
            to_state="PAUSED",
            request_id="creation",
            request_hash="a" * 64,
        )
    )
    observation = DecisionObservation(
        **record(
            owner,
            signal_date=DAY - timedelta(days=1),
            source_status="READY",
            ready_at=NOW,
            asof_cutoff=NOW,
            strategy_identity_hash="a" * 64,
            request_id="observe",
            request_hash="b" * 64,
        )
    )
    db.add_all([event, observation])
    db.flush()
    proposal = DecisionProposal(
        **record(
            owner,
            **scope,
            observation_id=observation.id,
            ts_code="000001.SZ",
            action="PROPOSE_BUY",
            target_weight=Decimal("0.1"),
            stage="TREND",
            score=Decimal("82"),
            revision=1,
            version=1,
            state="PENDING_REVIEW",
            expires_at=NOW + timedelta(days=1),
            request_id="proposal",
            request_hash="a" * 64,
        )
    )
    db.add(proposal)
    db.flush()
    approval = DecisionApprovalEvent(
        **record(
            owner,
            **scope,
            proposal_id=proposal.id,
            actor_user_id=owner.id,
            decision="APPROVED",
            approved_target_weight=Decimal("0.1"),
            event_at=NOW,
            request_id="approve",
            request_hash="b" * 64,
        )
    )
    day_run = PaperDayRun(
        **record(
            owner,
            **scope,
            trade_date=DAY,
            phase="EXECUTION",
            status="RUNNING",
            source_hash="a" * 64,
            input_hash="b" * 64,
            generation=1,
        )
    )
    db.add_all([approval, day_run])
    db.flush()
    order = PaperOrder(
        **record(
            owner,
            **scope,
            approval_id=approval.id,
            proposal_id=proposal.id,
            signal_date=DAY - timedelta(days=1),
            scheduled_date=DAY,
            ts_code="000001.SZ",
            side="BUY",
            quantity=100,
            target_weight=Decimal("0.1"),
            order_type="NEXT_OPEN",
            mode="PAPER",
            status="ORDER_PENDING",
            version=1,
            source_hash="a" * 64,
        )
    )
    db.add(order)
    db.flush()
    attempt = PaperOrderAttempt(
        **record(
            owner,
            **scope,
            order_id=order.id,
            trade_date=DAY,
            attempt_no=1,
            outcome="FILLED",
            market_snapshot_hash="a" * 64,
            execution_policy_version="paper-execution-v1",
        )
    )
    db.add(attempt)
    db.flush()
    fill = PaperFill(
        **record(
            owner,
            **scope,
            order_id=order.id,
            attempt_id=attempt.id,
            trade_date=DAY,
            ts_code=order.ts_code,
            side="BUY",
            quantity=100,
            ref_open_price=Decimal("10"),
            simulated_price=Decimal("10"),
            gross_amount=Decimal("1000"),
            cash_fee_total=Decimal("5"),
            total_cost=Decimal("5"),
            cash_delta=Decimal("-1005"),
            fee_json={"schema_version": "paper-cost-v1", "commission": "5"},
        )
    )
    db.add(fill)
    db.flush()
    ledger = PaperLedgerEntry(
        **record(
            owner,
            **scope,
            day_run_id=day_run.id,
            fill_id=fill.id,
            trade_date=DAY,
            business_key="fill:" + str(fill.id),
            entry_type="FILL",
            cash_delta=Decimal("-1005"),
            quantity_delta=100,
            instrument=order.ts_code,
        )
    )
    position = PaperPositionDaily(
        **record(
            owner,
            **scope,
            day_run_id=day_run.id,
            trade_date=DAY,
            ts_code=order.ts_code,
            quantity=100,
            available_quantity=0,
            avg_cost=Decimal("10.05"),
            close_price=Decimal("11"),
            market_value=Decimal("1100"),
            unrealized_pnl=Decimal("95"),
            realized_pnl=Decimal("0"),
            adj_factor=Decimal("1"),
            valuation_source="RAW_CLOSE",
            source_hash="a" * 64,
        )
    )
    nav = PaperNavDaily(
        **record(
            owner,
            **scope,
            day_run_id=day_run.id,
            trade_date=DAY,
            cash=Decimal("8995"),
            market_value=Decimal("1100"),
            total_assets=Decimal("10095"),
            nav=Decimal("1.0095"),
            benchmark_status="BENCHMARK_UNAVAILABLE",
            trading_cost=Decimal("5"),
            position_count=1,
            source_hash="a" * 64,
            status="FROZEN",
        )
    )
    review = PaperOutcomeReview(
        **record(
            owner,
            **scope,
            proposal_id=proposal.id,
            asof_date=DAY,
            window_days=1,
            eval_version="m17-review-v1",
            source_snapshot_hash=proposal.record_hash,
            status="PENDING",
        )
    )
    db.add_all([ledger, position, nav, review])
    db.flush()
    return (
        owner,
        other,
        dict(
            zip(
                MODELS,
                (
                    account,
                    event,
                    observation,
                    proposal,
                    approval,
                    day_run,
                    order,
                    attempt,
                    fill,
                    ledger,
                    position,
                    nav,
                    review,
                ),
                strict=True,
            )
        ),
    )


def test_0053_roundtrip_preserves_actual_legacy_rows_and_hashes(database):
    factory, engine = database
    with factory() as db:
        owner = _user(db, "m17-legacy")
        _source(db, owner, value="0.2")
        before = db.scalar(
            sa.text(
                "SELECT md5(string_agg(row_to_json(m)::text, '' ORDER BY id)) "
                "FROM agent_chat_message m"
            )
        )
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, PARENT)
        assert not sa.inspect(connection).has_table("paper_account")
        command.upgrade(config, HEAD)
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == HEAD
        assert (
            connection.scalar(
                sa.text(
                    "SELECT md5(string_agg(row_to_json(m)::text, '' ORDER BY id)) "
                    "FROM agent_chat_message m"
                )
            )
            == before
        )
        context = MigrationContext.configure(
            connection,
            opts={
                "include_object": lambda obj, name, type_, reflected, compare_to: (
                    name in {m.__tablename__ for m in MODELS} if type_ == "table" else True
                ),
            },
        )
        assert compare_metadata(context, Base.metadata) == []


def test_any_paper_history_blocks_downgrade_and_does_not_delete(database):
    factory, engine = database
    with factory() as db:
        _, _, rows = graph(db)
        ledger_id = rows[PaperLedgerEntry].id
        db.commit()
    config = Config("alembic.ini")
    with pytest.raises(RuntimeError, match="refusing to downgrade M17"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, PARENT)
    with factory() as db:
        assert db.get(PaperLedgerEntry, ledger_id).cash_delta == Decimal("-1005")
        assert db.scalar(sa.text("SELECT version_num FROM alembic_version")) == HEAD


@pytest.mark.parametrize("model", IMMUTABLE)
def test_immutable_rows_reject_update_and_delete(database, model):
    factory, _ = database
    with factory() as db:
        _, _, rows = graph(db)
        row = rows[model]
        for statement in (
            sa.update(model)
            .where(model.id == row.id)
            .values(record_json={"schema_version": "rewritten"}),
            sa.delete(model).where(model.id == row.id),
        ):
            with pytest.raises(DBAPIError, match="M17_APPEND_ONLY"), db.begin_nested():
                db.execute(statement)
        assert db.get(model, row.id).record_hash == row.record_hash


def test_owner_account_date_fks_and_unique_keys_reject_bad_insertions(database):
    factory, _ = database
    with factory() as db:
        _, other, rows = graph(db)
        for model, row in rows.items():
            values = {column.name: getattr(row, column.name) for column in model.__table__.columns}
            for bad in ({"id": uuid.uuid4()}, {"id": uuid.uuid4(), "owner_user_id": other.id}):
                # Owner-independent Observation/Account are constrained by per-owner request/name,
                # while every downstream record is constrained by the composite parent identity.
                if model in (PaperAccount, DecisionObservation) and "owner_user_id" in bad:
                    continue
                with pytest.raises(DBAPIError), db.begin_nested():
                    db.execute(sa.insert(model).values({**values, **bad}))
        for model in (PaperPositionDaily, PaperNavDaily, PaperFill, PaperLedgerEntry):
            row = rows[model]
            values = {c.name: getattr(row, c.name) for c in model.__table__.columns}
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(
                    sa.insert(model).values(
                        {**values, "id": uuid.uuid4(), "trade_date": DAY + timedelta(days=1)}
                    )
                )


def test_financial_and_json_constraints_are_real_postgresql_checks(database):
    factory, _ = database
    with factory() as db:
        _, _, rows = graph(db)
        for model, field, value in (
            (PaperAccount, "mode", "LIVE"),
            (PaperAccount, "initial_cash", Decimal("NaN")),
            (PaperAccount, "initial_cash", Decimal("-1")),
            (PaperAccount, "record_hash", "bad"),
            (PaperAccount, "record_json", {}),
            (PaperAccount, "record_json", {"schema_version": None}),
            (PaperPositionDaily, "available_quantity", 101),
            (PaperNavDaily, "total_assets", Decimal("1")),
            (PaperNavDaily, "benchmark_nav", Decimal("0")),
            (PaperFill, "cash_delta", Decimal("0")),
            (DecisionApprovalEvent, "actor_user_id", uuid.uuid4()),
        ):
            row = rows[model]
            values = {c.name: getattr(row, c.name) for c in model.__table__.columns}
            with pytest.raises(DBAPIError, match="violates check constraint"), db.begin_nested():
                db.execute(sa.insert(model).values({**values, "id": uuid.uuid4(), field: value}))


@pytest.mark.parametrize(
    "model", [model for model in MODELS if model not in (PaperAccount, DecisionObservation)]
)
def test_first_insert_cross_owner_rejected_by_actual_scoped_fk(database, monkeypatch, model):
    factory, _ = database
    with factory() as db:
        original_add = db.add

        def add_with_wrong_owner(row, *args, **kwargs):
            if isinstance(row, model):
                other_owner = db.scalar(
                    sa.select(AppUser.id).where(AppUser.id != row.owner_user_id).limit(1)
                )
                assert other_owner is not None
                row.owner_user_id = other_owner
                if isinstance(row, DecisionApprovalEvent):
                    row.actor_user_id = other_owner
            return original_add(row, *args, **kwargs)

        monkeypatch.setattr(db, "add", add_with_wrong_owner)
        # First insert, not a conflicting duplicate: the error must be a scoped FK.
        with pytest.raises(DBAPIError, match="violates foreign key constraint"):
            graph(db)


def test_mutable_heads_only_accept_valid_transitions_and_frozen_identities(database):
    factory, _ = database
    with factory() as db:
        _, _, rows = graph(db)
        account = rows[PaperAccount]
        db.execute(
            sa.update(PaperAccount)
            .where(PaperAccount.id == account.id)
            .values(state="ACTIVE", version=2, activated_at=NOW)
        )
        db.execute(
            sa.update(PaperAccount)
            .where(PaperAccount.id == account.id)
            .values(state="PAUSED", version=3)
        )
        for values in (
            {"state": "ACTIVE", "version": 3},
            {"state": "ACTIVE", "version": 4, "initial_cash": Decimal("1")},
            {"state": "ACTIVE", "version": 4, "activated_at": NOW + timedelta(seconds=1)},
        ):
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(
                    sa.update(PaperAccount).where(PaperAccount.id == account.id).values(**values)
                )
        db.execute(
            sa.update(PaperAccount)
            .where(PaperAccount.id == account.id)
            .values(state="CLOSED", version=4)
        )
        with pytest.raises(DBAPIError, match="M17_INVALID_STATE_TRANSITION"), db.begin_nested():
            db.execute(
                sa.update(PaperAccount)
                .where(PaperAccount.id == account.id)
                .values(state="ACTIVE", version=5)
            )
        for model, field, value in (
            (DecisionProposal, "state", "APPROVED"),
            (PaperOrder, "status", "FILLED"),
        ):
            row = rows[model]
            with pytest.raises(DBAPIError, match="M17_FROZEN_IDENTITY"), db.begin_nested():
                db.execute(
                    sa.update(model)
                    .where(model.id == row.id)
                    .values(**{field: value, "version": 2, "ts_code": "600000.SH"})
                )
            db.execute(
                sa.update(model).where(model.id == row.id).values(**{field: value, "version": 2})
            )
            with pytest.raises(DBAPIError, match="M17_INVALID_STATE_TRANSITION"), db.begin_nested():
                db.execute(
                    sa.update(model)
                    .where(model.id == row.id)
                    .values(**{field: value, "version": 3})
                )
        day = rows[PaperDayRun]
        db.execute(
            sa.update(PaperDayRun)
            .where(PaperDayRun.id == day.id)
            .values(status="SUCCESS", result_hash="a" * 64)
        )
        with pytest.raises(DBAPIError, match="M17_SEALED_DAY"), db.begin_nested():
            db.execute(
                sa.update(PaperDayRun).where(PaperDayRun.id == day.id).values(result_hash="b" * 64)
            )
        db.execute(
            sa.update(PaperDayRun)
            .where(PaperDayRun.id == day.id)
            .values(status="REVIEW_REQUIRED", error_code="PAPER_SOURCE_DRIFT")
        )
        assert (
            db.scalar(sa.select(PaperDayRun.result_hash).where(PaperDayRun.id == day.id))
            == "a" * 64
        )
        for model in (PaperAccount, DecisionProposal, PaperOrder, PaperDayRun):
            with pytest.raises(DBAPIError, match="M17_APPEND_ONLY"), db.begin_nested():
                db.execute(sa.delete(model).where(model.id == rows[model].id))
