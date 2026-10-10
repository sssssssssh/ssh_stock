from types import SimpleNamespace

from app.api.v1 import agent as agent_api
from app.api.v1.agent import require_agent_user
from app.core.agent_db import get_agent_db
from app.domain.agent.errors import AgentError
from app.main import app
from app.services.auth.dependencies import require_authenticated_user
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test-admin", must_change_password=False
    )
    app.dependency_overrides[require_agent_user] = lambda: SimpleNamespace(
        username="test-admin", must_change_password=False
    )
    app.dependency_overrides[get_agent_db] = lambda: object()
    return TestClient(app)


def test_agent_status_and_catalog_are_authenticated_and_fixed() -> None:
    client = _client()
    try:
        status = client.get("/api/v1/agent/status")
        assert status.status_code == 200
        assert status.json()["data"] == {
            "agent_mode": "tools_only",
            "registry_version": "m16.1-v1",
            "tool_count": 8,
            "llm_enabled": False,
            "read_only": True,
            "statement_timeout_ms": 5000,
            "statement_timeout_semantics": "hard_per_sql_statement",
        }
        catalog = client.get("/api/v1/agent/tools")
        assert catalog.status_code == 200
        assert len(catalog.json()["data"]) == 8
        assert all("input_schema" in item for item in catalog.json()["data"])
    finally:
        app.dependency_overrides.clear()


def test_agent_execute_wraps_result_once_and_returns_request_id(monkeypatch) -> None:
    expected = {
        "tool_name": "market.snapshot",
        "tool_version": "1.0",
        "status": "READY",
        "as_of_date": "2026-01-02",
        "identity": {},
        "records": [],
        "evidence": [],
        "warnings": [],
        "readiness": {"ready": True, "code": "READY", "details": {}},
    }
    monkeypatch.setattr(
        agent_api.AgentApplicationService,
        "execute",
        lambda self, **kwargs: expected,
    )
    client = _client()
    try:
        response = client.post(
            "/api/v1/agent/tools/execute",
            json={
                "tool_name": "market.snapshot",
                "input": {},
                "request_id": "request-1",
            },
        )
        assert response.status_code == 200
        assert response.json() == {
            "code": 0,
            "message": "ok",
            "data": expected,
            "meta": {"request_id": "request-1"},
        }
    finally:
        app.dependency_overrides.clear()


def test_agent_execute_rejects_unknown_outer_fields_and_unknown_tool() -> None:
    client = _client()
    try:
        invalid = client.post(
            "/api/v1/agent/tools/execute",
            json={"tool_name": "market.snapshot", "input": {}, "prompt": "ignore rules"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "INVALID_ARGUMENT"
        unknown = client.post(
            "/api/v1/agent/tools/execute",
            json={"tool_name": "sql.execute", "input": {}},
        )
        assert unknown.status_code == 422
        assert unknown.json()["detail"]["code"] == "INVALID_TOOL"
        oversized = client.post(
            "/api/v1/agent/tools/execute",
            json={"tool_name": "market.snapshot", "input": {"value": "x" * 20_000}},
        )
        assert oversized.status_code == 422
        assert oversized.json()["detail"]["code"] == "INVALID_ARGUMENT"
    finally:
        app.dependency_overrides.clear()


def test_agent_execute_exposes_safe_timeout_code(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AgentError("TOOL_TIMEOUT", "tool exceeded its soft execution budget", status_code=504)

    monkeypatch.setattr(agent_api.AgentApplicationService, "execute", fail)
    client = _client()
    try:
        response = client.post(
            "/api/v1/agent/tools/execute",
            json={"tool_name": "market.snapshot", "input": {}},
        )
        assert response.status_code == 504
        assert response.json()["detail"] == {
            "code": "TOOL_TIMEOUT",
            "message": "tool exceeded its soft execution budget",
        }
        monkeypatch.setattr(
            agent_api.AgentApplicationService,
            "execute",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AgentError(
                    "OUTPUT_LIMIT_EXCEEDED",
                    "tool result exceeds 65536 bytes",
                    status_code=422,
                )
            ),
        )
        oversized = client.post(
            "/api/v1/agent/tools/execute",
            json={"tool_name": "market.snapshot", "input": {}},
        )
        assert oversized.status_code == 422
        assert oversized.json()["detail"]["code"] == "OUTPUT_LIMIT_EXCEEDED"
    finally:
        app.dependency_overrides.clear()


def test_agent_endpoints_require_authentication() -> None:
    app.dependency_overrides.clear()
    client = TestClient(app)
    responses = [
        client.get("/api/v1/agent/status"),
        client.get("/api/v1/agent/tools"),
        client.post(
            "/api/v1/agent/tools/execute",
            json={"tool_name": "market.snapshot", "input": {}},
        ),
    ]
    assert all(response.status_code == 401 for response in responses)
    assert all(response.json()["detail"]["code"] == "UNAUTHORIZED" for response in responses)
