"""Isolated PG17 measurements for frozen summaries and real daily job execution."""

import json
import os
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import pytest
from app.core.retention_config import RetentionPolicy
from app.domain.decision.account_requests import AdvancePaperAccount
from app.domain.decision.contracts import PaperError, content_hash
from app.domain.decision.requests import (
    ApproveProposal,
    CreateObservation,
    CreateProposal,
    PaperRequest,
)
from app.models.auth import AppUser
from app.models.job import JobRun
from app.models.market_data import DataDirtyRange, TradeCalendar
from app.models.paper import (
    DecisionApprovalEvent,
    DecisionObservation,
    DecisionProposal,
    PaperAccount,
    PaperDayRun,
    PaperFill,
    PaperLedgerEntry,
    PaperNavDaily,
    PaperOrder,
    PaperOrderAttempt,
    PaperOutcomeReview,
    PaperPositionDaily,
)
from app.services.decision.application import DecisionApplication
from app.services.decision.approval import ApprovalApplication
from app.services.paper.accounts import PaperAccountApplication
from app.services.paper.job_application import PaperJobApplication
from app.services.paper.performance import PaperPerformance
from app.services.paper.queue import PAPER_DAILY, PaperQueue
from app.services.paper.records import make_record, open_cutoff, verify_record
from app.services.portfolio.ledger_precision import ratio
from app.services.retention import run_retention
from sqlalchemy import event, func, select

from tests.integration.m16_6_support import isolated_contract_database
from tests.integration.m17_support import CODES, DAY, NOW, seed, settings
from tests.integration.test_m17_1_paper_continuity import frozen_records

# Two-symbol fixtures exercise full source checks, queue/claim and atomic job settlement.
# Fix these budgets before running CI; history length must not introduce per-day SQL growth.
DAILY_SQL_BUDGET = 400
DAILY_SECONDS_BUDGET = 15


@pytest.fixture(scope="module")
def capacity_database():
    with pytest.MonkeyPatch.context() as patch:
        with isolated_contract_database(patch) as database:
            yield database


def emit_measurement(measurement):
    encoded = json.dumps(measurement, sort_keys=True)
    print("M17_MEASUREMENT " + encoded)
    if destination := os.environ.get("M17_MEASUREMENT_PATH"):
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write(encoded + "\n")


