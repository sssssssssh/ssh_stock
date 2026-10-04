import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.api.v1.analytics as analytics_api
from app.core.db import get_db
from app.main import app
from app.services.auth.dependencies import require_authenticated_user
from app.services.performance.analytics_compare import AnalyticsCompareError
from app.services.performance.analytics_read import (
    AnalyticsBacktestDTO,
    AnalyticsIdentityDTO,
    AnalyticsPerformanceDTO,
    AnalyticsRiskDTO,
    AnalyticsSummaryDTO,
    AnalyticsTradeDTO,
)
from fastapi.testclient import TestClient


def _summary(run_id: uuid.UUID) -> AnalyticsSummaryDTO:
    return AnalyticsSummaryDTO(
        schema_version="analytics_read_v1",
        identity=AnalyticsIdentityDTO(
            run_id=run_id,
            performance_id=uuid.uuid4(),
            risk_id=uuid.uuid4(),
            trade_id=uuid.uuid4(),
            period_id=None,
        ),
        backtest=AnalyticsBacktestDTO(
            name="demo",
            status="SUCCESS",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            initial_cash=Decimal("100000.1234"),
            benchmark_code="000300.SH",
        ),
        performance=AnalyticsPerformanceDTO(
            cumulative_return=Decimal("0.1"),
            annualized_return=Decimal("0.2"),
            max_drawdown=Decimal("-0.03"),
            max_drawdown_peak_date=None,
            max_drawdown_trough_date=None,
            max_drawdown_recovery_date=None,
            trade_days=20,
        ),
        risk=AnalyticsRiskDTO(
            benchmark_code="000300.SH",
            benchmark_cumulative_return=Decimal("0.05"),
            benchmark_annualized_return=Decimal("0.1"),
            excess_cumulative_return=Decimal("0.047619"),
            strategy_annualized_volatility=None,
            sharpe_ratio=None,
            sortino_ratio=None,
            calmar_ratio=None,
            tracking_error=None,
            information_ratio=None,
            alpha_annualized=None,
            beta=None,
            correlation=None,
        ),
        trade=AnalyticsTradeDTO(
            total_turnover=Decimal("0.4"),
            annualized_turnover=Decimal("5"),
            traded_gross_amount=Decimal("40000"),
            cash_fee_total=Decimal("30"),
            slippage_cost_total=Decimal("20"),
            total_execution_cost=Decimal("50"),
            total_cost_to_initial_capital=Decimal("0.0005"),
            closed_episode_count=2,
            open_episode_count=0,
            win_rate=None,
            profit_factor=None,
            payoff_ratio=None,
            average_holding_trade_days=None,
            median_holding_trade_days=None,
            closed_realized_pnl=Decimal("100"),
        ),
        warnings=[],
        source_versions={"performance": "performance_v1"},
    )


def test_analytics_summary_is_explicit_and_decimal_safe(monkeypatch) -> None:
    run_id = uuid.uuid4()

    class FakeRead:
        def __init__(self, _db):
            pass

        def summary(self, requested_run_id, **identities):
            assert requested_run_id == run_id
            assert all(value is None for value in identities.values())
            return _summary(run_id)

    monkeypatch.setattr(analytics_api, "AnalyticsReadApplicationService", FakeRead)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="test")
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).get(
            f"/api/v1/portfolio/backtests/{run_id}/analytics/summary"
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["schema_version"] == "analytics_read_v1"
    assert payload["performance"]["annualized_return"] == "0.2"
    assert payload["backtest"]["initial_cash"] == "100000.1234"
    assert "quality_score" not in payload


def test_period_calculate_returns_selected_bundle_ids(monkeypatch) -> None:
    run_id, performance_id, risk_id, trade_id = (uuid.uuid4() for _ in range(4))

    class FakePeriod:
        def __init__(self, _db):
            pass

        def queue_calculation(self, requested_run_id, **requested):
            assert requested_run_id == run_id
            assert requested["performance_id"] == performance_id
            bundle = SimpleNamespace(
                performance=SimpleNamespace(id=performance_id),
                risk=SimpleNamespace(id=risk_id),
                trade=SimpleNamespace(id=trade_id),
            )
            return SimpleNamespace(id=uuid.uuid4(), status="QUEUED"), bundle

    monkeypatch.setattr(analytics_api, "PerformancePeriodApplicationService", FakePeriod)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="test")
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/period/calculate",
            json={
                "performance_id": str(performance_id),
                "risk_id": str(risk_id),
                "trade_id": str(trade_id),
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 202
    assert response.json()["data"]["risk_id"] == str(risk_id)
    assert response.json()["data"]["period_version"] == "period_v1"


def test_compare_incompatible_returns_stable_mismatch_fields(monkeypatch) -> None:
    run_a, run_b = uuid.uuid4(), uuid.uuid4()

    class FakeCompare:
        def __init__(self, _db):
            pass

        def compare(self, _items):
            raise AnalyticsCompareError(
                "ANALYTICS_COMPARE_INCOMPATIBLE",
                "not compatible",
                mismatch_fields=["benchmark_code", "trade_date_set"],
            )

    monkeypatch.setattr(analytics_api, "AnalyticsCompareApplicationService", FakeCompare)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="test")
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).post(
            "/api/v1/portfolio/analytics/compare",
            json={"items": [{"run_id": str(run_a)}, {"run_id": str(run_b)}]},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "ANALYTICS_COMPARE_INCOMPATIBLE",
        "message": "not compatible",
        "mismatch_fields": ["benchmark_code", "trade_date_set"],
    }


def test_all_new_analytics_routes_require_authentication() -> None:
    run_id = uuid.uuid4()
    client = TestClient(app)
    assert client.get(f"/api/v1/portfolio/backtests/{run_id}/analytics/summary").status_code == 401
    assert client.get(f"/api/v1/portfolio/backtests/{run_id}/analytics/context").status_code == 401
    artifacts = client.get(
        f"/api/v1/portfolio/backtests/{run_id}/analytics/artifacts"
    )
    assert artifacts.status_code == 401
