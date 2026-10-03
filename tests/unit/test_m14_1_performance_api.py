import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.api.v1.performance as performance_api
from app.core.db import get_db
from app.main import app
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.services.auth.dependencies import require_authenticated_user
from app.services.performance.application import (
    PerformanceConflictError,
    PerformanceRunNotSuccessError,
)
from fastapi.testclient import TestClient


def _report(run_id: uuid.UUID) -> PortfolioPerformanceReport:
    return PortfolioPerformanceReport(
        id=uuid.uuid4(),
        run_id=run_id,
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
        source_hash="b" * 64,
        status="SUCCESS",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 6),
        trade_days=2,
        initial_nav=Decimal("1"),
        final_nav=Decimal("1.01"),
        cumulative_return=Decimal("0.01"),
        annualized_return=Decimal("2.5"),
        max_drawdown=Decimal("0"),
        max_drawdown_peak_date=None,
        max_drawdown_trough_date=None,
        max_drawdown_recovery_date=None,
        max_drawdown_duration_days=0,
        positive_days=1,
        negative_days=0,
        flat_days=1,
        warnings=["SHORT_SAMPLE_ANNUALIZATION"],
        result_summary={},
    )


def _daily(report: PortfolioPerformanceReport) -> list[PortfolioPerformanceDaily]:
    return [
        PortfolioPerformanceDaily(
            performance_id=report.id,
            run_id=report.run_id,
            trade_date=date(2026, 1, 5),
            nav=Decimal("1"),
            daily_return=Decimal("0"),
            cumulative_return=Decimal("0"),
            running_peak_nav=Decimal("1"),
            drawdown=Decimal("0"),
            drawdown_duration_days=0,
            cash_ratio=Decimal("1"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
            position_count=0,
            trading_cost=Decimal("0"),
        )
    ]


def test_performance_api_calculate_report_and_daily_pagination(monkeypatch) -> None:
    run_id = uuid.uuid4()
    report = _report(run_id)

    class FakeService:
        def __init__(self, _db) -> None:
            pass

        def queue_calculation(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(id=uuid.uuid4(), status="QUEUED")

        def get_report(self, requested_run_id):
            assert requested_run_id == run_id
            return report

        def daily_page(self, requested_run_id, *, limit, offset):
            assert requested_run_id == run_id
            assert (limit, offset) == (10, 2)
            return report, _daily(report), 3

    monkeypatch.setattr(performance_api, "PerformanceApplicationService", FakeService)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        queued = client.post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/calculate"
        )
        loaded = client.get(f"/api/v1/portfolio/backtests/{run_id}/performance")
        daily = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/daily",
            params={"limit": 10, "offset": 2},
        )
    finally:
        app.dependency_overrides.clear()

    assert queued.status_code == 202
    assert queued.json()["data"]["job_status"] == "QUEUED"
    assert loaded.status_code == 200
    assert loaded.json()["data"]["performance_version"] == "performance_v1"
    assert loaded.json()["data"]["cumulative_return"] == "0.01"
    assert daily.status_code == 200
    assert daily.json()["meta"]["total"] == 3
    assert daily.json()["meta"]["offset"] == 2


def test_performance_api_reports_not_found_and_active_job_conflict(monkeypatch) -> None:
    run_id = uuid.uuid4()
    job_id = uuid.uuid4()

    class FakeService:
        def __init__(self, _db) -> None:
            pass

        def queue_calculation(self, _run_id):
            raise PerformanceConflictError("already queued", job_id=job_id)

        def get_report(self, _run_id):
            raise LookupError("portfolio performance report not found")

    monkeypatch.setattr(performance_api, "PerformanceApplicationService", FakeService)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        conflict = client.post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/calculate"
        )
        missing = client.get(f"/api/v1/portfolio/backtests/{run_id}/performance")
    finally:
        app.dependency_overrides.clear()

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "PERFORMANCE_CALCULATION_CONFLICT"
    assert conflict.json()["detail"]["job_id"] == str(job_id)
    assert missing.status_code == 404


def test_performance_api_rejects_non_success_run_before_queue(monkeypatch) -> None:
    run_id = uuid.uuid4()

    class FakeService:
        def __init__(self, _db) -> None:
            pass

        def queue_calculation(self, _run_id):
            raise PerformanceRunNotSuccessError("run is not a successful BACKTEST")

    monkeypatch.setattr(performance_api, "PerformanceApplicationService", FakeService)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/calculate"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PERFORMANCE_RUN_NOT_SUCCESS"