def trading_dates(count):
    days, day = [], date(2025, 1, 2)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def seed_frozen_ledger(db, count):
    """One fee-paying buy per day, conserved ledger, T+1 shares, genuine ORM constraints."""
    owner = uuid.uuid4()
    db.add(AppUser(id=owner, username=owner.hex, password_hash="synthetic", is_active=True))
    db.flush()
    days = trading_dates(count + 1)
    created = datetime.combine(days[0], time(0), UTC)
    config = {"schema_version": "m17-capacity-synthetic-config-v1"}
    account = make_record(
        PaperAccount,
        owner,
        "account",
        now=created,
        name="synthetic-capacity",
        state="ACTIVE",
        mode="PAPER",
        initial_cash=Decimal("1000000"),
        benchmark_code="999999.SH",
        first_trade_date=days[1],
        config_version="synthetic-v1",
        config_snapshot_json=config,
        config_hash=content_hash(config),
        request_id="account",
        request_hash="a" * 64,
        version=1,
        activated_at=created,
    )
    db.add(account)
    db.flush()
    db.add(
        make_record(
            PaperLedgerEntry,
            owner,
            "initial",
            now=created,
            account_id=account.id,
            trade_date=days[1],
            business_key="initial",
            entry_type="INITIAL_CASH",
            cash_delta=account.initial_cash,
            quantity_delta=0,
        )
    )
    for index, day in enumerate(days):
        if db.get(TradeCalendar, day) is None:
            db.add(
                TradeCalendar(
                    cal_date=day,
                    exchange="SSE",
                    is_open=True,
                    pretrade_date=days[index - 1] if index else day - timedelta(days=1),
                )
            )
    db.flush()
    for index, day in enumerate(days[1:], start=1):
        signal = days[index - 1]
        stamp = datetime.combine(signal, time(10), UTC)
        close_stamp = datetime.combine(day, time(10), UTC)
        key = day.isoformat()
        observation = make_record(
            DecisionObservation,
            owner,
            key,
            now=stamp,
            signal_date=signal,
            source_status="READY",
            asof_cutoff=stamp,
            ready_at=stamp,
            strategy_identity_hash="b" * 64,
            request_id=key,
            request_hash="a" * 64,
        )
        db.add(observation)
        db.flush()
        proposal = make_record(
            DecisionProposal,
            owner,
            key,
            now=stamp,
            data={"candidate": {"trade_date": signal, "opportunity_stage": "TREND"}},
            account_id=account.id,
            observation_id=observation.id,
            ts_code="000001.SZ",
            action="PROPOSE_BUY",
            target_weight=Decimal("0.001"),
            stage="TREND",
            score=Decimal("85"),
            revision=1,
            version=1,
            state="APPROVED",
            expires_at=open_cutoff(day),
            request_id=key,
            request_hash="a" * 64,
        )
        db.add(proposal)
        db.flush()
        approval = make_record(
            DecisionApprovalEvent,
            owner,
            key,
            now=stamp,
            account_id=account.id,
            proposal_id=proposal.id,
            actor_user_id=owner,
            decision="APPROVED",
            approved_target_weight=Decimal("0.001"),
            event_at=stamp,
            request_id=key,
            request_hash="a" * 64,
        )
        db.add(approval)
        db.flush()
        order = make_record(
            PaperOrder,
            owner,
            key,
            now=stamp,
            data={"estimated_gross": Decimal("1000")},
            account_id=account.id,
            approval_id=approval.id,
            proposal_id=proposal.id,
            signal_date=signal,
            scheduled_date=day,
            ts_code="000001.SZ",
            side="BUY",
            quantity=100,
            target_weight=Decimal("0.001"),
            status="FILLED",
            version=1,
            source_hash="b" * 64,
        )
        db.add(order)
        heads = {}
        for phase in ("EXECUTION", "CLOSE", "DAY_COMPLETED"):
            heads[phase] = make_record(
                PaperDayRun,
                owner,
                f"{key}:{phase}",
                now=close_stamp,
                account_id=account.id,
                trade_date=day,
                phase=phase,
                status="SUCCESS",
                source_hash="b" * 64,
                input_hash="c" * 64,
                result_hash="d" * 64,
                generation=1,
            )
            db.add(heads[phase])
        db.flush()
        attempt = make_record(
            PaperOrderAttempt,
            owner,
            key,
            now=close_stamp,
            account_id=account.id,
            order_id=order.id,
            trade_date=day,
            attempt_no=1,
            outcome="FILLED",
            market_snapshot_hash="b" * 64,
            execution_policy_version="synthetic-v1",
        )
        db.add(attempt)
        db.flush()
        fill = make_record(
            PaperFill,
            owner,
            key,
            now=close_stamp,
            data={"realized_delta": Decimal("0")},
            account_id=account.id,
            order_id=order.id,
            attempt_id=attempt.id,
            trade_date=day,
            ts_code="000001.SZ",
            side="BUY",
            quantity=100,
            ref_open_price=Decimal("10"),
            simulated_price=Decimal("10"),
            gross_amount=Decimal("1000"),
            cash_fee_total=Decimal("5"),
            total_cost=Decimal("5"),
            cash_delta=Decimal("-1005"),
            fee_json={"schema_version": "synthetic-fees-v1", "commission": "5"},
        )
        db.add(fill)
        db.flush()
        db.add(
            make_record(
                PaperLedgerEntry,
                owner,
                key,
                now=close_stamp,
                account_id=account.id,
                day_run_id=heads["EXECUTION"].id,
                fill_id=fill.id,
                trade_date=day,
                business_key=key,
                entry_type="FILL",
                cash_delta=fill.cash_delta,
                quantity_delta=100,
                instrument="000001.SZ",
            )
        )
        quantity = index * 100
        cash = account.initial_cash - Decimal(index * 1005)
        market_value = Decimal(quantity * 10)
        db.add(
            make_record(
                PaperPositionDaily,
                owner,
                key,
                now=close_stamp,
                data={"context": {"opportunity_stage": "TREND"}},
                account_id=account.id,
                day_run_id=heads["CLOSE"].id,
                trade_date=day,
                ts_code="000001.SZ",
                quantity=quantity,
                available_quantity=quantity - 100,
                avg_cost=Decimal("10.05"),
                close_price=Decimal("10"),
                market_value=market_value,
                unrealized_pnl=Decimal(-index * 5),
                realized_pnl=Decimal("0"),
                adj_factor=Decimal("1"),
                valuation_source="CLOSE",
                source_hash="b" * 64,
            )
        )
        db.add(
            make_record(
                PaperNavDaily,
                owner,
                key,
                now=close_stamp,
                data={
                    "turnover": ratio(Decimal("1000") / (account.initial_cash - (index - 1) * 5))
                },
                account_id=account.id,
                day_run_id=heads["CLOSE"].id,
                trade_date=day,
                cash=cash,
                market_value=market_value,
                total_assets=cash + market_value,
                nav=ratio((cash + market_value) / account.initial_cash),
                benchmark_nav=None,
                benchmark_status="BENCHMARK_UNAVAILABLE",
                trading_cost=Decimal("5"),
                position_count=1,
                source_hash="b" * 64,
            )
        )
        db.add(
            make_record(
                PaperOutcomeReview,
                owner,
                key,
                now=close_stamp,
                data={
                    "counterfactual": False,
                    "included_in_nav": False,
                    "forward_mark_return": "0",
                },
                account_id=account.id,
                proposal_id=proposal.id,
                asof_date=day,
                window_days=1,
                eval_version="m17-outcome-mark-v1",
                source_snapshot_hash="b" * 64,
                status="READY",
            )
        )
    db.commit()
    return owner, account.id


