import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from app.domain.decision.account_requests import AdvancePaperAccount, ReviewPaperAccount
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import (
    ApproveProposal,
    CreateObservation,
    CreateProposal,
    PaperRequest,
)
from app.models.job import JobRun
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    StockDaily,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockTradeStatusDaily,
)
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
from app.models.portfolio import PortfolioBacktestRun, PortfolioNavDaily
from app.services.decision.application import DecisionApplication
from app.services.decision.approval import ApprovalApplication
from app.services.paper.account_state import account_settings
from app.services.paper.accounts import PaperAccountApplication
from app.services.paper.job_application import PaperJobApplication
from app.services.paper.queue import PaperQueue
from app.services.paper.reviews import PaperReviews
from app.services.paper.scheduling import run_scheduled_paper
from sqlalchemy import func, select

from tests.integration.m17_1_support import AFTER_HOLIDAY, FIRST, SECOND, add_dirty
from tests.integration.m17_1_support import dirty_paper as dirty_paper
from tests.integration.m17_support import CODES, DAY, NOW, settings
from tests.integration.test_m13_3_2_consistency import _nav, _run
from tests.integration.test_m17_paper_daily import approve, run

FROZEN = (PaperAccount, PaperAccountEvent, DecisionObservation, DecisionProposal,
          DecisionApprovalEvent, PaperDayRun, PaperOrder, PaperOrderAttempt,
          PaperFill, PaperLedgerEntry, PaperPositionDaily, PaperNavDaily, PaperOutcomeReview)
FINANCE = (PaperFill, PaperLedgerEntry, PaperPositionDaily, PaperNavDaily)
AT = NOW + timedelta(days=1)


def frozen_records(db):
    return {(model.__tablename__, str(row.id)): (row.record_hash, json.dumps(
        row.record_json, sort_keys=True, separators=(",", ":"),
    )) for model in FROZEN for row in db.scalars(select(model))}


def assert_preserved(db, previous):
    current = frozen_records(db)
    assert previous.items() <= current.items()


def financial_counts(db):
    return tuple(db.scalar(select(func.count()).select_from(model)) for model in FINANCE)


