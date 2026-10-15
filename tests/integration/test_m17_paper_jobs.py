from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest
from app.api.v1 import decisions, jobs, system
from app.api.v1 import paper as paper_api
from app.api.v1.agent import require_agent_user
from app.core.db import get_db
from app.domain.decision.account_requests import AdvancePaperAccount, ReviewPaperAccount
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import CreateObservation, CreateProposal, PaperRequest
from app.models.job import JobRun
from app.models.market_data import StockDaily, StockOpportunityDaily
from app.models.paper import (
    DecisionObservation,
    DecisionProposal,
    PaperAccount,
    PaperAccountEvent,
    PaperDayRun,
    PaperFill,
    PaperLedgerEntry,
    PaperNavDaily,
    PaperOrder,
    PaperPositionDaily,
)
from app.repositories.paper import PaperRepository
from app.services import job_worker
from app.services.decision.application import DecisionApplication
from app.services.paper.job_application import PaperJobApplication
from app.services.paper.queue import PAPER_DAILY, PAPER_OBSERVATION, PaperQueue
from app.services.paper.recovery import recover_stale_paper_jobs
from app.services.paper.scheduling import run_scheduled_paper
from app.services.retention import run_retention
from fastapi import FastAPI
from fastapi.testclient import TestClient
from m17_support import CODES, DAY, NOW, settings
from sqlalchemy import event, func, select
from test_m17_paper_daily import FIRST, SECOND, approve, run
from test_m17_paper_daily import paper as paper

AT = NOW + timedelta(days=1)


@pytest.fixture(autouse=True)
def bounded_lock_waits(paper):
    factory, _, _, _ = paper
    engine = factory.kw["bind"]

    def bound(connection):
        connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")

    event.listen(engine, "begin", bound)
    try:
        yield
    finally:
        event.remove(engine, "begin", bound)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def enqueue(factory, owner, account, *, request="queued", day=FIRST, clock=lambda: AT):
    with factory() as db:
        return (
            PaperQueue(db, settings(), clock=clock)
            .advance(owner, account, AdvancePaperAccount(request_id=request, trade_date=day))
            .id
        )


def claim(factory, monkeypatch, *, worker="synthetic-worker"):
    monkeypatch.setattr(job_worker, "get_settings", settings)
    monkeypatch.setattr(job_worker, "SessionLocal", factory)
    with factory() as db:
        return job_worker.claim_next_job(db, worker)


def execute(factory, job, *, fault=None, clock=lambda: AT):
    with factory() as db:
        return PaperJobApplication(db, settings(), clock=clock, fault_hook=fault).run_job(job)


def test_worker_dispatch_completes_financial_bundle_and_job_atomically(paper, monkeypatch):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job_id = enqueue(factory, owner, account)
    assert claim(factory, monkeypatch) == job_id
    real = PaperJobApplication
    monkeypatch.setattr(
        job_worker, "PaperJobApplication", lambda db, config: real(db, config, clock=lambda: AT)
    )
    monkeypatch.setattr(job_worker, "_provider", lambda *_: pytest.fail("PAPER called Provider"))
    with factory() as db:
        job_worker.execute_claimed_job(db, job_id)
    with factory() as db:
        job = db.get(JobRun, job_id)
        assert job.status == "SUCCESS" and job.job_metadata["progress_pct"] == 100
        assert count(db, PaperFill) == 1 and count(db, PaperNavDaily) == 1
        assert set(db.scalars(select(PaperDayRun.status))) == {"SUCCESS"}
        assert set(db.scalars(select(PaperDayRun.job_id))) == {job_id}
        hashes = list(
            db.scalars(select(PaperLedgerEntry.record_hash).order_by(PaperLedgerEntry.id))
        )
    execute(factory, job_id)
    with factory() as db:
        assert (
            list(db.scalars(select(PaperLedgerEntry.record_hash).order_by(PaperLedgerEntry.id)))
            == hashes
        )


