import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.api.v1.performance as performance_api
from app.core.db import get_db
from app.main import app
from app.models.performance_trade import (
    PortfolioPerformanceTradeDaily,
    PortfolioPerformanceTradeEpisode,
    PortfolioPerformanceTradeReport,
)
from app.services.auth.dependencies import require_authenticated_user
from app.services.performance.trade_application import PerformanceTradeConflictError
from app.services.performance.trade_source import PerformanceTradeSourceError
from fastapi.testclient import TestClient


def _report(run_id: uuid.UUID, performance_id: uuid.UUID):
    return PortfolioPerformanceTradeReport(
        id=uuid.uuid4(),
        run_id=run_id,
        performance_id=performance_id,
        trade_version="trade_v1",
        trade_config_hash="a" * 64,
        trade_source_hash="b" * 64,
        status="SUCCESS",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 6),
        trade_days=2,
        warnings=[],
        result_summary={},
    )


def test_trade_api_calculate_report_daily_and_episode_filters(monkeypatch) -> None:
    run_id = uuid.uuid4()
    performance_id = uuid.uuid4()
    report = _report(run_id, performance_id)
    daily = PortfolioPerformanceTradeDaily(
        trade_id=report.id,
        performance_id=performance_id,
        run_id=run_id,
        trade_date=date(2026, 1, 5),
        buy_fill_count=1,
        sell_fill_count=0,
        fill_count=1,
        buy_gross_amount=Decimal("1000"),
        sell_gross_amount=Decimal("0"),
        traded_gross_amount=Decimal("1000"),
        commission=Decimal("1"),
        stamp_tax=Decimal("0"),
        transfer_fee=Decimal("0"),
        cash_fee_total=Decimal("1"),
        slippage_cost=Decimal("2"),
        total_execution_cost=Decimal("3"),
        turnover_denominator=Decimal("10000"),
        daily_turnover=Decimal("0.1"),
    )
    episode = PortfolioPerformanceTradeEpisode(
        trade_id=report.id,
        performance_id=performance_id,
        run_id=run_id,
        ts_code="000001.SZ",
        episode_no=1,
        status="OPEN",
        entry_date=date(2026, 1, 5),
        holding_trade_days=2,
        ending_quantity=100,
    )

    class FakeService:
        def __init__(self, _db) -> None:
            pass

        def queue_calculation(self, requested_run_id, requested_performance_id):
            assert (requested_run_id, requested_performance_id) == (
                run_id,
                performance_id,
            )
            return SimpleNamespace(
                id=uuid.uuid4(),
                status="QUEUED",
                job_metadata={"performance_id": str(performance_id)},
            )

        def get_report(self, requested_run_id, requested_performance_id):
            assert (requested_run_id, requested_performance_id) == (
                run_id,
                performance_id,
            )
            return report

        def daily_page(self, requested_run_id, **kwargs):
            assert requested_run_id == run_id
            assert kwargs == {
                "performance_id": performance_id,
                "limit": 10,
                "offset": 2,
            }
            return report, [daily], 3

        def episode_page(self, requested_run_id, **kwargs):
            assert requested_run_id == run_id
            assert kwargs == {
                "performance_id": performance_id,
                "status": "OPEN",
                "ts_code": "000001.SZ",
                "limit": 5,
                "offset": 1,
            }
            return report, [episode], 1

    monkeypatch.setattr(performance_api, "PerformanceTradeApplicationService", FakeService)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="test")
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        queued = client.post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/trade/calculate",
            json={"performance_id": str(performance_id)},
        )
        loaded = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/trade",
            params={"performance_id": str(performance_id)},
        )
        daily_response = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/trade/daily",
            params={"performance_id": str(performance_id), "limit": 10, "offset": 2},
        )
        episodes = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/trade/episodes",
            params={
                "performance_id": str(performance_id),
                "status": "OPEN",
                "ts_code": "000001.SZ",
                "limit": 5,
                "offset": 1,
            },
        )
    finally:
        app.dependency_overrides.clear()

    unauthenticated = TestClient(app).get(
        f"/api/v1/portfolio/backtests/{run_id}/performance/trade"
    )

    assert queued.status_code == 202
    assert queued.json()["data"]["trade_version"] == "trade_v1"
    assert loaded.status_code == 200
    assert loaded.json()["data"]["trade_source_hash"] == "b" * 64
    assert daily_response.status_code == 200
    assert daily_response.json()["meta"]["total"] == 3
    assert daily_response.json()["data"][0]["slippage_cost"] == "2"
    assert episodes.status_code == 200
    assert episodes.json()["meta"]["status"] == "OPEN"
    assert episodes.json()["data"][0]["ts_code"] == "000001.SZ"
    assert unauthenticated.status_code == 401


def test_trade_api_rejects_extra_fields_invalid_status_and_maps_errors(
    monkeypatch,
) -> None:
    run_id = uuid.uuid4()
    job_id = uuid.uuid4()

    class FakeService:
        def __init__(self, _db) -> None:
            pass

        def queue_calculation(self, _run_id, _performance_id):
            raise PerformanceTradeConflictError("already queued", job_id=job_id)

        def get_report(self, _run_id, _performance_id):
            raise PerformanceTradeSourceError(
                "PERFORMANCE_TRADE_ARTIFACT_RUN_MISMATCH",
                "belongs to another run",
            )

    monkeypatch.setattr(performance_api, "PerformanceTradeApplicationService", FakeService)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(username="test")
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        rejected = client.post(
            f"/api/v1/portfolio/backtests/{run_id}/performance/trade/calculate",
            json={"benchmark_code": "000300.SH"},
        )
        conflict = client.post(f"/api/v1/portfolio/backtests/{run_id}/performance/trade/calculate")
        mismatch = client.get(f"/api/v1/portfolio/backtests/{run_id}/performance/trade")
        invalid_status = client.get(
            f"/api/v1/portfolio/backtests/{run_id}/performance/trade/episodes",
            params={"status": "DONE"},
        )
    finally:
        app.dependency_overrides.clear()

    assert rejected.status_code == 422
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["job_id"] == str(job_id)
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == ("PERFORMANCE_TRADE_ARTIFACT_RUN_MISMATCH")
    assert invalid_status.status_code == 422
