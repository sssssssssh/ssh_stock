import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.api.v1.analytics as analytics_api
import app.api.v1.performance as performance_api
from app.core.db import get_db
from app.main import app
from app.services.auth.dependencies import require_authenticated_user
from app.services.performance.analytics_series import (
    AnalyticsSeriesDTO,
    AnalyticsSeriesMetaDTO,
    AnalyticsSeriesPage,
)
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def test_series_api_returns_persisted_values_and_pagination_meta(monkeypatch) -> None:
    run_id, performance_id, risk_id, trade_id, period_id = (
        uuid.uuid4() for _ in range(5)
    )

    class FakeSeries:
        def __init__(self, _db):
            pass

        def page(self, requested_run_id, **requested):
            assert requested_run_id == run_id
            assert requested == {
                "performance_id": performance_id,
                "risk_id": risk_id,
                "trade_id": trade_id,
                "period_id": period_id,
                "limit": 500,
                "offset": 500,
            }
            return AnalyticsSeriesPage(
                rows=[
                    AnalyticsSeriesDTO(
                        trade_date=date(2026, 1, 5),
                        strategy_nav=Decimal("1.0234"),
                        strategy_daily_return=Decimal("0.0021"),
                        strategy_cumulative_return=Decimal("0.0234"),
                        drawdown=Decimal("-0.0112"),
                        benchmark_nav=Decimal("1.0102"),
                        benchmark_daily_return=Decimal("0.0010"),
                        active_return=Decimal("0.0011"),
                    )
                ],
                meta=AnalyticsSeriesMetaDTO(
                    run_id=run_id,
                    performance_id=performance_id,
                    risk_id=risk_id,
                    trade_id=trade_id,
                    period_id=period_id,
                    limit=500,
                    offset=500,
                    total=1200,
                ),
            )

    monkeypatch.setattr(analytics_api, "AnalyticsSeriesReadApplicationService", FakeSeries)
    try:
        response = _client().get(
            f"/api/v1/portfolio/backtests/{run_id}/analytics/series",
            params={
                "performance_id": str(performance_id),
                "risk_id": str(risk_id),
                "trade_id": str(trade_id),
                "period_id": str(period_id),
                "limit": 500,
                "offset": 500,
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["strategy_nav"] == "1.0234"
    assert payload["data"][0]["drawdown"] == "-0.0112"
    assert payload["meta"]["total"] == 1200
    assert payload["meta"]["period_id"] == str(period_id)


def test_episode_api_forwards_explicit_trade_id(monkeypatch) -> None:
    run_id, performance_id, trade_id = (uuid.uuid4() for _ in range(3))

    class FakeTrade:
        def __init__(self, _db):
            pass

        def episode_page(self, requested_run_id, **requested):
            assert requested_run_id == run_id
            assert requested["performance_id"] == performance_id
            assert requested["trade_id"] == trade_id
            report = SimpleNamespace(
                id=trade_id,
                performance_id=performance_id,
                trade_version="trade_v1",
                trade_source_hash="source",
            )
            return report, [], 0

    monkeypatch.setattr(performance_api, "PerformanceTradeApplicationService", FakeTrade)
    try:
        response = _client().get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/trade/episodes",
            params={
                "performance_id": str(performance_id),
                "trade_id": str(trade_id),
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["meta"]["trade_id"] == str(trade_id)


def test_period_api_forwards_explicit_period_id(monkeypatch) -> None:
    run_id, performance_id, risk_id, trade_id, period_id = (
        uuid.uuid4() for _ in range(5)
    )

    class FakePeriod:
        def __init__(self, _db):
            pass

        def page(self, requested_run_id, **requested):
            assert requested_run_id == run_id
            assert requested["period_id"] == period_id
            report = SimpleNamespace(
                id=period_id,
                performance_id=performance_id,
                risk_id=risk_id,
                trade_id=trade_id,
                period_version="period_v1",
                period_source_hash="source",
            )
            return report, [], 0

    monkeypatch.setattr(analytics_api, "PerformancePeriodApplicationService", FakePeriod)
    try:
        response = _client().get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/period",
            params={
                "performance_id": str(performance_id),
                "risk_id": str(risk_id),
                "trade_id": str(trade_id),
                "period_id": str(period_id),
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["meta"]["period_id"] == str(period_id)