@pytest.mark.parametrize("phase", ["before_orders", "after_fill", "before_nav", "before_commit"])
def test_crash_rolls_back_finance_failed_job_can_explicitly_retry(paper, monkeypatch, phase):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)

    def crash(point):
        if point == phase:
            raise RuntimeError("private SQL parameters must not be stored")

    with pytest.raises(RuntimeError):
        execute(factory, job, fault=crash)
    with factory() as db:
        row = db.get(JobRun, job)
        assert row.status == "FAILED" and row.error_message == "PAPER_EXECUTION_FAILED"
        assert count(db, PaperFill) == 0 and count(db, PaperNavDaily) == 0
        assert count(db, PaperDayRun) == 0 and count(db, PaperLedgerEntry) == 1
    retry = enqueue(factory, owner, account, request="explicit-retry")
    assert retry != job and claim(factory, monkeypatch) == retry
    execute(factory, retry)
    with factory() as db:
        assert count(db, PaperFill) == 1 and db.get(JobRun, retry).status == "SUCCESS"


def test_postcommit_reply_loss_never_downgrades_success_or_debits_again(paper, monkeypatch):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)

    def crash(point):
        if point == "after_commit":
            raise RuntimeError("lost reply")

    with pytest.raises(RuntimeError):
        execute(factory, job, fault=crash)
    with factory() as db:
        assert db.get(JobRun, job).status == "SUCCESS" and count(db, PaperFill) == 1
    execute(factory, job)
    with factory() as db:
        assert count(db, PaperFill) == 1 and count(db, PaperLedgerEntry) == 2


def test_cancel_during_financial_execution_does_not_deadlock_or_commit_partial_day(
    paper, monkeypatch
):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)

    def cancel(point):
        if point == "before_nav":
            with factory() as db:
                PaperQueue(db, settings(), clock=lambda: AT).cancel(
                    owner, account, job, PaperRequest(request_id="cancel-running")
                )

    with pytest.raises(PaperError, match="PAPER_JOB_CANCELLED"):
        execute(factory, job, fault=cancel)
    with factory() as db:
        assert db.get(JobRun, job).status == "CANCELLED"
        assert count(db, PaperFill) == 0 and count(db, PaperNavDaily) == 0
        assert count(db, PaperLedgerEntry) == 1 and count(db, PaperDayRun) == 0


def test_claim_identity_tamper_rejected_before_financial_writes(paper, monkeypatch):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)
    with factory() as db:
        row = db.get(JobRun, job)
        row.job_metadata = {**row.job_metadata, "trade_date": SECOND.isoformat()}
        db.commit()
    with pytest.raises(PaperError, match="PAPER_JOB_IDENTITY_INVALID"):
        execute(factory, job)
    with factory() as db:
        assert count(db, PaperFill) == 0 and db.get(JobRun, job).status == "FAILED"


def test_claim_ownership_loss_fences_old_worker_before_commit(paper, monkeypatch):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)

    def replace(point):
        if point == "before_commit":
            with factory() as db:
                db.get(JobRun, job).worker_id = "replacement-worker"
                db.commit()

    with pytest.raises(PaperError, match="PAPER_JOB_LEASE_LOST"):
        execute(factory, job, fault=replace)
    with factory() as db:
        assert db.get(JobRun, job).worker_id == "replacement-worker"
        assert db.get(JobRun, job).status == "RUNNING" and count(db, PaperFill) == 0
    execute(factory, job)
    with factory() as db:
        assert count(db, PaperFill) == 1 and db.get(JobRun, job).status == "SUCCESS"


def test_two_executions_same_account_day_have_one_financial_result(paper, monkeypatch):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)

    def work():
        try:
            execute(factory, job)
            return "SUCCESS"
        except PaperError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: work(), range(2)))
    assert "SUCCESS" in outcomes and set(outcomes) <= {"SUCCESS", "PAPER_JOB_LEASE_LOST"}
    with factory() as db:
        assert db.get(JobRun, job).status == "SUCCESS" and count(db, PaperFill) == 1
        assert count(db, PaperLedgerEntry) == 2 and count(db, PaperNavDaily) == 1