def measured_summary(factory, engine, owner, account, config=None):
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with factory() as db:
            start = perf_counter()
            summary = PaperPerformance(db, config or settings()).summary(owner, account)
            elapsed = perf_counter() - start
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    return summary, statements, elapsed


@pytest.mark.parametrize("days", [1, 30, 250])
def test_frozen_history_summary_has_bounded_sql_and_elapsed(capacity_database, days):
    factory, engine = capacity_database
    with factory() as db:
        owner, account = seed_frozen_ledger(db, days)
        last = db.scalar(
            select(PaperNavDaily)
            .where(PaperNavDaily.account_id == account)
            .order_by(PaperNavDaily.trade_date.desc())
        )
        assert last.cash == db.scalar(
            select(func.sum(PaperLedgerEntry.cash_delta)).where(
                PaperLedgerEntry.account_id == account
            )
        )
        assert last.market_value == Decimal(days * 1000)
        assert last.nav == ratio(last.total_assets / Decimal("1000000"))
        position = db.scalar(
            select(PaperPositionDaily).where(
                PaperPositionDaily.account_id == account,
                PaperPositionDaily.trade_date == last.trade_date,
            )
        )
        assert position.quantity == db.scalar(
            select(func.sum(PaperLedgerEntry.quantity_delta)).where(
                PaperLedgerEntry.account_id == account
            )
        )
        assert position.available_quantity == (days - 1) * 100
        for model in (PaperFill, PaperNavDaily, PaperLedgerEntry, PaperPositionDaily):
            for record in db.scalars(select(model).where(model.account_id == account)):
                verify_record(record)
    result, statements, elapsed = measured_summary(factory, engine, owner, account)
    assert len(statements) <= 14, "summary must not query once per day or once per proposal"
    assert elapsed < 30, "bounded 250-day evidence must finish within the CI measurement budget"
    assert not any("stock_daily" in sql or "stock_opportunity_daily" in sql for sql in statements)
    assert result["continuous"] and len(result["series"]) == days
    assert result["cumulative_return"] == str(-Decimal(days * 5) / Decimal("1000000"))
    assert Decimal(result["cumulative_cost"]) == days * 5
    assert Decimal(result["unrealized_pnl"]) == -days * 5
    assert result["decision_metrics"]["denominator"]["legal_proposals"] == days
    assert result["execution"]["hypothetical_fill_rate"] == "1"
    assert result["observation_metrics"]["included_in_nav"] is False
    assert result["benchmark_status"] == "BENCHMARK_UNAVAILABLE"
    again, _, _ = measured_summary(factory, engine, owner, account)
    assert result == again
    measurement = {
        "kind": "frozen_summary",
        "operation": "paper_performance_frozen_summary",
        "trade_days": days,
        "sql_count": len(statements),
        "elapsed_seconds": elapsed,
        "max_sql_count": 14,
        "max_elapsed_seconds": 30,
        "synthetic": True,
        "daily_replay_measured": False,
    }
    emit_measurement(measurement)


