from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from app.domain.decision.account_requests import CreatePaperAccount
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import (
    ApproveProposal,
    CreateObservation,
    CreateProposal,
    PaperRequest,
)
from app.models.market_data import IndexDaily, StockAdjFactor, StockDaily
from app.models.paper import (
    PaperAccountEvent,
    PaperDayRun,
    PaperFill,
    PaperLedgerEntry,
    PaperNavDaily,
    PaperOrder,
    PaperOrderAttempt,
    PaperPositionDaily,
)
from app.services.decision.application import DecisionApplication
from app.services.decision.approval import ApprovalApplication
from app.services.paper.accounts import PaperAccountApplication
from app.services.paper.daily import PaperDailyApplication
from app.services.paper.records import verify_record
from sqlalchemy import func, select

from tests.integration.m16_6_support import isolated_contract_database
from tests.integration.m17_support import CODES, DAY, NOW, seed, settings

FIRST = DAY + timedelta(days=1)
SECOND = DAY + timedelta(days=2)


@pytest.fixture
def paper(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, _):
        with factory() as db:
            owner, other, account_id = seed(db, days=(DAY, FIRST, SECOND))
            PaperAccountApplication(db, settings(), clock=lambda: NOW).transition(
                owner, account_id, PaperRequest(request_id="activate"), "ACTIVE"
            )
        yield factory, owner, other, account_id


def approve(
    factory, owner, account, *, day=DAY, action="PROPOSE_BUY", weight="0.08", code=CODES[0]
):
    stamp = NOW + timedelta(days=(day - DAY).days)
    with factory() as db:
        application = DecisionApplication(db, settings(), clock=lambda: stamp)
        observation = application.observe(
            owner,
            CreateObservation(
                request_id=f"observe:{day}:{code}", signal_date=day, account_id=account
            ),
        )
        proposal = application.propose(
            owner,
            CreateProposal(
                request_id=f"proposal:{day}:{code}",
                observation_id=observation.id,
                account_id=account,
                ts_code=code,
                action=action,
                target_weight=weight,
            ),
        )
        ApprovalApplication(db, settings(), clock=lambda: stamp).approve(
            owner,
            proposal.id,
            ApproveProposal(
                request_id=f"approve:{day}:{code}", target_weight=weight, confirmed=True
            ),
        )


