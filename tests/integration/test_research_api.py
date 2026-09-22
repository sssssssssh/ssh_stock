from datetime import date

import app.api.v1.research as research_api
import pytest
from app.core.db import get_db
from app.main import app
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("path", "service"),
    [
        ("/research/opportunities/stats", "opportunity_stats"),
        ("/research/opportunities/buckets", "bucket_stats"),
        ("/research/left/thresholds", "transition_stats"),
        ("/research/right/transitions", "transition_stats"),
        ("/research/trends/topn", "topn_stats"),
        ("/research/positions/stats", "position_stats"),
        ("/research/themes/stats", "theme_stats"),
        ("/research/themes/buckets", "bucket_stats"),
        ("/research/themes/topn", "topn_stats"),
        ("/research/themes/lifecycle", "theme_lifecycle_stats"),
        ("/research/context", "context_stats"),
    ],
)
def test_research_endpoints_are_available_and_filter_by_base_date(monkeypatch, path, service):
    calls = []
    monkeypatch.setattr(
        research_api.analytics,
        service,
        lambda *args, **kwargs: calls.append((args, kwargs)) or [],
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get(f"/api/v1{path}?start=2026-01-01&end=2026-01-31")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["start"] == "2026-01-01"
    assert date(2026, 1, 1) in calls[0][0]


def test_research_status_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        research_api.analytics,
        "research_status",
        lambda db, settings: {"research_version": "research_v1"},
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get("/api/v1/research/status")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["data"]["research_version"] == "research_v1"


def test_research_bucket_whitelist_rejects_unknown_field() -> None:
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get(
            "/api/v1/research/opportunities/buckets?field=sql_expression"
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


@pytest.mark.parametrize("path", ("/research/context", "/research/opportunities/buckets"))
def test_research_type_is_validated_and_passed_to_analytics(monkeypatch, path) -> None:
    calls = []
    service = "context_stats" if path.endswith("context") else "bucket_stats"
    monkeypatch.setattr(
        research_api.analytics, service,
        lambda *args, **kwargs: calls.append((args, kwargs)) or [],
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        invalid = client.get(f"/api/v1{path}?research_type=INVALID")
        valid = client.get(f"/api/v1{path}?research_type=TREND")
    finally:
        app.dependency_overrides.clear()
    assert invalid.status_code == 422
    assert valid.status_code == 200
    assert valid.json()["meta"]["research_type"] == "TREND"
    assert "TREND" in calls[0][0] or calls[0][1].get("research_type") == "TREND"
