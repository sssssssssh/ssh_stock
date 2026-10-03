import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.api.v1.performance as performance_api
from app.core.db import get_db
from app.main import app
from app.models.performance_risk import (
    PortfolioPerformanceRiskDaily,
    PortfolioPerformanceRiskReport,
)
from app.services.auth.dependencies import require_authenticated_user
from app.services.performance.risk_application import PerformanceRiskConflictError
from app.services.performance.risk_source import PerformanceRiskSourceError
from fastapi.testclient import TestClient


def _report(run_id: uuid.UUID, performance_id: uuid.UUID):
    return PortfolioPerformanceRiskReport(
        id=uuid.uuid4(),
        run_id=run_id,
        performance_id=performance_id,
        risk_version="risk_v1",
        risk_config_hash="a" * 64,
        benchmark_code="000300.SH",
        benchmark_source_hash="b" * 64,
        risk_source_hash="c" * 64,
        status="SUCCESS",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 6),
        trade_days=2,
        risk_free_rate_annual=Decimal("0"),
        benchmark_initial_nav=Decimal("1"),
        benchmark_final_nav=Decimal("1.02"),
        benchmark_cumulative_return=Decimal("0.02"),
        benchmark_annualized_return=Decimal("10"),
        excess_cumulative_return=Decimal("-0.01"),
        relative_nav_final=Decimal("0.99"),
        warnings=["RISK_SHORT_SAMPLE"],
        result_summary={},
    )


def _daily(report: PortfolioPerformanceRiskReport):
    return [
        PortfolioPerformanceRiskDaily(
            risk_id=report.id,
            performance_id=report.performance_id,
            run_id=report.run_id,
            trade_date=date(2026, 1, 5),
            benchmark_reference_close=Decimal("100"),
            benchmark_close=Decimal("101"),
            benchmark_daily_return=Decimal("0.01"),
            benchmark_nav=Decimal("1.01"),
            active_return=Decimal("-0.005"),
            relative_nav=Decimal("0.995"),
            excess_cumulative_return=Decimal("-0.005"),
        )
    ]


def test_risk_api_calculate_report_and_daily_pagination(monkeypatch) -> None:
    run_id = uuid.uuid4()
    performance_id = uuid.uuid4()
    report = _report(run_id, performance_id)

    class FakeService:
        def __init__(self, _db) -> None:
            pass

        def queue_calculation(self, requested_run_id, requested_performance_id):
            assert requested_run_id == run_id
            assert requested_performance_id == performance_id
            return SimpleNamespace(
                id=uuid.uuid4(),
                status="QUEUED",
                job_metadata={"performance_id": str(performance_id)},
            )

        def get_report(self, requested_run_id, requested_performance_id):
            assert requested_run_id == run_id
            assert requested_performance_id == performance_id
            return report

        def daily_page(
            self, requested_run_id, *, performance_id, limit, offset
        ):
            assert requested_run_id == run_id
            assert performance_id == report.performance_id
            assert (limit, offset) == (10, 2)
            return report, _daily(report), 3

    monkeypatch.setattr(
        performance_api, "PerformanceRiskApplicationService", FakeService
    )
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        queued = client.post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/risk/calculate",
            json={"performance_id": str(performance_id)},
        )
        loaded = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/risk",
            params={"performance_id": str(performance_id)},
        )
        daily = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/risk/daily",
            params={
                "performance_id": str(performance_id),
                "limit": 10,
                "offset": 2,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert queued.status_code == 202
    assert queued.json()["data"] == {
        "run_id": str(run_id),
        "performance_id": str(performance_id),
        "job_id": queued.json()["data"]["job_id"],
        "job_status": "QUEUED",
        "risk_version": "risk_v1",
    }
    assert loaded.status_code == 200
    assert loaded.json()["data"]["benchmark_code"] == "000300.SH"
    assert loaded.json()["data"]["benchmark_cumulative_return"] == "0.02"
    assert daily.status_code == 200
    assert daily.json()["meta"]["total"] == 3
    assert daily.json()["meta"]["offset"] == 2
    assert daily.json()["meta"]["benchmark_source_hash"] == "b" * 64


def test_risk_api_rejects_benchmark_override_and_requires_authentication(
    monkeypatch,
) -> None:
    run_id = uuid.uuid4()

    class FakeService:
        def __init__(self, _db) -> None:
            pass

    monkeypatch.setattr(
        performance_api, "PerformanceRiskApplicationService", FakeService
    )
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        rejected = TestClient(app).post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/risk/calculate",
            json={"benchmark_code": "000905.SH"},
        )
    finally:
        app.dependency_overrides.clear()

    unauthenticated = TestClient(app).get(
        f"/api/v1/portfolio/backtests/{run_id}/performance/risk"
    )
    assert rejected.status_code == 422
    assert unauthenticated.status_code == 401


def test_risk_api_maps_source_and_active_job_errors(monkeypatch) -> None:
    run_id = uuid.uuid4()
    job_id = uuid.uuid4()

    class FakeService:
        def __init__(self, _db) -> None:
            pass

        def queue_calculation(self, _run_id, _performance_id):
            raise PerformanceRiskConflictError("already queued", job_id=job_id)

        def get_report(self, _run_id, _performance_id):
            raise PerformanceRiskSourceError(
                "PERFORMANCE_ARTIFACT_RUN_MISMATCH", "belongs to another run"
            )

    monkeypatch.setattr(
        performance_api, "PerformanceRiskApplicationService", FakeService
    )
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        conflict = client.post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/risk/calculate"
        )
        mismatch = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/risk"
        )
    finally:
        app.dependency_overrides.clear()

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {
        "code": "PERFORMANCE_RISK_CALCULATION_CONFLICT",
        "message": "already queued",
        "job_id": str(job_id),
    }
    assert mismatch.status_code == 409
    assert (
        mismatch.json()["detail"]["code"] == "PERFORMANCE_ARTIFACT_RUN_MISMATCH"
    )