def test_recovery_skips_active_account_and_requires_explicit_retry_after_crash(paper, monkeypatch):
    factory, owner, _, account = paper
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)
    with factory() as db:
        db.get(JobRun, job).heartbeat_at = AT
        db.commit()
    later = AT + timedelta(minutes=30)
    with factory() as active:
        PaperRepository(active).owned(PaperAccount, owner, account, lock=True)
        with factory() as db:
            assert (
                recover_stale_paper_jobs(db, timeout_minutes=15, now=later, settings=settings())
                == 0
            )
        active.rollback()
    with factory() as db:
        assert recover_stale_paper_jobs(db, timeout_minutes=15, now=later, settings=settings()) == 1
        assert db.get(JobRun, job).status == "FAILED"
        assert db.get(PaperAccount, account).state == "ACTIVE"
        assert count(db, PaperNavDaily) == 0
    retry = enqueue(factory, owner, account, request="after-crash", clock=lambda: later)
    assert claim(factory, monkeypatch) == retry
    execute(factory, retry, clock=lambda: later)
    with factory() as db:
        assert count(db, PaperNavDaily) == 1


def automatic(*, observation=False):
    config = settings()
    decision = config.paper_config.decision.model_copy(
        update={"daily_observation_enabled": observation}
    )
    return config.model_copy(
        update={
            "paper_config": config.paper_config.model_copy(
                update={"auto_advance": True, "decision": decision}
            )
        }
    )


def test_scheduler_never_approves_and_queues_observation_only_after_own_close(paper, monkeypatch):
    factory, owner, _, account = paper
    with factory() as db:
        assert (
            run_scheduled_paper(db, FIRST, settings=automatic(observation=True), clock=lambda: AT)[
                "queued"
            ]
            == 1
        )
        assert (
            run_scheduled_paper(db, FIRST, settings=automatic(observation=True), clock=lambda: AT)[
                "blocked"
            ]
            == 0
        )
        assert count(db, PaperOrder) == 0 and count(db, DecisionObservation) == 0
        queued = list(db.scalars(select(JobRun).where(JobRun.status == "QUEUED")))
        assert len(queued) == 1 and queued[0].job_type == PAPER_DAILY
        job_id = queued[0].id
    claim(factory, monkeypatch)
    execute(factory, job_id)
    with factory() as db:
        run_scheduled_paper(db, FIRST, settings=automatic(observation=True), clock=lambda: AT)
        observed = db.scalar(select(JobRun.id).where(JobRun.job_type == PAPER_OBSERVATION))
    assert claim(factory, monkeypatch) == observed
    execute(factory, observed)
    with factory() as db:
        assert count(db, DecisionObservation) == 1 and count(db, PaperOrder) == 0
        assert db.get(JobRun, observed).status == "SUCCESS"


def test_optional_preinception_observation_generates_no_account_trade(paper, monkeypatch):
    factory, _, _, _ = paper
    with factory() as db:
        result = run_scheduled_paper(
            db, DAY, settings=automatic(observation=True), clock=lambda: NOW
        )
        assert result["queued"] == 1 and result["blocked"] == 0
        job = db.scalar(select(JobRun.id).where(JobRun.job_type == PAPER_OBSERVATION))
    assert claim(factory, monkeypatch) == job
    execute(factory, job, clock=lambda: NOW)
    with factory() as db:
        assert count(db, DecisionObservation) == 1
        assert count(db, PaperOrder) == 0 and count(db, PaperNavDaily) == 0


