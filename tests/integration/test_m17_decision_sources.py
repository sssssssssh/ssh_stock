from datetime import timedelta
from decimal import Decimal

import pytest
from app.domain.agent.report import CreateResearchReport
from app.domain.decision.contracts import PaperError
from app.domain.decision.requests import CreateObservation, CreateProposal
from app.models.auth import AppUser
from app.models.job import JobRun
from app.models.market_data import (
    DataDirtyRange,
    StockDaily,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.models.paper import DecisionObservation, DecisionProposal, PaperFill, PaperOrder
from app.services.agent.report.application import AgentReportApplication
from app.services.decision.application import DecisionApplication
from app.services.paper.records import close_cutoff, verify_record
from m16_6_support import isolated_contract_database
from m17_support import CODES, DAY, NOW, seed, settings
from sqlalchemy import func, select
from test_m16_4_research_reports import _source


@pytest.fixture
def case(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, engine):
        with factory() as db:
            ids = seed(db)
        yield factory, engine, ids


def observation():
    return CreateObservation(request_id="observe", signal_date=DAY)


def proposal(account_id, observation_id, *, action="PROPOSE_BUY", **values):
    return CreateProposal(
        request_id="propose",
        account_id=account_id,
        observation_id=observation_id,
        ts_code=CODES[0],
        action=action,
        target_weight="0.1" if action == "PROPOSE_BUY" else "0",
        **values,
    )


def test_observe_and_manual_draft_are_frozen_idempotent_and_do_not_execute(case):
    factory, _, (owner, _, account) = case
    with factory() as db:
        app = DecisionApplication(db, settings(), clock=lambda: NOW)
        row = app.observe(owner, observation())
        assert app.observe(owner, observation()).id == row.id
        data = verify_record(row)
        assert [item["ts_code"] for item in data["candidates"]] == list(CODES)
        assert data["candidates"][0]["reason_codes"] == ["SOURCE_READY", "TREND"]
        draft = app.propose(owner, proposal(account, row.id))
        assert app.propose(owner, proposal(account, row.id)).id == draft.id
        assert draft.state == "PENDING_REVIEW" and draft.score == Decimal("85")
        for model in (PaperOrder, PaperFill):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        with pytest.raises(PaperError, match="IDEMPOTENCY_CONFLICT"):
            app.propose(owner, proposal(account, row.id, note="different payload"))
        with pytest.raises(PaperError, match="IDEMPOTENCY_CONFLICT"):
            app.observe(
                owner, observation().model_copy(update={"signal_date": DAY - timedelta(days=1)})
            )


def test_t_boundary_ignores_future_price_and_score_then_correction_keeps_old_hash(case):
    factory, _, (owner, _, account) = case
    with factory() as db:
        app = DecisionApplication(db, settings(), clock=lambda: NOW)
        row = app.observe(owner, observation())
        original_hash, original_source = row.record_hash, verify_record(row)["source_hash"]
        db.add(
            StockDaily(trade_date=DAY + timedelta(days=1), ts_code=CODES[0], close=999, open=999)
        )
        db.add(
            StockOpportunityDaily(
                trade_date=DAY + timedelta(days=1),
                ts_code=CODES[0],
                algo_version=settings().algo_version,
                state="S5",
                opportunity_stage="STRONG_TREND",
                opportunity_score=999,
                calc_version="future",
                config_hash="a" * 64,
                source_strategy_config_hash="b" * 64,
                calculated_at=NOW + timedelta(days=1),
            )
        )
        db.commit()
        current = app.source.capture(DAY, cutoff=NOW)
        assert current["source_hash"] == original_source
        draft = app.propose(owner, proposal(account, row.id))
        assert draft.score == Decimal("85")
        value = db.get(StockOpportunityDaily, (DAY, CODES[0], settings().algo_version))
        value.opportunity_score = 82.123456789
        db.commit()
        with pytest.raises(PaperError, match="DECISION_SOURCE_DRIFT"):
            app.propose(
                owner, proposal(account, row.id).model_copy(update={"request_id": "changed"})
            )
        assert db.get(DecisionObservation, row.id).record_hash == original_hash
        second = app.observe(
            owner, observation().model_copy(update={"request_id": "new-observation"})
        )
        new_draft = app.propose(
            owner, proposal(account, second.id).model_copy(update={"request_id": "new-draft"})
        )
        db.expire_all()
        assert (
            verify_record(db.get(DecisionProposal, new_draft.id))["candidate"]["opportunity_score"]
            == "82.123456789"
        )


@pytest.mark.parametrize(
    "change,error",
    [
        ("closed", "DECISION_NON_TRADING_DAY"),
        ("factor_version", "SOURCE_NOT_READY"),
        ("factor_missing", "SOURCE_NOT_READY"),
        ("status_missing", "SOURCE_TRADE_STATUS_INCOMPLETE"),
        ("state_mismatch", "SOURCE_STATE_MISMATCH"),
        ("job_missing", "SOURCE_CALC_LINEAGE_UNAVAILABLE"),
        ("raw_stale", "SOURCE_DERIVED_STALE"),
        ("raw_intraday", "SOURCE_DERIVED_STALE"),
        ("calc_intraday", "SOURCE_CALC_LINEAGE_UNAVAILABLE"),
        ("job_intraday", "SOURCE_JOB_NOT_READY"),
        ("dirty", "SOURCE_DIRTY_RANGE"),
    ],
)
def test_readiness_failures_make_no_observation(case, change, error):
    factory, _, (owner, _, _) = case
    with factory() as db:
        if change == "closed":
            db.get(TradeCalendar, DAY).is_open = False
        elif change in ("factor_version", "factor_missing"):
            row = db.get(StockFactorDaily, (DAY, CODES[0]))
            if change == "factor_missing":
                db.delete(row)
            else:
                row.calc_version = "old"
        elif change == "status_missing":
            db.delete(db.get(StockTradeStatusDaily, (DAY, CODES[0])))
        elif change == "state_mismatch":
            db.get(StockStateDaily, (DAY, CODES[0], settings().algo_version)).state = "S1"
        elif change == "job_missing":
            db.get(StockFactorDaily, (DAY, CODES[0])).calc_run_id = None
        elif change == "raw_stale":
            db.get(StockDaily, (DAY, CODES[0])).source_updated_at = NOW
        elif change == "raw_intraday":
            db.get(StockDaily, (DAY, CODES[0])).source_updated_at = close_cutoff(
                DAY
            ) - timedelta(seconds=1)
        elif change == "calc_intraday":
            db.get(StockFactorDaily, (DAY, CODES[0])).calculated_at = close_cutoff(
                DAY
            ) - timedelta(seconds=1)
        elif change == "job_intraday":
            run_id = db.get(StockFactorDaily, (DAY, CODES[0])).calc_run_id
            db.get(JobRun, run_id).finished_at = close_cutoff(DAY) - timedelta(seconds=1)
        else:
            db.add(
                DataDirtyRange(
                    dataset="stock_daily", dirty_start_date=DAY, dirty_end_date=DAY, status="OPEN"
                )
            )
        db.commit()
        with pytest.raises(PaperError, match=error):
            DecisionApplication(db, settings(), clock=lambda: NOW).observe(owner, observation())
        assert db.scalar(select(func.count()).select_from(DecisionObservation)) == 0


def test_owner_security_watch_risks_and_revision(case):
    factory, _, (owner, other, account) = case
    with factory() as db:
        opp = db.get(StockOpportunityDaily, (DAY, CODES[0], settings().algo_version))
        opp.opportunity_stage, opp.extension_risk = "LEFT_WATCH", "HIGH"
        db.commit()
        app = DecisionApplication(db, settings(), clock=lambda: NOW)
        row = app.observe(owner, observation())
        frozen = verify_record(row)
        assert "WATCH_ONLY" in frozen["candidates"][0]["risk_codes"]
        assert "EXTENSION_RISK" in frozen["candidates"][0]["risk_codes"]
        body = proposal(account, row.id, action="WATCH")
        draft = app.propose(owner, body)
        revised = app.propose(
            owner, body.model_copy(update={"request_id": "revision", "supersedes_id": draft.id})
        )
        assert revised.revision == 2 and revised.supersedes_id == draft.id
        with pytest.raises(PaperError) as error:
            app.propose(other, body)
        assert error.value.status_code == 404
        with pytest.raises(PaperError, match="DECISION_SECURITY_MISMATCH"):
            app.propose(
                owner, body.model_copy(update={"request_id": "wrong-code", "ts_code": "000002.SZ"})
            )
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 0


def test_m16_report_reference_is_owned_hash_bound_and_only_context(case):
    factory, _, (owner, other, account) = case
    with factory() as db:
        user = db.get(AppUser, owner)
        chat, message = _source(db, user, value="0.2")
        report = AgentReportApplication(db, settings()).create_report(
            user=user,
            body=CreateResearchReport(
                source_chat_id=chat,
                source_message_id=message,
                report_type="market_review",
                request_id="report",
            ),
        )
        app = DecisionApplication(db, settings(), clock=lambda: NOW)
        row = app.observe(owner, observation())
        body = proposal(
            account,
            row.id,
            action="WATCH",
            source_report_id=report.report_id,
            source_report_hash=report.snapshot_hash,
        )
        draft = app.propose(owner, body)
        ref = verify_record(draft)["source_report"]
        assert (
            ref["snapshot_hash"] == report.snapshot_hash and ref["execution_authorization"] is False
        )
        with pytest.raises(PaperError, match="DECISION_REPORT_HASH_MISMATCH"):
            app.propose(
                owner,
                body.model_copy(update={"request_id": "bad-hash", "source_report_hash": "0" * 64}),
            )
        assert db.scalar(select(func.count()).select_from(PaperOrder)) == 0
        # Use the actual M16 owner boundary, not an owner supplied by the request.
        from app.domain.agent.report_errors import AgentReportError

        with pytest.raises(AgentReportError) as error:
            AgentReportApplication(db, settings()).get_report(
                user=db.get(AppUser, other), report_id=report.report_id
            )
        assert error.value.status_code == 404