@pytest.mark.parametrize("limit", ["rows", "bytes"])
def test_history_preflight_rejects_before_loading_historical_json(capacity_database, limit):
    factory, engine = capacity_database
    with factory() as db:
        owner, account = seed_frozen_ledger(db, 30 if limit == "rows" else 1)
    config = settings()
    if limit == "rows":
        config = config.model_copy(
            update={
                "paper_config": config.paper_config.model_copy(
                    update={
                        "decision": config.paper_config.decision.model_copy(
                            update={"max_source_rows": 100}
                        ),
                    }
                )
            }
        )
    else:
        config = config.model_copy(
            update={
                "paper_config": config.paper_config.model_copy(update={"max_history_bytes": 1024}),
            }
        )
    statements = []

    def capture(conn, cursor, sql, params, context, executemany):
        statements.append(sql)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with factory() as db, pytest.raises(PaperError, match="PAPER_HISTORY_CAPACITY_EXCEEDED"):
            PaperPerformance(db, config).summary(owner, account)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) == (2 if limit == "rows" else 3)
    if limit == "rows":
        assert "count(" in statements[-1] and "record_json" not in statements[-1]
    else:
        assert "octet_length" in statements[-1]
    for table in ("paper_fill", "paper_order", "decision_proposal", "paper_outcome_review"):
        assert table in statements[-1]
    assert not any(sql.startswith("SELECT paper_nav_daily.id") for sql in statements)


def test_counterfactual_returns_cannot_change_financial_summary(capacity_database):
    factory, engine = capacity_database
    with factory() as db:
        owner, account = seed_frozen_ledger(db, 1)
    before, _, _ = measured_summary(factory, engine, owner, account)
    with factory() as db:
        proposal = db.scalar(select(DecisionProposal).where(DecisionProposal.account_id == account))
        watch = make_record(
            DecisionProposal,
            owner,
            "counterfactual-watch",
            now=proposal.created_at,
            data=verify_record(proposal),
            account_id=account,
            observation_id=proposal.observation_id,
            ts_code=proposal.ts_code,
            action="WATCH",
            target_weight=Decimal("0"),
            stage=proposal.stage,
            score=proposal.score,
            state="PENDING_REVIEW",
            version=1,
            revision=1,
            expires_at=proposal.expires_at,
            request_id="watch",
            request_hash="a" * 64,
        )
        db.add(watch)
        db.flush()
        db.add(
            make_record(
                PaperOutcomeReview,
                owner,
                "synthetic-counterfactual",
                now=proposal.created_at + timedelta(days=1),
                data={
                    "counterfactual": True,
                    "included_in_nav": False,
                    "forward_mark_return": "99",
                },
                account_id=account,
                proposal_id=watch.id,
                asof_date=trading_dates(2)[1],
                window_days=1,
                eval_version="m17-outcome-mark-v1",
                source_snapshot_hash="a" * 64,
                status="READY",
            )
        )
        db.commit()
    after, _, _ = measured_summary(factory, engine, owner, account)
    for field in (
        "financial_source_hash",
        "series",
        "cumulative_return",
        "maximum_drawdown",
        "cumulative_cost",
        "realized_pnl",
        "unrealized_pnl",
    ):
        assert before[field] == after[field]
    assert after["observation_metrics"]["windows"]["1"]["hit_rate"] == "1"