def test_queued_cancel_is_idempotent_and_disabled_worker_does_not_claim_paper(paper, monkeypatch):
    factory, owner, other, account = paper
    job = enqueue(factory, owner, account)
    config = settings()
    disabled = config.model_copy(
        update={"paper_config": config.paper_config.model_copy(update={"enabled": False})}
    )
    monkeypatch.setattr(job_worker, "get_settings", lambda: disabled)
    with factory() as db:
        assert job_worker.claim_next_job(db, "disabled-worker") is None
        assert db.get(JobRun, job).status == "QUEUED"
        queue = PaperQueue(db, config, clock=lambda: AT)
        body = PaperRequest(request_id="cancel-one")
        with pytest.raises(PaperError) as error:
            queue.cancel(other, account, job, body)
        assert error.value.status_code == 404
        assert queue.cancel(owner, account, job, body).status == "CANCELLED"
        assert queue.cancel(owner, account, job, body).status == "CANCELLED"
        assert count(db, PaperFill) == 0 and count(db, PaperNavDaily) == 0


def test_successful_eod_expires_drafts_with_evidence_unchanged(paper, monkeypatch):
    factory, owner, _, account = paper
    with factory() as db:
        service = DecisionApplication(db, settings(), clock=lambda: NOW)
        observed = service.observe(
            owner,
            CreateObservation(
                request_id="to-expire-observation",
                signal_date=DAY,
                account_id=account,
            ),
        )
        proposal = service.propose(
            owner,
            CreateProposal(
                request_id="to-expire",
                account_id=account,
                observation_id=observed.id,
                ts_code=CODES[0],
                action="WATCH",
            ),
        )
        proposal_id, original = proposal.id, proposal.record_hash
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)
    execute(factory, job)
    execute(factory, job)
    with factory() as db:
        proposal = db.get(DecisionProposal, proposal_id)
        assert proposal.state == "EXPIRED" and proposal.record_hash == original
        assert count(db, PaperOrder) == 0
        alerts = list(
            db.scalars(
                select(PaperAccountEvent).where(
                    PaperAccountEvent.record_json["data"]["kind"].astext == "DECISION_EXPIRED"
                )
            )
        )
        assert len(alerts) == 1


def test_partial_sale_preserves_remaining_positions_frozen_buy_stage(paper):
    factory, owner, _, account = paper
    with factory() as db:
        opportunity = db.get(StockOpportunityDaily, (FIRST, CODES[0], settings().algo_version))
        opportunity.opportunity_stage = "RIGHT_SIDE"
        db.commit()
    approve(factory, owner, account)
    run(factory, owner, account)
    approve(factory, owner, account, day=FIRST, action="PROPOSE_REDUCE", weight="0.04")
    run(factory, owner, account, SECOND)
    with factory() as db:
        remaining = db.scalar(select(PaperPositionDaily).where(
            PaperPositionDaily.account_id == account, PaperPositionDaily.trade_date == SECOND,
        ))
        assert remaining.quantity > 0
        assert remaining.record_json["data"]["context"]["opportunity_stage"] == "TREND"


def test_scheduler_blocks_gap_and_deduplicates_alerts(paper):
    factory, _, _, _ = paper
    with factory() as db:
        for _ in range(2):
            assert (
                run_scheduled_paper(
                    db, SECOND, settings=automatic(), clock=lambda: AT + timedelta(days=1)
                )["blocked"]
                == 1
            )
        assert count(db, JobRun) == 3
        alerts = list(
            db.scalars(
                select(PaperAccountEvent).where(
                    PaperAccountEvent.record_json["data"]["kind"].astext
                    == "PAPER_SCHEDULER_BLOCKED"
                )
            )
        )
        assert len(alerts) == 1 and alerts[0].record_json["data"]["reason_code"] == "PAPER_DAY_GAP"


def test_scheduler_detects_backfill_drift_without_repricing_ledger(paper):
    factory, owner, _, account = paper
    run(factory, owner, account)
    with factory() as db:
        financial_hash = db.scalar(select(PaperNavDaily.record_hash))
        raw = db.get(StockDaily, (FIRST, CODES[0]))
        raw.close = 10.2
        raw.source_updated_at = AT - timedelta(seconds=150)
        db.commit()
        assert (
            run_scheduled_paper(
                db, SECOND, settings=automatic(), clock=lambda: AT + timedelta(days=1)
            )["blocked"]
            == 1
        )
        assert db.scalar(select(PaperNavDaily.record_hash)) == financial_hash
        assert set(db.scalars(select(PaperDayRun.status))) == {"REVIEW_REQUIRED"}