def run(factory, owner, account, day=FIRST, *, fault=None, clock=None):
    with factory() as db:
        return PaperDailyApplication(
            db,
            settings(),
            clock=clock or (lambda: NOW + timedelta(days=(day - DAY).days)),
            fault_hook=fault,
        ).run(owner, account, day)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_day_cash_quantity_nav_and_idempotent_retry(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    first = run(factory, owner, account)
    again = run(factory, owner, account)
    assert first.id == again.id and first.result_hash == again.result_hash
    with factory() as db:
        fill = db.scalar(select(PaperFill))
        nav = db.scalar(select(PaperNavDaily))
        position = db.scalar(select(PaperPositionDaily))
        assert count(db, PaperOrderAttempt) == count(db, PaperFill) == 1
        assert count(db, PaperLedgerEntry) == 2
        assert count(db, PaperDayRun) == 3
        assert position.quantity == fill.quantity and position.available_quantity == 0
        assert nav.cash == Decimal("1000000") + fill.cash_delta
        assert nav.market_value == position.quantity * position.close_price
        assert nav.total_assets == nav.cash + nav.market_value
        assert nav.trading_cost == fill.total_cost
        assert verify_record(fill)["market_data_mode"] == "POST_EOD_SIMULATED_OPEN"
    run(factory, owner, account, SECOND)
    with factory() as db:
        position = db.scalar(
            select(PaperPositionDaily).where(PaperPositionDaily.trade_date == SECOND)
        )
        assert position.available_quantity == position.quantity
        assert count(db, PaperFill) == 1


@pytest.mark.parametrize("phase", ["before_orders", "after_fill", "before_nav", "before_commit"])
def test_crash_rolls_back_every_financial_row_and_can_retry(paper, phase):
    factory, owner, _, account = paper
    approve(factory, owner, account)

    def fail(at):
        if at == phase:
            raise RuntimeError("synthetic crash")

    with pytest.raises(RuntimeError):
        run(factory, owner, account, fault=fail)
    with factory() as db:
        for model in (PaperFill, PaperOrderAttempt, PaperDayRun, PaperNavDaily, PaperPositionDaily):
            assert count(db, model) == 0
        assert count(db, PaperLedgerEntry) == 1
        assert db.scalar(select(PaperOrder.status)) == "ORDER_PENDING"
    run(factory, owner, account)
    with factory() as db:
        assert count(db, PaperFill) == 1


def test_lost_response_after_commit_returns_original_bundle(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)

    def fail(at):
        if at == "after_commit":
            raise RuntimeError("response lost")

    with pytest.raises(RuntimeError):
        run(factory, owner, account, fault=fail)
    run(factory, owner, account)
    with factory() as db:
        assert count(db, PaperFill) == 1 and count(db, PaperLedgerEntry) == 2


def test_concurrent_workers_commit_once(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    barrier = Barrier(2)

    def worker():
        barrier.wait(timeout=10)
        return run(factory, owner, account).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        assert futures[0].result(timeout=30) == futures[1].result(timeout=30)
    with factory() as db:
        assert count(db, PaperFill) == 1


def test_source_correction_marks_review_without_rewriting_ledger(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    run(factory, owner, account)
    with factory() as db:
        hashes = [row.record_hash for row in db.scalars(select(PaperLedgerEntry))]
        raw = db.get(StockDaily, (FIRST, CODES[0]))
        raw.close = 10.2
        db.commit()
    with pytest.raises(PaperError):
        run(factory, owner, account)
    with factory() as db:
        assert [row.record_hash for row in db.scalars(select(PaperLedgerEntry))] == hashes
        assert set(db.scalars(select(PaperDayRun.status))) == {"REVIEW_REQUIRED"}
        assert count(db, PaperFill) == 1


def test_company_action_stops_before_first_fill(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    with factory() as db:
        db.get(StockAdjFactor, (FIRST, CODES[0])).adj_factor = 2
        db.commit()
    with pytest.raises(PaperError, match="CORPORATE_ACTION_UNSUPPORTED"):
        run(factory, owner, account)
    with factory() as db:
        assert count(db, PaperFill) == 0 and count(db, PaperLedgerEntry) == 1


def test_missing_day_and_before_eod_and_cross_owner_fail_closed(paper):
    factory, owner, other, account = paper
    with pytest.raises(PaperError, match="PAPER_DAY_GAP"):
        run(factory, owner, account, SECOND)
    with pytest.raises(PaperError, match="SOURCE_EOD_NOT_READY"):
        run(factory, owner, account, clock=lambda: NOW)
    with pytest.raises(PaperError) as error:
        run(factory, other, account)
    assert error.value.status_code == 404


def test_pause_resume_is_sequential_and_close_keeps_history(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    with factory() as db:
        application = PaperAccountApplication(db, settings(), clock=lambda: NOW)
        application.transition(owner, account, PaperRequest(request_id="pause"), "PAUSED")
    with pytest.raises(PaperError, match="NOT_ACTIVE"):
        run(factory, owner, account)
    with factory() as db:
        application = PaperAccountApplication(db, settings(), clock=lambda: NOW)
        application.transition(owner, account, PaperRequest(request_id="resume"), "ACTIVE")
    run(factory, owner, account)
    with factory() as db:
        PaperAccountApplication(db, settings(), clock=lambda: NOW).transition(
            owner, account, PaperRequest(request_id="close"), "CLOSED"
        )
    assert run(factory, owner, account).status == "SUCCESS"
    with factory() as db:
        assert count(db, PaperNavDaily) == 1


def test_benchmark_missing_is_null_not_zero(paper):
    factory, owner, _, account = paper
    # A non-core benchmark can be unavailable while required market data stays READY.
    with factory() as db:
        row = db.get(IndexDaily, (FIRST, "000300.SH"))
        db.delete(row)
        db.commit()
    with pytest.raises(PaperError):
        run(factory, owner, account)
    # Restore required core index, but remove benchmark price on next test account creation.
    with factory() as db:
        db.add(IndexDaily(trade_date=FIRST, ts_code="000300.SH", close=100, pre_close=100))
        db.commit()
        application = PaperAccountApplication(db, settings(), clock=lambda: NOW)
        created = application.create(
            owner,
            CreatePaperAccount(
                request_id="other-account",
                name="no benchmark",
                initial_cash="10000",
                benchmark_code="999999.SH",
            ),
        )
        application.transition(
            owner, created.id, PaperRequest(request_id="other-activate"), "ACTIVE"
        )
    run(factory, owner, created.id)
    with factory() as db:
        nav = db.scalar(select(PaperNavDaily).where(PaperNavDaily.account_id == created.id))
        assert nav.benchmark_nav is None and nav.benchmark_status == "BENCHMARK_UNAVAILABLE"


def test_creation_initial_funding_idempotency_and_state_version(paper):
    factory, owner, other, _ = paper
    with factory() as db:
        application = PaperAccountApplication(db, settings(), clock=lambda: NOW)
        body = CreatePaperAccount(request_id="new", name="forward", initial_cash="100000")
        account = application.create(owner, body)
        assert account.state == "PAUSED" and account.first_trade_date == FIRST
        assert application.create(owner, body).id == account.id
        assert (
            db.scalar(
                select(func.count())
                .select_from(PaperLedgerEntry)
                .where(PaperLedgerEntry.account_id == account.id)
            )
            == 1
        )
        with pytest.raises(PaperError, match="IDEMPOTENCY_CONFLICT"):
            application.create(owner, body.model_copy(update={"initial_cash": Decimal("200000")}))
        with pytest.raises(PaperError, match="INCEPTION_DATE_INVALID"):
            application.create(
                owner,
                CreatePaperAccount(
                    request_id="past", name="past", initial_cash="1000", first_trade_date=DAY
                ),
            )
        event = application.transition(
            owner, account.id, PaperRequest(request_id="new-active"), "ACTIVE"
        )
        assert (
            application.transition(
                owner, account.id, PaperRequest(request_id="new-active"), "ACTIVE"
            ).id
            == event.id
        )
        with pytest.raises(PaperError) as error:
            application.transition(other, account.id, PaperRequest(request_id="foreign"), "PAUSED")
        assert error.value.status_code == 404
        assert count(db, PaperAccountEvent) >= 2


def test_exit_next_open_charges_sell_taxes_and_preserves_realized_history(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    run(factory, owner, account)
    approve(factory, owner, account, day=FIRST, action="PROPOSE_EXIT", weight="0")
    run(factory, owner, account, SECOND)
    with factory() as db:
        fills = list(db.scalars(select(PaperFill).order_by(PaperFill.trade_date)))
        assert [fill.side for fill in fills] == ["BUY", "SELL"]
        assert Decimal(fills[1].fee_json["stamp_tax"]) > 0
        assert count(db, PaperPositionDaily) == 1  # The old day stays immutable.
        closing = db.scalar(select(PaperNavDaily).where(PaperNavDaily.trade_date == SECOND))
        assert closing.position_count == 0 and closing.market_value == 0
        assert closing.cash == Decimal("1000000") + sum(fill.cash_delta for fill in fills)
        assert verify_record(fills[1])["realized_delta"] is not None


def test_limit_block_is_final_and_does_not_change_capital(paper):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    with factory() as db:
        db.get(StockDaily, (FIRST, CODES[0])).open = 11
        db.commit()
    run(factory, owner, account)
    run(factory, owner, account)
    with factory() as db:
        order = db.scalar(select(PaperOrder))
        assert order.status == "SKIPPED" and order.reason_code == "LIMIT_UP_BUY_BLOCKED"
        assert count(db, PaperOrderAttempt) == 1 and count(db, PaperFill) == 0
        nav = db.scalar(select(PaperNavDaily))
        assert nav.nav == 1 and nav.cash == Decimal("1000000")


def test_new_account_observation_waits_for_its_own_close(paper):
    factory, owner, _, account = paper
    with factory() as db:
        application = DecisionApplication(db, settings(), clock=lambda: NOW + timedelta(days=1))
        with pytest.raises(PaperError, match="SNAPSHOT_NOT_READY"):
            application.observe(
                owner,
                CreateObservation(request_id="too-early", signal_date=FIRST, account_id=account),
            )
    run(factory, owner, account)
    with factory() as db:
        observation = DecisionApplication(
            db, settings(), clock=lambda: NOW + timedelta(days=1)
        ).observe(
            owner,
            CreateObservation(request_id="after-close", signal_date=FIRST, account_id=account),
        )
        assert observation.signal_date == FIRST