def forward_weekdays(count):
    days, day = [DAY], DAY
    while len(days) <= count:
        day += timedelta(days=1)
        if day.weekday() < 5:
            days.append(day)
    return tuple(days)


@pytest.fixture
def daily_capacity_database(monkeypatch):
    # Each case owns its full Raw/Derived fixture; do not share source rows across cases.
    with isolated_contract_database(monkeypatch) as database:
        _, engine = database

        def bound(connection):
            connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")

        event.listen(engine, "begin", bound)
        try:
            yield database
        finally:
            event.remove(engine, "begin", bound)


def prepare_daily_account(factory, days, config):
    with factory() as db:
        owner, _, account_id = seed(db, days=days)
        PaperAccountApplication(db, config, clock=lambda: NOW).transition(
            owner, account_id, PaperRequest(request_id="capacity-activate"), "ACTIVE"
        )
        account = db.get(PaperAccount, account_id)
        assert account.first_trade_date == days[1] and account.state == "ACTIVE"
        initial_cash = account.initial_cash
        decisions = DecisionApplication(db, config, clock=lambda: NOW)
        observation = decisions.observe(
            owner,
            CreateObservation(
                request_id="capacity-observe", signal_date=DAY, account_id=account_id
            ),
        )
        proposal = decisions.propose(
            owner,
            CreateProposal(
                request_id="capacity-buy",
                account_id=account_id,
                observation_id=observation.id,
                ts_code=CODES[0],
                action="PROPOSE_BUY",
                target_weight="0.08",
            ),
        )
        ApprovalApplication(db, config, clock=lambda: NOW).approve(
            owner,
            proposal.id,
            ApproveProposal(
                request_id="capacity-manual-approve", target_weight="0.08", confirmed=True
            ),
        )
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 1
    return owner, account_id, initial_cash


def measured_daily_job(factory, engine, owner, account_id, day, config):
    stamp = datetime.combine(day, time(10), UTC)
    statements = []

    def capture(conn, cursor, sql, params, context, executemany):
        statements.append(sql)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        start = perf_counter()
        with factory() as db:
            job = PaperQueue(db, config, clock=lambda: stamp).advance(
                owner,
                account_id,
                AdvancePaperAccount(request_id=f"capacity-advance:{day}", trade_date=day),
            )
            job_id = job.id
            assert job.job_type == PAPER_DAILY and job.status == "QUEUED"
        with factory() as db:
            # Test claim substitutes only worker leasing, preserving dispatch receipt and identity.
            job = db.scalar(
                select(JobRun)
                .where(JobRun.id == job_id, JobRun.status == "QUEUED")
                .with_for_update(skip_locked=True)
            )
            assert job is not None and not job.cancel_requested
            job.status, job.worker_id, job.heartbeat_at = "RUNNING", "capacity-worker", stamp
            job.step = "paper claimed"
            db.commit()
        with factory() as db:
            completed = PaperJobApplication(db, config, clock=lambda: stamp).run_job(job_id)
            assert completed.status == "SUCCESS" and completed.trade_date == day
        elapsed = perf_counter() - start
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    # Capture includes the independent source and progress sessions on this same engine.
    assert sum("SET TRANSACTION READ ONLY" in sql for sql in statements) >= 2
    assert any("stock_daily" in sql for sql in statements)
    return job_id, {
        "trade_date": day.isoformat(),
        "sql_count": len(statements),
        "elapsed_seconds": elapsed,
    }


