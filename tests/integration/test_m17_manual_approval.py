import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import (
    ApproveProposal,
    CreateObservation,
    CreateProposal,
    RejectProposal,
)
from app.models.paper import (
    DecisionApprovalEvent,
    DecisionProposal,
    PaperAccount,
    PaperAccountEvent,
    PaperOrder,
)
from app.services.decision.application import DecisionApplication
from app.services.decision.approval import ApprovalApplication
from app.services.paper.records import verify_record
from m16_6_support import isolated_contract_database
from m17_support import CODES, DAY, NOW, seed, settings
from sqlalchemy import func, select


@pytest.fixture
def case(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        with factory() as db:
            owner, other, account = seed(db)
            row = db.get(PaperAccount, account)
            row.state, row.version, row.activated_at = "ACTIVE", 2, NOW
            db.commit()
            app = DecisionApplication(db, settings(), clock=lambda: NOW)
            observation = app.observe(
                owner, CreateObservation(request_id="observe", signal_date=DAY)
            )
            draft = app.propose(
                owner,
                CreateProposal(
                    request_id="draft",
                    account_id=account,
                    observation_id=observation.id,
                    ts_code=CODES[0],
                    action="PROPOSE_BUY",
                    target_weight="0.08",
                ),
            )
        yield factory, engine, (owner, other, account, draft.id, observation.id)


def approve_body(request="approve", weight="0.08"):
    return ApproveProposal(request_id=request, target_weight=weight, confirmed=True)


def test_approval_event_and_intent_atomic_idempotent_and_frozen(case):
    factory, _, (owner, _, _, proposal, _) = case
    with factory() as db:
        app = ApprovalApplication(db, settings(), clock=lambda: NOW)
        event = app.approve(owner, proposal, approve_body())
        order = db.scalar(select(PaperOrder))
        assert order.approval_id == event.id and order.proposal_id == proposal
        assert order.side == "BUY" and order.quantity > 0 and order.quantity % 100 == 0
        assert order.signal_date == DAY and order.scheduled_date == DAY + timedelta(days=1)
        assert db.get(DecisionProposal, proposal).state == "APPROVED"
        assert verify_record(order)["account_snapshot_hash"]
        assert app.approve(owner, proposal, approve_body()).id == event.id
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 1
        with pytest.raises(PaperError, match="IDEMPOTENCY_CONFLICT"):
            app.approve(owner, proposal, approve_body(weight="0.07"))
        with pytest.raises(PaperError, match="DECISION_ALREADY_TERMINAL"):
            app.reject(owner, proposal, RejectProposal(request_id="reject", reason="manual"))


@pytest.mark.parametrize("phase", ["after_approval", "before_commit"])
def test_fault_before_commit_rolls_back_event_order_and_proposal(case, phase):
    factory, _, (owner, _, _, proposal, _) = case
    with factory() as db:

        def fault(actual):
            if actual == phase:
                raise RuntimeError("synthetic crash")

        with pytest.raises(RuntimeError, match="synthetic crash"):
            ApprovalApplication(db, settings(), clock=lambda: NOW, fault_hook=fault).approve(
                owner, proposal, approve_body()
            )
        assert db.get(DecisionProposal, proposal).state == "PENDING_REVIEW"
        assert db.scalar(select(func.count()).select_from(DecisionApprovalEvent)) == 0
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 0
        assert (
            ApprovalApplication(db, settings(), clock=lambda: NOW)
            .approve(owner, proposal, approve_body())
            .decision
            == "APPROVED"
        )


def test_rejection_and_watch_do_not_generate_orders(case):
    factory, _, (owner, _, account, proposal, observation) = case
    with factory() as db:
        app = ApprovalApplication(db, settings(), clock=lambda: NOW)
        rejected = app.reject(
            owner, proposal, RejectProposal(request_id="reject", reason="manual reject")
        )
        assert rejected.decision == "REJECTED" and verify_record(rejected)["plan"] is None
        watch = DecisionApplication(db, settings(), clock=lambda: NOW).propose(
            owner,
            CreateProposal(
                request_id="watch",
                observation_id=observation,
                account_id=account,
                ts_code=CODES[0],
                action="WATCH",
            ),
        )
        with pytest.raises(PaperError, match="WATCH_NOT_EXECUTABLE"):
            app.approve(owner, watch.id, approve_body(request="watch-approve", weight="0"))
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 0


@pytest.mark.parametrize(
    "scenario,code",
    [
        ("paused", "PAPER_ACCOUNT_PAUSED"),
        ("closed", "PAPER_ACCOUNT_CLOSED"),
        ("late", "DECISION_APPROVAL_WINDOW_EXPIRED"),
        ("weight", "SINGLE_WEIGHT_LIMIT"),
        ("owner", "PAPER_NOT_FOUND"),
    ],
)
def test_failed_approval_has_no_partial_intent(case, scenario, code):
    factory, _, (owner, other, account, proposal, _) = case
    with factory() as db:
        if scenario in ("paused", "closed"):
            row = db.get(PaperAccount, account)
            row.state, row.version = scenario.upper(), 3
            db.commit()
        clock = NOW + timedelta(days=1) if scenario == "late" else NOW
        with pytest.raises(PaperError, match=code):
            ApprovalApplication(db, settings(), clock=lambda: clock).approve(
                other if scenario == "owner" else owner,
                proposal,
                approve_body(weight="0.11" if scenario == "weight" else "0.08"),
            )
        assert db.scalar(select(func.count()).select_from(DecisionApprovalEvent)) == 0
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 0


def test_pending_security_conflict_has_audit_and_no_second_order(case):
    factory, _, (owner, _, account, first, observation) = case
    with factory() as db:
        second = DecisionApplication(db, settings(), clock=lambda: NOW).propose(
            owner,
            CreateProposal(
                request_id="draft-2",
                observation_id=observation,
                account_id=account,
                ts_code=CODES[0],
                action="PROPOSE_BUY",
                target_weight="0.05",
            ),
        )
        app = ApprovalApplication(db, settings(), clock=lambda: NOW)
        app.approve(owner, first, approve_body())
        with pytest.raises(PaperError, match="REJECT_CONFLICTING_PENDING"):
            app.approve(owner, second.id, approve_body(request="approve-2", weight="0.05"))
        audit = db.scalar(select(PaperAccountEvent))
        assert verify_record(audit)["reason_code"] == "REJECT_CONFLICTING_PENDING"
        assert db.get(DecisionProposal, second.id).state == "PENDING_REVIEW"
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 1


def test_real_concurrent_approve_reject_only_one_terminal_event(case):
    factory, _, (owner, _, _, proposal, _) = case
    barrier = threading.Barrier(2)

    def run(approved):
        with factory() as db:
            app = ApprovalApplication(db, settings(), clock=lambda: NOW)
            barrier.wait(timeout=10)
            try:
                event = (
                    app.approve(owner, proposal, approve_body())
                    if approved
                    else app.reject(
                        owner, proposal, RejectProposal(request_id="reject", reason="manual")
                    )
                )
                return event.decision
            except PaperError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(run, (True, False)))
    assert outcomes.count("DECISION_ALREADY_TERMINAL") == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(DecisionApprovalEvent)) == 1
        assert db.scalar(select(func.count()).select_from(PaperOrder)) <= 1
