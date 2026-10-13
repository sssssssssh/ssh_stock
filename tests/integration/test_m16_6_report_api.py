import uuid

import pytest
import sqlalchemy as sa
from app.api.v1.agent import require_agent_user
from app.api.v1.agent_reports import get_report_application
from app.domain.agent.report import CreateResearchReport
from app.domain.agent.report_errors import AgentReportError
from app.main import app
from app.models.agent_report import AgentResearchReport
from app.models.portfolio import PortfolioBacktestRun
from app.services.agent.chat.application import AgentChatApplication
from app.services.agent.report.application import AgentReportApplication
from fastapi.testclient import TestClient
from m16_6_support import isolated_contract_database
from test_m16_2_agent_chat import _enabled_settings, _user
from test_m16_6_contract_atomic import _case_and_provider


def captured_answer(db, settings, user, *, benchmark_code="000300.SH"):
    fake = _case_and_provider(db, benchmark_code=benchmark_code)
    chat_service = AgentChatApplication(db, settings, provider=fake)
    chat = chat_service.create_chat(user=user, title="Synthetic API integration")
    answer = chat_service.send_message(
        user=user,
        chat_id=chat.chat_id,
        content="核验冻结收益",
        request_id=uuid.uuid4().hex,
    )
    assert answer.status == "COMPLETED"
    return chat.chat_id, answer.message_id


def test_actual_tool_archive_report_and_comparison_api_are_offline_and_owner_scoped(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, _):
        with factory() as db:
            settings = _enabled_settings()
            settings.agent_config.archive.enabled = True
            settings.agent_config.frozen_contract.enabled = True
            user = _user(db, suffix="m166-api")
            sources = [captured_answer(db, settings, user) for _ in range(2)]
            sources.append(captured_answer(db, settings, user, benchmark_code="000905.SH"))
            service = AgentReportApplication(db, settings)
            app.dependency_overrides[require_agent_user] = lambda: user
            app.dependency_overrides[get_report_application] = lambda: service
            client = TestClient(app)
            try:
                reports = []
                for index, (chat_id, message_id) in enumerate(sources):
                    payload = dict(
                        source_chat_id=str(chat_id),
                        source_message_id=str(message_id),
                        report_type="strategy_review",
                        request_id=f"report-{index}",
                    )
                    response = client.post("/api/v1/agent/reports", json=payload)
                    assert response.status_code == 201, response.text
                    report = response.json()["data"]
                    assert report["report_version"] == "m16.6-report-v1"
                    assert report["contract_check"]["contract_semantics"]["status"] == "VERIFIED"
                    assert report["contract_check"]["calculation_reproduced"] is False
                    assert (
                        client.post("/api/v1/agent/reports", json=payload).json()["data"] == report
                    )
                    reports.append(report)
                path = f"/api/v1/agent/reports/{reports[0]['report_id']}"
                page = client.get(path + "/contracts?limit=1").json()
                assert page["meta"]["total"] == 1
                contract_id = page["data"][0]["contract_id"]
                detail = client.get(path + f"/contracts/{contract_id}")
                assert detail.status_code == 200
                assert detail.json()["data"]["projection"]["selected"]["run_id"]
                assert "config_snapshot" not in detail.text
                assert 'trade_dates"' not in detail.text
                assert client.get(path + f"/contracts/{uuid.uuid4()}").status_code == 404
                assert client.get(path + "/contracts?limit=51").status_code == 422
                assert (
                    client.post(path + "/verify-contracts", json={"repair": True}).status_code
                    == 422
                )
                checks = client.post(path + "/verify-contracts", json={}).json()["data"]
                assert checks["contract_semantics"]["status"] == "VERIFIED"
                payload = dict(
                    left_report_id=reports[0]["report_id"],
                    right_report_id=reports[1]["report_id"],
                    request_id="same-sample",
                    comparison_mode="STRICT_SAME_SAMPLE",
                )
                response = client.post("/api/v1/agent/report-comparisons", json=payload)
                assert response.status_code == 201, response.text
                comparison = response.json()["data"]
                assert comparison["policy_version"] == "m16.6-report-comparison-v4"
                assert comparison["state"] == "COMPARABLE"
                assert comparison["display_result"]["facts"][0]["delta"] == "0"
                assert comparison["display_result"]["comparison_permissions"]["allowed"] is True
                assert (
                    client.post("/api/v1/agent/report-comparisons", json=payload).json()["data"]
                    == comparison
                )
                rejected = client.post(
                    "/api/v1/agent/report-comparisons",
                    json={
                        **payload,
                        "right_report_id": reports[2]["report_id"],
                        "request_id": "benchmark-mismatch",
                    },
                ).json()["data"]
                assert rejected["state"] != "COMPARABLE"
                assert not rejected["display_result"]["comparison_permissions"]["allowed"]
                assert all("delta" not in row for row in rejected["display_result"]["facts"])
                context = client.post(
                    "/api/v1/agent/report-comparisons",
                    json={
                        **payload,
                        "request_id": "sensitivity",
                        "comparison_mode": "DIFFERENT_ASSUMPTIONS",
                    },
                ).json()["data"]
                assert context["state"] == "CONTEXT_REQUIRED"
                assert all("delta" not in row for row in context["display_result"]["facts"])
                # Live source changes cannot change frozen report/comparison decisions.
                run = db.scalar(sa.select(PortfolioBacktestRun))
                run.initial_cash += 100
                db.commit()
                assert client.get(path).json()["data"] == reports[0]
                comparison_path = f"/api/v1/agent/report-comparisons/{comparison['comparison_id']}"
                assert client.get(comparison_path).json()["data"] == comparison
                for export_path in (path, comparison_path):
                    for fmt in ("markdown", "html"):
                        response = client.get(export_path + f"/export?format={fmt}")
                        assert response.status_code == 200, response.text
                        assert "FROZEN_CONTRACT_RECHECK" in response.text
                        assert response.headers["x-content-type-options"] == "nosniff"
                        assert response.headers["cache-control"] == "private, no-store"
                other = _user(db, suffix="m166-other")
                app.dependency_overrides[require_agent_user] = lambda: other
                for target in (
                    path,
                    path + "/contracts",
                    path + f"/contracts/{contract_id}",
                    comparison_path,
                    comparison_path + "/export",
                ):
                    assert client.get(target).status_code == 404
                assert client.post(path + "/verify-contracts", json={}).status_code == 404
            finally:
                app.dependency_overrides.clear()


def test_v4_precommit_verification_failure_leaves_no_report(monkeypatch):
    with isolated_contract_database(monkeypatch) as (factory, _):
        with factory() as db:
            settings = _enabled_settings()
            settings.agent_config.archive.enabled = True
            settings.agent_config.frozen_contract.enabled = True
            user = _user(db, suffix="m166-report-rollback")
            chat_id, message_id = captured_answer(db, settings, user)
            service = AgentReportApplication(db, settings)

            def fail(row):
                raise AgentReportError("SYNTHETIC_VERIFY_FAILED", "synthetic", status_code=409)

            monkeypatch.setattr(service, "_verified_report_view", fail)
            with pytest.raises(AgentReportError, match="synthetic"):
                service.create_report(
                    user=user,
                    body=CreateResearchReport(
                        source_chat_id=chat_id,
                        source_message_id=message_id,
                        report_type="strategy_review",
                        request_id="fail-before-commit",
                    ),
                )
            assert db.scalar(sa.select(sa.func.count()).select_from(AgentResearchReport)) == 0