@pytest.mark.parametrize("trade_days", [1, 30, 250])
@pytest.mark.parametrize("with_dirty_history", [False, True])
def test_real_daily_queue_claim_source_and_settlement_are_bounded(
    daily_capacity_database, trade_days, with_dirty_history
):
    factory, engine = daily_capacity_database
    days, config = forward_weekdays(trade_days), settings()
    owner, account_id, initial_cash = prepare_daily_account(factory, days, config)
    if with_dirty_history:
        with factory() as db:
            day = days[0]
            while day <= days[-1]:
                if db.get(TradeCalendar, day) is None:
                    db.add(TradeCalendar(cal_date=day, exchange="SSE", is_open=False))
                day += timedelta(days=1)
            db.add(DataDirtyRange(
                dataset="stock_daily", dirty_start_date=DAY, dirty_end_date=DAY,
                status="RESOLVED", created_at=NOW - timedelta(days=1),
            ))
            db.commit()
    measurements, job_ids = [], []
    frozen_fill_hash, buy_quantity, cash_delta, buy_cost = None, None, None, None
    for index, day in enumerate(days[1:]):
        if with_dirty_history and index == trade_days - 1:
            clock = datetime.combine(day, time(10), UTC)
            with factory() as db:
                unused = JobRun(job_type="provider_smoke", status="SUCCESS",
                                started_at=clock - timedelta(days=181, minutes=1),
                                finished_at=clock - timedelta(days=181))
                db.add(unused)
                db.commit()
                unused_id, before = unused.id, frozen_records(db)
                result = run_retention(db, now=clock, policy=RetentionPolicy(
                    job_deletion_enabled=True,
                ))
                assert not result["blocked"] and result["successful_jobs"] == 1, result
                assert db.get(JobRun, unused_id) is None and frozen_records(db) == before
                if trade_days == 250:
                    assert result["protected_referenced_jobs"] > 0
                emit_measurement({"kind": "retention_during_daily_advance",
                                  "trade_days": trade_days, "retention": result})
        job_id, measurement = measured_daily_job(factory, engine, owner, account_id, day, config)
        measurements.append(measurement)
        job_ids.append(job_id)
        assert measurement["sql_count"] <= DAILY_SQL_BUDGET, measurement
        assert measurement["elapsed_seconds"] < DAILY_SECONDS_BUDGET, measurement
        # Assertions use a new transaction after commit and are outside the operation measurement.
        with factory() as db:
            job = db.get(JobRun, job_id)
            heads = list(
                db.scalars(
                    select(PaperDayRun).where(
                        PaperDayRun.account_id == account_id, PaperDayRun.trade_date == day
                    )
                )
            )
            assert job.status == "SUCCESS" and job.worker_id == "capacity-worker"
            assert job.finished_at == datetime.combine(day, time(10), UTC)
            assert job.error_message is None and job.job_metadata["progress_pct"] == 100
            assert {head.phase for head in heads} == {"EXECUTION", "CLOSE", "DAY_COMPLETED"}
            assert len(heads) == 3 and {head.status for head in heads} == {"SUCCESS"}
            assert {head.job_id for head in heads} == {job_id}
            assert {head.result_hash for head in heads} == {job.job_metadata["result_hash"]}
            for head in heads:
                verify_record(head)
            fills = list(db.scalars(select(PaperFill).where(PaperFill.account_id == account_id)))
            assert len(fills) == 1
            fill = fills[0]
            verify_record(fill)
            if index == 0:
                assert fill.side == "BUY" and fill.trade_date == days[1]
                frozen_fill_hash, buy_quantity = fill.record_hash, fill.quantity
                cash_delta, buy_cost = fill.cash_delta, fill.total_cost
                commission = Decimal(fill.fee_json["commission"])
                assert commission > 0 and fill.cash_fee_total == sum(
                    (
                        Decimal(fill.fee_json[key])
                        for key in ("commission", "stamp_tax", "transfer_fee")
                    ),
                    Decimal("0"),
                )
            assert fill.record_hash == frozen_fill_hash
            nav = db.scalar(
                select(PaperNavDaily).where(
                    PaperNavDaily.account_id == account_id, PaperNavDaily.trade_date == day
                )
            )
            position = db.scalar(
                select(PaperPositionDaily).where(
                    PaperPositionDaily.account_id == account_id,
                    PaperPositionDaily.trade_date == day,
                )
            )
            verify_record(nav)
            verify_record(position)
            assert nav.cash == initial_cash + cash_delta
            assert nav.market_value == position.market_value == buy_quantity * Decimal("10")
            assert nav.total_assets == nav.cash + nav.market_value
            assert nav.nav == ratio(nav.total_assets / initial_cash)
            assert nav.trading_cost == (buy_cost if index == 0 else Decimal("0"))
            assert position.quantity == buy_quantity
            assert position.available_quantity == (0 if index == 0 else buy_quantity)
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PaperLedgerEntry)
                    .where(PaperLedgerEntry.account_id == account_id)
                )
                == 2
            )
            assert nav.cash == db.scalar(
                select(func.sum(PaperLedgerEntry.cash_delta)).where(
                    PaperLedgerEntry.account_id == account_id
                )
            )
    with factory() as db:
        navs = list(
            db.scalars(
                select(PaperNavDaily)
                .where(PaperNavDaily.account_id == account_id)
                .order_by(PaperNavDaily.trade_date)
            )
        )
        completed = list(
            db.scalars(
                select(PaperDayRun)
                .where(PaperDayRun.account_id == account_id, PaperDayRun.phase == "DAY_COMPLETED")
                .order_by(PaperDayRun.trade_date)
            )
        )
        assert (
            [nav.trade_date for nav in navs]
            == [head.trade_date for head in completed]
            == list(days[1:])
        )
        assert len(navs) == trade_days and {head.status for head in completed} == {"SUCCESS"}
        assert sum((nav.trading_cost for nav in navs), Decimal("0")) == buy_cost
        assert set(db.scalars(select(JobRun.status).where(JobRun.id.in_(job_ids)))) == {"SUCCESS"}
        assert (
            db.scalar(
                select(func.count())
                .select_from(PaperOrderAttempt)
                .where(PaperOrderAttempt.account_id == account_id)
            )
            == 1
        )
    total_sql = sum(m["sql_count"] for m in measurements)
    elapsed = sum(m["elapsed_seconds"] for m in measurements)
    assert total_sql <= trade_days * DAILY_SQL_BUDGET
    assert elapsed < trade_days * DAILY_SECONDS_BUDGET
    emit_measurement(
        {
            "kind": "daily_advance_dirty_history" if with_dirty_history else "daily_advance",
            "historical_dirty_status": "RESOLVED" if with_dirty_history else None,
            "operation": "paper_queue_claim_source_atomic_settlement",
            "trade_days": trade_days,
            "sql_count": total_sql,
            "total_sql_count": total_sql,
            "max_daily_sql_count": max(m["sql_count"] for m in measurements),
            "elapsed_seconds": elapsed,
            "max_daily_elapsed_seconds": max(m["elapsed_seconds"] for m in measurements),
            "daily_sql_budget": DAILY_SQL_BUDGET,
            "daily_elapsed_budget_seconds": DAILY_SECONDS_BUDGET,
            "synthetic": True,
            "daily_replay_measured": True,
            "manual_buy_orders": 1,
            "measurement_scope": (
                "QUEUE_CLAIM_SOURCE_FINANCIAL_JOB_COMMIT_EXCLUDING_SETUP_AND_ASSERTIONS"
            ),
            "days": measurements,
        }
    )