def test_review_worker_results_and_job_are_one_transaction(paper, monkeypatch):
    factory, owner, _, account = paper
    run(factory, owner, account)
    with factory() as db:
        job = (
            PaperQueue(db, settings(), clock=lambda: AT)
            .review(owner, account, ReviewPaperAccount(request_id="review-queue", asof_date=FIRST))
            .id
        )
    assert claim(factory, monkeypatch) == job
    execute(factory, job)
    with factory() as db:
        row = db.get(JobRun, job)
        result = db.get(PaperAccountEvent, row.job_metadata["result_id"])
        assert (
            row.status == "SUCCESS"
            and result.record_json["data"]["kind"] == "PAPER_REVIEW_COMPLETED"
        )


def test_retention_keeps_success_failed_cancelled_paper_jobs_and_finance(paper, monkeypatch):
    factory, owner, _, account = paper
    approve(factory, owner, account)
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)
    execute(factory, job)
    with factory() as db:
        cancelled = PaperQueue(db, settings(), clock=lambda: AT).review(
            owner, account, ReviewPaperAccount(request_id="to-cancel", asof_date=FIRST)
        )
        PaperQueue(db, settings(), clock=lambda: AT).cancel(
            owner, account, cancelled.id, PaperRequest(request_id="cancel-queued")
        )
        failed = PaperQueue(db, settings(), clock=lambda: AT).review(
            owner, account, ReviewPaperAccount(request_id="failed-review", asof_date=FIRST)
        )
        failed.status, failed.finished_at = "FAILED", AT
        db.commit()
        ids = set(db.scalars(select(JobRun.id).where(JobRun.job_type.like("PAPER_%"))))
        before = set(db.scalars(select(PaperLedgerEntry.record_hash)))
        run_retention(db, now=AT + timedelta(days=400))
        assert set(db.scalars(select(JobRun.id).where(JobRun.job_type.like("PAPER_%")))) == ids
        assert set(db.scalars(select(PaperLedgerEntry.record_hash))) == before
        assert count(db, PaperFill) == 1 and count(db, PaperNavDaily) == 1


def test_paper_job_reads_and_cancel_are_owner_scoped_and_hidden_from_legacy_runtime(
    paper, monkeypatch
):
    factory, owner, other, account = paper
    job = enqueue(factory, owner, account)
    claim(factory, monkeypatch)
    app = FastAPI()
    app.include_router(paper_api.router, prefix="/paper")
    app.include_router(jobs.router, prefix="/jobs")
    app.include_router(system.router, prefix="/system")
    actor = [owner]

    def db():
        with factory() as session:
            yield session

    app.dependency_overrides[decisions.get_paper_db] = db
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[require_agent_user] = lambda: SimpleNamespace(id=actor[0])
    monkeypatch.setattr(paper_api, "get_settings", settings)
    monkeypatch.setattr(system, "get_settings", settings)
    with TestClient(app) as http:
        page = http.get(f"/paper/accounts/{account}/jobs").json()
        assert page["meta"]["total"] == 1 and page["meta"]["active_count"] == 1
        assert "owner_user_id" not in page["data"][0]
        assert "metadata" not in page["data"][0]
        assert http.get("/jobs?job_type=PAPER_DAILY").json()["data"] == []
        assert http.get("/system/runtime").json()["data"]["active_job"] is None
        assert http.post(f"/jobs/{job}/cancel").status_code == 404
        actor[0] = other
        assert http.get(f"/paper/accounts/{account}/jobs").status_code == 404
        assert (
            http.post(
                f"/paper/accounts/{account}/jobs/{job}/cancel", json={"request_id": "wrong-owner"}
            ).status_code
            == 404
        )
