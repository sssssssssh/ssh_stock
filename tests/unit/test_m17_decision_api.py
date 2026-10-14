import uuid
from types import SimpleNamespace

import pytest
from app.api.v1 import decisions
from app.core.config import get_settings
from fastapi import FastAPI
from fastapi.testclient import TestClient


def client(monkeypatch, *, authenticated=True):
    app = FastAPI()
    app.include_router(decisions.router, prefix="/api/v1/decisions")
    app.dependency_overrides[decisions.get_paper_db] = lambda: object()
    if authenticated:
        app.dependency_overrides[decisions.require_agent_user] = lambda: SimpleNamespace(
            id=uuid.uuid4()
        )
    else:
        from fastapi import HTTPException

        def unauthorized():
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED"})

        app.dependency_overrides[decisions.require_agent_user] = unauthorized
    monkeypatch.setattr(decisions, "get_settings", get_settings)
    return TestClient(app)


def test_all_new_writes_default_off_and_unauthorized(monkeypatch):
    response = client(monkeypatch).post(
        "/api/v1/decisions/observations", json={"request_id": "x", "signal_date": "2026-10-14"}
    )
    assert response.status_code == 403 and response.json()["detail"]["code"] == "PAPER_DISABLED"
    assert (
        client(monkeypatch, authenticated=False)
        .post(
            "/api/v1/decisions/observations", json={"request_id": "x", "signal_date": "2026-10-14"}
        )
        .status_code
        == 401
    )


@pytest.mark.parametrize("extra", ["owner_user_id", "mode", "price", "cash", "sql", "callback"])
def test_manual_approval_api_forbids_client_facts_and_execution_modes(monkeypatch, extra):
    response = client(monkeypatch).post(
        f"/api/v1/decisions/proposals/{uuid.uuid4()}/approve",
        json={"request_id": "x", "target_weight": "0.08", "confirmed": True, extra: "untrusted"},
    )
    assert response.status_code == 422


def test_missing_confirmation_is_rejected_before_any_business_call(monkeypatch):
    response = client(monkeypatch).post(
        f"/api/v1/decisions/proposals/{uuid.uuid4()}/approve",
        json={"request_id": "x", "target_weight": "0.08"},
    )
    assert response.status_code == 422