def typed_facts(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def draft(db, owner, account):
    app = DecisionApplication(db, settings(), clock=lambda: NOW)
    observed = app.observe(owner, CreateObservation(
        request_id="observation", signal_date=DAY, account_id=account,
    ))
    body = CreateProposal(request_id="proposal", account_id=account,
                          observation_id=observed.id, ts_code=CODES[0],
                          action="PROPOSE_BUY", target_weight="0.08")
    return app, observed, body


def corrected_and_recomputed_source(db, day):
    stamp = NOW + timedelta(days=(day - DAY).days)
    raw = db.get(StockDaily, (day, CODES[0]))
    raw.close, raw.source_updated_at = 10.5, stamp - timedelta(seconds=100)
    job = JobRun(job_type="recalculate", status="SUCCESS", target_trade_date=day,
                 started_at=stamp - timedelta(seconds=90),
                 finished_at=stamp - timedelta(seconds=10), job_metadata={})
    db.add(job)
    db.flush()
    for model in (StockFactorDaily, StockStateDaily, StockTradeStatusDaily,
                  StockOpportunityDaily, MarketDaily, SectorFactorDaily):
        for row in db.scalars(select(model).where(model.trade_date == day)):
            row.calc_run_id, row.calculated_at = job.id, stamp - timedelta(seconds=30)
    db.commit()


@pytest.mark.parametrize("entry", ["observe", "propose", "approve"])
@pytest.mark.parametrize("problem", ["intersecting", "historical_stale", "source_drift"])
def test_decision_chain_rejects_without_order_or_financial_write(dirty_paper, entry, problem):
    factory, _, owner, _, account = dirty_paper
    with factory() as db:
        app, observed, body = draft(db, owner, account)
        proposal = app.propose(owner, body) if entry == "approve" else None
        frozen, before = frozen_records(db), financial_counts(db)
        if problem == "intersecting":
            add_dirty(db, start=DAY, end=DAY, status="OPEN")
            code = "SOURCE_DIRTY_RANGE"
        elif problem == "historical_stale":
            add_dirty(db, created_at=NOW - timedelta(days=10))
            code = "SOURCE_DERIVED_STALE"
        else:
            corrected_and_recomputed_source(db, DAY)
            code = "DECISION_SOURCE_DRIFT"
        if entry == "observe" and problem == "source_drift":
            # A fresh observation may freeze a new valid source; drift is against an old snapshot.
            with pytest.raises(PaperError, match=code):
                app.propose(owner, body)
        else:
            with pytest.raises(PaperError, match=code):
                if entry == "observe":
                    app.observe(owner, CreateObservation(request_id="blocked", signal_date=DAY))
                elif entry == "propose":
                    app.propose(owner, body)
                else:
                    ApprovalApplication(db, settings(), clock=lambda: NOW).approve(
                        owner, proposal.id, ApproveProposal(request_id="approve",
                                                           target_weight="0.08", confirmed=True),
                    )
        assert financial_counts(db) == before
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 0
        assert_preserved(db, frozen)


def test_unrelated_historical_failed_range_allows_manual_chain_replay_and_eod(dirty_paper):
    factory, _, owner, _, account = dirty_paper
    with factory() as db:
        add_dirty(db)
        legacy = _run(DAY)
        db.add(legacy)
        db.flush()
        legacy_nav = _nav(legacy.id, DAY)
        db.add(legacy_nav)
        db.commit()
        legacy_id, legacy_nav_id = legacy.id, (legacy.id, DAY)
        legacy_facts, legacy_nav_facts = typed_facts(legacy), typed_facts(legacy_nav)
        app, observed, body = draft(db, owner, account)
        proposal = app.propose(owner, body)
        assert app.propose(owner, body).id == proposal.id
        approve_body = ApproveProposal(request_id="approve", target_weight="0.08", confirmed=True)
        approval = ApprovalApplication(db, settings(), clock=lambda: NOW)
        event = approval.approve(owner, proposal.id, approve_body)
        assert approval.approve(owner, proposal.id, approve_body).id == event.id
        frozen = frozen_records(db)
    completed = run(factory, owner, account)
    assert run(factory, owner, account).id == completed.id
    with factory() as db:
        assert financial_counts(db) == (1, 2, 1, 1)
        nav = db.scalar(select(PaperNavDaily))
        fill = db.scalar(select(PaperFill))
        position = db.scalar(select(PaperPositionDaily))
        assert nav.cash == db.scalar(select(func.sum(PaperLedgerEntry.cash_delta)))
        assert nav.total_assets == nav.cash + position.market_value
        assert position.quantity == fill.quantity and position.available_quantity == 0
        assert nav.trading_cost == fill.total_cost
        assert typed_facts(db.get(PortfolioBacktestRun, legacy_id)) == legacy_facts
        assert typed_facts(db.get(PortfolioNavDaily, legacy_nav_id)) == legacy_nav_facts
        assert db.scalar(select(func.count()).select_from(PortfolioBacktestRun)) == 1
        assert_preserved(db, frozen)


@pytest.mark.parametrize("problem", ["intersecting", "historical_stale"])
def test_dirty_eod_rejects_without_fill_ledger_nav_and_preserves_approved_order(
    dirty_paper, problem
):
    factory, _, owner, _, account = dirty_paper
    approve(factory, owner, account)
    with factory() as db:
        frozen, before = frozen_records(db), financial_counts(db)
        if problem == "intersecting":
            add_dirty(db, start=FIRST, end=FIRST, status="PROCESSING")
            code = "SOURCE_DIRTY_RANGE"
        else:
            add_dirty(db, created_at=NOW - timedelta(days=10))
            code = "SOURCE_DERIVED_STALE"
    with pytest.raises(PaperError, match=code):
        run(factory, owner, account)
    with factory() as db:
        assert financial_counts(db) == before
        assert db.scalar(select(PaperOrder.status)) == "ORDER_PENDING"
        assert_preserved(db, frozen)


def test_correction_after_success_marks_review_and_never_reprices(dirty_paper):
    factory, _, owner, _, account = dirty_paper
    approve(factory, owner, account)
    run(factory, owner, account)
    with factory() as db:
        before, frozen = financial_counts(db), frozen_records(db)
        corrected_and_recomputed_source(db, FIRST)
    with pytest.raises(PaperError, match="PAPER_SOURCE_DRIFT"):
        run(factory, owner, account, SECOND)
    with factory() as db:
        assert financial_counts(db) == before
        assert db.scalar(select(PaperDayRun.status).where(
            PaperDayRun.trade_date == FIRST, PaperDayRun.phase == "DAY_COMPLETED",
        )) == "REVIEW_REQUIRED"
        assert_preserved(db, frozen)


def test_pause_gap_recovery_and_weekend_holiday_are_real_calendar_sequential(dirty_paper):
    factory, _, owner, _, account = dirty_paper
    approve(factory, owner, account)
    with factory() as db:
        add_dirty(db)
    run(factory, owner, account)
    with factory() as db:
        before, frozen = financial_counts(db), frozen_records(db)
        lifecycle = PaperAccountApplication(db, settings(), clock=lambda: AT)
        lifecycle.transition(owner, account, PaperRequest(request_id="pause"), "PAUSED")
    with pytest.raises(PaperError, match="PAPER_ACCOUNT_NOT_ACTIVE"):
        run(factory, owner, account, SECOND)
    with factory() as db:
        assert financial_counts(db) == before
        PaperAccountApplication(db, settings(), clock=lambda: AT).transition(
            owner, account, PaperRequest(request_id="resume"), "ACTIVE",
        )
    with pytest.raises(PaperError, match="PAPER_DAY_GAP"):
        run(factory, owner, account, AFTER_HOLIDAY)
    with factory() as db:
        assert financial_counts(db) == before
    run(factory, owner, account, SECOND)
    final = run(factory, owner, account, AFTER_HOLIDAY)
    assert run(factory, owner, account, AFTER_HOLIDAY).id == final.id
    with factory() as db:
        navs = list(db.scalars(select(PaperNavDaily).order_by(PaperNavDaily.trade_date)))
        assert [nav.trade_date for nav in navs] == [FIRST, SECOND, AFTER_HOLIDAY]
        assert sum((nav.trading_cost for nav in navs), Decimal("0")) == navs[0].trading_cost
        assert financial_counts(db) == (1, 2, 3, 3)
        assert db.scalar(select(PaperPositionDaily.available_quantity).where(
            PaperPositionDaily.trade_date == AFTER_HOLIDAY,
        )) == db.scalar(select(PaperFill.quantity))
        assert_preserved(db, frozen)


def queue_and_claim(factory, owner, account, request="advance"):
    with factory() as db:
        job = PaperQueue(db, settings(), clock=lambda: AT).advance(
            owner, account, AdvancePaperAccount(request_id=request, trade_date=FIRST),
        )
        job_id = job.id
        assert job.status == "QUEUED"
        job.status, job.worker_id, job.heartbeat_at = "RUNNING", "m17.1-worker", AT
        db.commit()
        return job_id


def execute(factory, job, fault=None):
    with factory() as db:
        return PaperJobApplication(db, settings(), clock=lambda: AT, fault_hook=fault).run_job(job)


@pytest.mark.parametrize("failure", ["before_nav", "cancel", "lost_response", "parallel"])
def test_worker_recovery_with_historical_dirty_has_one_atomic_financial_commit(
    dirty_paper, failure
):
    factory, _, owner, _, account = dirty_paper
    approve(factory, owner, account)
    with factory() as db:
        add_dirty(db)
        before, frozen = financial_counts(db), frozen_records(db)
    job = queue_and_claim(factory, owner, account)
    if failure == "parallel":
        def work():
            try:
                execute(factory, job)
                return "SUCCESS"
            except PaperError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: work(), range(2)))
        assert "SUCCESS" in outcomes and set(outcomes) <= {"SUCCESS", "PAPER_JOB_LEASE_LOST"}
    else:
        def fault(point):
            if failure == "cancel" and point == "before_nav":
                with factory() as db:
                    PaperQueue(db, settings(), clock=lambda: AT).cancel(
                        owner, account, job, PaperRequest(request_id="cancel"),
                    )
            if (failure == "before_nav" and point == "before_nav") or (
                failure == "lost_response" and point == "after_commit"
            ):
                raise RuntimeError("synthetic interrupted reply")

        with pytest.raises((RuntimeError, PaperError)):
            execute(factory, job, fault)
        with factory() as db:
            expected = "SUCCESS" if failure == "lost_response" else (
                "CANCELLED" if failure == "cancel" else "FAILED"
            )
            assert db.get(JobRun, job).status == expected
            if failure != "lost_response":
                assert financial_counts(db) == before
        if failure != "lost_response":
            job = queue_and_claim(factory, owner, account, request="explicit-retry")
        execute(factory, job)
    with factory() as db:
        assert db.get(JobRun, job).status == "SUCCESS"
        assert financial_counts(db) == (1, 2, 1, 1)
        assert db.scalar(select(PaperNavDaily.cash)) == db.scalar(
            select(func.sum(PaperLedgerEntry.cash_delta)),
        )
        assert_preserved(db, frozen)


