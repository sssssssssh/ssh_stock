import json
import uuid
from datetime import date, timedelta

import sqlalchemy as sa
from app.api.v1.agent import require_agent_user
from app.api.v1.agent_reports import get_report_application
from app.domain.agent.contracts import WalkForwardWindowLineageInput
from app.main import app
from app.models.experiment import PortfolioExperimentTrial
from app.models.market_data import TradeCalendar
from app.models.walk_forward import (
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.chat.application import AgentChatApplication
from app.services.agent.contracts.m15 import BASE_IDENTITY_FIELDS
from app.services.agent.llm.contracts import LLMResponse, ToolCall
from app.services.agent.llm.fake import FakeLLMProvider
from app.services.agent.report.application import AgentReportApplication
from app.services.experiment_evaluation import ExperimentEvaluationApplicationService
from app.services.walk_forward import WalkForwardApplicationService
from fastapi.testclient import TestClient
from m16_6_support import isolated_contract_database
from test_m16_2_2_research_integrity import _align_run_snapshot, _complete_bundle
from test_m16_2_agent_chat import _enabled_settings, _user


def seed_window(db):
    # Synthetic financial fixtures, genuine persisted M14/M15 service identities.
    dates = tuple(date(2088, 1, 2) + timedelta(days=index) for index in range(14))
    db.add_all(TradeCalendar(cal_date=value, is_open=True, exchange="SSE") for value in dates)
    db.flush()
    service = WalkForwardApplicationService(db)
    created = service.create(
        name="m166-window",
        start_date=dates[0],
        end_date=dates[-1],
        mode="ROLLING",
        train_trade_days=7,
        test_trade_days=7,
        step_trade_days=7,
        initial_cash=None,
        benchmark_code=None,
        grid={},
        train_evaluation_policy=None,
    )
    study = db.get(PortfolioWalkForwardStudy, uuid.UUID(created["id"]))
    window = db.scalar(
        sa.select(PortfolioWalkForwardWindow).where(
            PortfolioWalkForwardWindow.study_id == study.id,
        )
    )
    train_case, _ = _complete_bundle(
        db, tuple(date.fromisoformat(d) for d in window.train_trade_dates)
    )
    experiment = service._frozen_experiment_service(study).create_from_frozen_base(
        name="m166-train",
        start_date=window.train_start_date,
        end_date=window.train_end_date,
        grid=study.parameter_space,
        base_config_snapshot=study.base_config_snapshot,
        base_identities={key: getattr(study, key) for key in BASE_IDENTITY_FIELDS},
        commit=False,
    )
    window.train_experiment_id = experiment.id
    trial = db.scalar(
        sa.select(PortfolioExperimentTrial).where(
            PortfolioExperimentTrial.experiment_id == experiment.id,
        )
    )
    trial.run_id = train_case.run_id
    _align_run_snapshot(db, train_case.run_id, experiment, trial)
    db.commit()
    evaluation = ExperimentEvaluationApplicationService(db).calculate_now(experiment.id).report
    service._freeze_selection(window, experiment, evaluation)
    oos_case, period = _complete_bundle(
        db, tuple(date.fromisoformat(d) for d in window.test_trade_dates)
    )
    _align_run_snapshot(db, oos_case.run_id, experiment, trial)
    window.oos_run_id = oos_case.run_id
    db.flush()
    bundle = service.bundle_resolver.resolve(
        oos_case.run_id,
        performance_id=oos_case.performance_id,
        risk_id=oos_case.risk_id,
        trade_id=oos_case.trade_id,
        period_id=period.id,
        require_period=True,
    )
    service._pin_oos_bundle(window, bundle)
    db.commit()
    validation, _ = service.calculate_now(study.id)
    persisted = db.get(
        PortfolioWalkForwardWindowValidation, {"validation_id": validation.id, "window_no": 1}
    )
    db.commit()
    return study.id, validation.id, persisted.return_degradation


def test_real_window_chat_archive_report_comparison_uses_original_m15_formula(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, _):
        with factory() as db:
            study_id, validation_id, expected = seed_window(db)
            settings = _enabled_settings()
            settings.agent_config.archive.enabled = True
            settings.agent_config.frozen_contract.enabled = True
            user = _user(db, suffix="m166-window")
            parameters = dict(study_id=str(study_id), validation_id=str(validation_id), window_no=1)
            result = ResearchAgentAdapter(db).walk_forward_window_lineage(
                WalkForwardWindowLineageInput(**parameters),
            )
            ref = result.evidence[0]
            sources = []
            for role, prefix in (("TRAIN", "train"), ("OOS", "oos")):
                facts = [
                    {
                        "path": f"records.0.{prefix}_metrics.{metric}",
                        "value": str(value),
                        "unit": "decimal",
                        "trade_date": result.as_of_date.isoformat(),
                        "entity": ref.entity_id,
                        "sample_role": role,
                    }
                    for metric, value in result.records[0][prefix + "_metrics"].items()
                    if value is not None
                ]
                fake = FakeLLMProvider(
                    [
                        LLMResponse(
                            tool_calls=[
                                ToolCall(
                                    id="window",
                                    name="walk_forward.window_lineage",
                                    arguments=parameters,
                                )
                            ]
                        ),
                        LLMResponse(
                            final_text=json.dumps(
                                {
                                    "answer": "verified",
                                    "evidence_ids": [],
                                    "warnings": [],
                                    "needs_clarification": False,
                                    "claims": [
                                        {
                                            "claim_id": "window",
                                            "claim_type": "FACT",
                                            "text": "verified",
                                            "evidence_ids": [ref.evidence_id],
                                            "structured_facts": facts,
                                        }
                                    ],
                                }
                            )
                        ),
                    ]
                )
                db.rollback()
                chat_service = AgentChatApplication(db, settings, provider=fake)
                chat = chat_service.create_chat(user=user, title="Synthetic window " + role)
                answer = chat_service.send_message(
                    user=user,
                    chat_id=chat.chat_id,
                    content="核验窗口",
                    request_id=role,
                )
                assert answer.status == "COMPLETED", answer
                sources.append((chat.chat_id, answer.message_id))
            service = AgentReportApplication(db, settings)
            app.dependency_overrides[require_agent_user] = lambda: user
            app.dependency_overrides[get_report_application] = lambda: service
            client = TestClient(app)
            try:
                reports = []
                for index, (chat_id, message_id) in enumerate(sources):
                    response = client.post(
                        "/api/v1/agent/reports",
                        json={
                            "source_chat_id": str(chat_id),
                            "source_message_id": str(message_id),
                            "report_type": "oos_review",
                            "request_id": f"window-report-{index}",
                        },
                    )
                    assert response.status_code == 201, response.text
                    reports.append(response.json()["data"])
                response = client.post(
                    "/api/v1/agent/report-comparisons",
                    json={
                        "left_report_id": reports[0]["report_id"],
                        "right_report_id": reports[1]["report_id"],
                        "request_id": "window-degradation",
                        "comparison_mode": "WINDOW_DEGRADATION",
                    },
                )
                assert response.status_code == 201, response.text
                comparison = response.json()["data"]
                assert comparison["state"] == "COMPARABLE", comparison
                facts = {row["metric_key"]: row for row in comparison["display_result"]["facts"]}
                from decimal import Decimal

                assert Decimal(facts["annualized_return"]["delta"]) == expected
                assert facts["annualized_return"]["formula"] == "TRAIN_MINUS_OOS"
                assert facts["max_drawdown_abs"]["formula"] == "OOS_MINUS_TRAIN"
                assert (
                    "DIFFERENT_TRAIN_OOS_SAMPLES"
                    in comparison["display_result"]["sample_context"]["limitations"]
                )
                assert (
                    client.get(f"/api/v1/agent/reports/{reports[0]['report_id']}/contracts").json()[
                        "meta"
                    ]["total"]
                    == 3
                )
            finally:
                app.dependency_overrides.clear()
