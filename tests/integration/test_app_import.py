from collections.abc import Generator
from typing import Any

from app.core.db import get_db
from app.main import app
from fastapi.testclient import TestClient


def test_health() -> None:
    class FakeSession:
        def execute(self, _stmt: Any) -> None:
            return None

    def fake_get_db() -> Generator[FakeSession, None, None]:
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_health_reports_database_failure() -> None:
    class FakeSession:
        def execute(self, _stmt: Any) -> None:
            raise RuntimeError("database unavailable")

    def fake_get_db() -> Generator[FakeSession, None, None]:
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_get_db
    try:
        response = TestClient(app).get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["database"] == "unavailable"


def test_dashboard_summary_returns_empty_payload_without_state_date() -> None:
    class FakeResult:
        def scalar_one_or_none(self) -> None:
            return None

    class FakeSession:
        def execute(self, _stmt: Any) -> FakeResult:
            return FakeResult()

    def fake_get_db() -> Generator[FakeSession, None, None]:
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_get_db
    try:
        client = TestClient(app)
        response = client.get("/api/v1/dashboard/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["trade_date"] is None
    assert body["data"]["right_side_new"] == []
    assert body["data"]["theme_heat_top"] == []
    assert body["data"]["left_reversal_top"] == []


def test_milestone10_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/themes" in paths
    assert "/api/v1/themes/{theme_code}/overview" in paths
    assert "/api/v1/themes/{theme_code}/members" in paths
    assert "/api/v1/opportunities/left-reversal" in paths
    assert "/api/v1/opportunities/right-side" in paths
    assert "/api/v1/opportunities/trends" in paths