def automatic():
    config = settings()
    return config.model_copy(update={
        "paper_config": config.paper_config.model_copy(update={"auto_advance": True}),
    })


@pytest.mark.parametrize("blocked", [False, True])
def test_scheduler_and_review_use_the_same_dirty_contract(dirty_paper, blocked):
    factory, _, owner, _, account = dirty_paper
    approve(factory, owner, account)
    with factory() as db:
        before = financial_counts(db)
        add_dirty(db)
        if blocked:
            add_dirty(db, start=FIRST, end=FIRST, status="OPEN")
        result = run_scheduled_paper(db, FIRST, settings=automatic(), clock=lambda: AT)
        assert result["blocked"] == int(blocked)
        assert financial_counts(db) == before
        queued = list(db.scalars(select(JobRun).where(JobRun.job_type == "PAPER_DAILY")))
        if blocked:
            assert result["queued"] == 0 and queued == []
            return
        assert result["queued"] == 1 and len(queued) == 1
        queued[0].status, queued[0].worker_id = "RUNNING", "m17.1-worker"
        job_id = queued[0].id
        db.commit()
    execute(factory, job_id)
    with factory() as db:
        frozen, before = frozen_records(db), financial_counts(db)
        review = PaperReviews(db, settings(), clock=lambda: AT)
        body = ReviewPaperAccount(request_id="review", asof_date=FIRST, window_days=1)
        receipt = review.create(owner, account, body)
        assert review.create(owner, account, body).id == receipt.id
        assert db.scalar(select(func.count()).select_from(PaperOutcomeReview)) == 1
        assert financial_counts(db) == before
        assert_preserved(db, frozen)
        add_dirty(db, start=FIRST, end=FIRST, status="FAILED")
        with pytest.raises(PaperError, match="SOURCE_DIRTY_RANGE"):
            review.create(owner, account, body.model_copy(update={"request_id": "blocked-review"}))
        assert db.scalar(select(func.count()).select_from(PaperOutcomeReview)) == 1
        assert financial_counts(db) == before
        assert_preserved(db, frozen)


