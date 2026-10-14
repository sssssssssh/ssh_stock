from datetime import timedelta
from types import SimpleNamespace

import pytest
from app.api.v1 import decisions
from app.api.v1 import paper as paper_api
from app.api.v1.agent import require_agent_user
from app.domain.decision.account_requests import AdvancePaperAccount, ReviewPaperAccount
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import CreateObservation, CreateProposal
from app.models.paper import (
    DecisionObservation,
    DecisionProposal,
    PaperNavDaily,
    PaperOutcomeReview,
)
from app.services.decision.application import DecisionApplication
from app.services.paper.performance import PaperPerformance
from app.services.paper.queue import PaperQueue
from app.services.paper.reviews import PaperReviews
from fastapi import FastAPI
from fastapi.testclient import TestClient
from m17_support import CODES, DAY, NOW, settings
from sqlalchemy import select
from test_m17_paper_daily import approve, run
from test_m17_paper_daily import paper as paper

FIRST = DAY + timedelta(days=1)


@pytest.fixture
def client(paper, monkeypatch):
    factory, owner, _, _ = paper
    app = FastAPI()
    app.include_router(paper_api.router, prefix="/paper")
    app.include_router(decisions.router, prefix="/decisions")
    actor = [owner]

    def db():
        with factory() as session:
            yield session

    app.dependency_overrides[decisions.get_paper_db] = db
    app.dependency_overrides[require_agent_user] = lambda: SimpleNamespace(id=actor[0])
    monkeypatch.setattr(paper_api, "get_settings", settings)
    monkeypatch.setattr(decisions, "get_settings", settings)
    with TestClient(app) as http:
        yield http, actor


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/performance",
        "/jobs",
        "/orders",
        "/fills",
        "/positions",
        "/reviews",
        "/ledger",
        "/events",
        "/attempts",
        "/days",
        "/runs",
        "/approvals",
    ],
)
def test_every_account_read_is_owner_scoped_404(paper, client, suffix):
    _, _, other, account = paper
    http, actor = client
    actor[0] = other
    response = http.get(f"/paper/accounts/{account}{suffix}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PAPER_NOT_FOUND"


def test_observation_proposal_detail_and_lists_do_not_leak_other_owner(paper, client):
    factory, owner, other, account = paper
    approve(factory, owner, account)
    http, actor = client
    with factory() as db:
        observation = db.scalar(select(DecisionObservation.id))
        proposal = db.scalar(select(DecisionProposal.id))
    actor[0] = other
    assert http.get(f"/decisions/observations/{observation}").status_code == 404
    assert http.get(f"/decisions/proposals/{proposal}").status_code == 404
    assert http.get("/decisions/proposals").json()["data"] == []
    assert http.get("/paper/accounts").json()["data"] == []
    assert http.get(f"/decisions/proposals?account_id={account}").status_code == 404


def test_ledger_reads_and_performance_use_frozen_facts_only(paper, client):
    from app.models.market_data import StockDaily

    factory, owner, _, account = paper
    approve(factory, owner, account)
    run(factory, owner, account)
    http, _ = client
    result = http.get(f"/paper/accounts/{account}/performance")
    assert result.status_code == 200
    first = result.json()["data"]
    assert isinstance(first["cumulative_return"], str)
    assert isinstance(first["maximum_drawdown"], str)
    assert isinstance(first["series"][0]["daily_return"], str)
    with factory() as db:
        db.get(StockDaily, (FIRST, CODES[0])).close = 500
        db.commit()
    second = http.get(f"/paper/accounts/{account}/performance").json()["data"]
    assert first == second
    assert http.get(f"/paper/accounts/{account}/fills").json()["meta"]["total"] == 1
    position = http.get(f"/paper/accounts/{account}/positions?trade_date={FIRST}").json()["data"][0]
    assert position["available_quantity"] == 0
    assert "owner_user_id" not in position


def test_watch_counterfactual_review_is_append_only_and_never_nav(paper):
    from app.models.market_data import StockDaily

    factory, owner, _, account = paper
    with factory() as db:
        application = DecisionApplication(db, settings(), clock=lambda: NOW)
        observation = application.observe(
            owner,
            CreateObservation(request_id="watch-observe", signal_date=DAY, account_id=account),
        )
        proposal = application.propose(
            owner,
            CreateProposal(
                request_id="watch",
                account_id=account,
                observation_id=observation.id,
                ts_code=CODES[0],
                action="WATCH",
            ),
        )
        original_proposal_hash = proposal.record_hash
        db.get(StockDaily, (FIRST, CODES[0])).close = 10.2
        db.commit()
    run(factory, owner, account)
    with factory() as db:
        nav = db.scalar(select(PaperNavDaily))
        nav_hash = nav.record_hash
        body = ReviewPaperAccount(request_id="review", asof_date=FIRST)
        service = PaperReviews(db, settings(), clock=lambda: NOW + timedelta(days=1))
        result = service.create(owner, account, body)
        assert service.create(owner, account, body).id == result.id
        service.create(owner, account, body.model_copy(update={"request_id": "review-again"}))
        reviews = list(db.scalars(select(PaperOutcomeReview)))
        assert len(reviews) == 1
        assert reviews[0].record_json["data"]["forward_mark_return"] == "0.02"
        assert reviews[0].record_json["data"]["counterfactual"] is True
        assert reviews[0].record_json["data"]["included_in_nav"] is False
        assert db.scalar(select(DecisionProposal.record_hash)) == original_proposal_hash
        assert db.scalar(select(PaperNavDaily.record_hash)) == nav_hash
        assert nav.nav == 1
        summary = PaperPerformance(db, settings()).summary(owner, account)
        assert summary["observation_metrics"]["windows"]["1"]["hit_rate"] == "1"
        assert summary["observation_metrics"]["windows"]["1"]["valid_marks"] == 1
        assert summary["observation_metrics"]["included_in_nav"] is False


def test_manual_advance_only_enqueues_and_replays_same_job(paper):
    factory, owner, _, account = paper
    with factory() as db:
        queue = PaperQueue(db, settings(), clock=lambda: NOW + timedelta(days=1))
        body = AdvancePaperAccount(request_id="advance", trade_date=FIRST)
        job = queue.advance(owner, account, body)
        assert job.status == "QUEUED"
        assert queue.advance(owner, account, body).id == job.id
        assert (
            queue.advance(
                owner, account, body.model_copy(update={"request_id": "advance-other"})
            ).id
            == job.id
        )
        assert db.scalar(select(PaperNavDaily.id)) is None
        with pytest.raises(PaperError, match="IDEMPOTENCY_CONFLICT"):
            queue.advance(owner, account, body.model_copy(update={"trade_date": DAY}))


def test_page_bounds_and_filters(paper, client):
    factory, owner, _, account = paper
    with factory() as db:
        application = DecisionApplication(db, settings(), clock=lambda: NOW)
        observation = application.observe(
            owner, CreateObservation(request_id="page-observe", signal_date=DAY, account_id=account)
        )
        for index in range(24):
            application.propose(
                owner,
                CreateProposal(
                    request_id=f"page:{index}",
                    account_id=account,
                    observation_id=observation.id,
                    ts_code=CODES[0],
                    action="WATCH",
                ),
            )
    http, _ = client
    first = http.get(f"/decisions/proposals?account_id={account}&limit=20").json()
    last = http.get(f"/decisions/proposals?account_id={account}&limit=20&offset=20").json()
    assert len(first["data"]) == 20 and len(last["data"]) == 4
    assert first["meta"]["total"] == last["meta"]["total"] == 24
    assert (
        http.get(f"/decisions/proposals?account_id={account}&state=APPROVED").json()["data"] == []
    )
    assert http.get("/paper/accounts?limit=101").status_code == 422
    assert http.get("/paper/accounts?offset=-1").status_code == 422


def test_same_owner_wrong_account_child_is_404(paper, client):
    from app.domain.decision.account_requests import CreatePaperAccount
    from app.services.paper.accounts import PaperAccountApplication

    factory, owner, _, account = paper
    approve(factory, owner, account)
    run(factory, owner, account)
    http, _ = client
    nav = http.get(f"/paper/accounts/{account}/days").json()["data"][0]
    with factory() as db:
        other_account = PaperAccountApplication(db, settings(), clock=lambda: NOW).create(
            owner,
            CreatePaperAccount(request_id="second-owned", name="second", initial_cash="100000"),
        )
    assert http.get(f"/paper/accounts/{other_account.id}/days/{nav['id']}").status_code == 404


def test_review_detects_corrected_source_but_preserves_prior_artifacts(paper):
    from app.models.market_data import StockDaily
    from app.models.paper import PaperDayRun

    factory, owner, _, account = paper
    with factory() as db:
        application = DecisionApplication(db, settings(), clock=lambda: NOW)
        observation = application.observe(
            owner,
            CreateObservation(request_id="drift-observe", signal_date=DAY, account_id=account),
        )
        application.propose(
            owner,
            CreateProposal(
                request_id="drift-watch",
                account_id=account,
                observation_id=observation.id,
                ts_code=CODES[0],
                action="WATCH",
            ),
        )
    run(factory, owner, account)
    with factory() as db:
        service = PaperReviews(db, settings(), clock=lambda: NOW + timedelta(days=1))
        service.create(
            owner, account, ReviewPaperAccount(request_id="first-review", asof_date=FIRST)
        )
        original = db.scalar(select(PaperOutcomeReview.record_hash))
        nav_hash = db.scalar(select(PaperNavDaily.record_hash))
        db.get(StockDaily, (FIRST, CODES[0])).close = 10.1
        db.commit()
        with pytest.raises(PaperError, match="PAPER_SOURCE_DRIFT"):
            service.create(
                owner, account, ReviewPaperAccount(request_id="drift-review", asof_date=FIRST)
            )
        assert db.scalar(select(PaperOutcomeReview.record_hash)) == original
        assert db.scalar(select(PaperNavDaily.record_hash)) == nav_hash
        assert set(db.scalars(select(PaperDayRun.status))) == {"REVIEW_REQUIRED"}


def test_benchmark_unavailable_keeps_nullable_comparison(paper):
    factory, owner, _, account = paper
    run(factory, owner, account)
    with factory() as db:
        result = PaperPerformance(db, settings()).summary(owner, account)
        assert result["mode"] == "PAPER" and result["continuous"]
        assert result["execution"]["hypothetical_fill_rate"] is None