@pytest.mark.parametrize("change", ["algo", "strategy", "opportunity_version"])
def test_owner_boundaries_precede_dirty_facts_and_legacy_version_cannot_silently_upgrade(
    dirty_paper, monkeypatch, change,
):
    factory, _, owner, other, account = dirty_paper
    with factory() as db:
        add_dirty(db, start=DAY, end=DAY, status="OPEN")
        before, frozen = financial_counts(db), frozen_records(db)
        with pytest.raises(PaperError) as error:
            PaperQueue(db, settings(), clock=lambda: AT).advance(
                other, account, AdvancePaperAccount(request_id="other", trade_date=FIRST),
            )
        assert error.value.status_code == 404
        row = db.get(PaperAccount, account)
        changed = settings().model_copy(deep=True)
        if change == "algo":
            changed.algo_version = "m17.1-incompatible"
        elif change == "strategy":
            changed.strategy["universe"]["min_listed_trading_days"] += 1
        else:
            monkeypatch.setattr("app.services.paper.account_state.OPPORTUNITY_CALC_VERSION",
                                "m17.1-incompatible")
        with pytest.raises(PaperError, match="PAPER_SOURCE_VERSION_DRIFT"):
            account_settings(row, changed)
        assert financial_counts(db) == before
        assert_preserved(db, frozen)
