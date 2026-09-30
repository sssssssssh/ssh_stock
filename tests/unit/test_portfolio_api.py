import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import app.api.v1.portfolio as portfolio_api
from app.core.db import get_db
from app.domain.portfolio import PortfolioTarget, TargetPosition
from app.main import app
from app.services.auth.dependencies import require_authenticated_user
from app.services.portfolio.candidates import CandidateBatch
from app.services.portfolio.contracts import (
    PortfolioSourceNotReadyError,
    SourceReadinessStatus,
)
from fastapi.testclient import TestClient


class FakePortfolioService:
    def __init__(self, _db) -> None:
        pass

    def identity_meta(self):
        return {
            "portfolio_version": "portfolio_v1",
            "execution_version": "execution_v3",
            "backtest_engine_version": "backtest_v3",
        }

    def get_config_status(self):
        return {"account_mode": "BACKTEST", **self.identity_meta()}

    def list_candidates(self, trade_date):
        return CandidateBatch(
            trade_date=trade_date,
            candidates=(),
            source_status=SourceReadinessStatus.INCOMPLETE,
            source_reason="RAW_UNIVERSE_SET_MISMATCH",
            expected_count=2,
            stock_daily_count=1,
            factor_count=1,
            state_count=1,
            opportunity_count=1,
            mismatch_layers=("stock_daily",),
            missing_code_samples={"stock_daily": ("000001.SZ",)},
            extra_code_samples={},
        )

    def preview_target(self, trade_date):
        return PortfolioTarget(
            signal_trade_date=trade_date,
            targets=(
                TargetPosition("000001.SZ", Decimal("0.1"), Decimal("88")),
            ),
            target_cash_ratio=Decimal("0.9"),
            source_available=True,
        )

    def list_backtests(self, *, limit, offset):
        return []

    def get_backtest(self, run_id):
        return None


def test_portfolio_endpoints_require_authentication() -> None:
    app.dependency_overrides.pop(require_authenticated_user, None)
    response = TestClient(app).get("/api/v1/portfolio/config")
    assert response.status_code == 401


def test_portfolio_read_and_preview_endpoints_return_identity_without_writes(
    monkeypatch,
) -> None:
    monkeypatch.setattr(portfolio_api, "PortfolioApplicationService", FakePortfolioService)
    fake_db = SimpleNamespace(commits=0, adds=0)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        config = client.get("/api/v1/portfolio/config")
        candidates = client.get(
            "/api/v1/portfolio/candidates", params={"trade_date": "2026-09-01"}
        )
        preview = client.post(
            "/api/v1/portfolio/targets/preview", json={"trade_date": "2026-09-01"}
        )
        listing = client.get("/api/v1/portfolio/backtests")
        missing = client.get(f"/api/v1/portfolio/backtests/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert config.status_code == 200
    assert config.json()["meta"]["portfolio_version"] == "portfolio_v1"
    assert candidates.json()["meta"]["source_available"] is True
    assert candidates.json()["meta"]["source_ready"] is False
    assert candidates.json()["meta"]["source_status"] == "INCOMPLETE"
    assert candidates.json()["meta"]["expected_count"] == 2
    assert candidates.json()["meta"]["factor_count"] == 1
    assert candidates.json()["meta"]["mismatch_layers"] == ["stock_daily"]
    assert candidates.json()["meta"]["missing_code_samples"] == {
        "stock_daily": ["000001.SZ"]
    }
    assert preview.json()["data"]["targets"][0]["target_weight"] == "0.1"
    assert listing.status_code == 200
    assert missing.status_code == 404
    assert fake_db.commits == 0
    assert fake_db.adds == 0


def test_preview_returns_409_when_portfolio_source_is_not_ready(monkeypatch) -> None:
    class NotReadyPortfolioService(FakePortfolioService):
        def preview_target(self, trade_date):
            batch = self.list_candidates(trade_date)
            raise PortfolioSourceNotReadyError(batch)

    monkeypatch.setattr(
        portfolio_api, "PortfolioApplicationService", NotReadyPortfolioService
    )
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).post(
            "/api/v1/portfolio/targets/preview",
            json={"trade_date": "2026-09-01"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PORTFOLIO_SOURCE_NOT_READY"
    assert response.json()["detail"]["source_status"] == "INCOMPLETE"
    assert response.json()["detail"]["expected_count"] == 2
    assert response.json()["detail"]["mismatch_layers"] == ["stock_daily"]


def test_backtest_create_request_validates_dates_and_money(monkeypatch) -> None:
    monkeypatch.setattr(portfolio_api, "PortfolioApplicationService", FakePortfolioService)
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).post(
            "/api/v1/portfolio/backtests",
            json={
                "start_date": "2026-09-01",
                "end_date": "2026-09-30",
                "initial_cash_cny": 0,
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_backtest_lifecycle_endpoints_are_async_and_report_progress(
    monkeypatch,
) -> None:
    run_id = uuid.uuid4()
    job_id = uuid.uuid4()
    run = SimpleNamespace(id=run_id, status="CREATED")
    job = SimpleNamespace(
        id=job_id,
        status="QUEUED",
        cancel_requested=False,
    )

    class FakeBacktestService:
        def __init__(self, _db) -> None:
            pass

        def execute(self, requested_run_id):
            assert requested_run_id == run_id
            return run, job

        def resume(self, requested_run_id):
            assert requested_run_id == run_id
            return run, job

        def cancel(self, requested_run_id):
            assert requested_run_id == run_id
            job.cancel_requested = True
            return run, job

        def progress(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(
                run=SimpleNamespace(id=run_id, status="RUNNING"),
                job=SimpleNamespace(id=job_id, status="RUNNING"),
                current_trade_date=date(2026, 9, 30),
                current_phase="CLOSE",
                total_trade_days=5,
                completed_trade_days=2,
                progress_pct=40.0,
                error_code=None,
                error_message=None,
            )

    monkeypatch.setattr(
        portfolio_api, "BacktestApplicationService", FakeBacktestService
    )
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        client = TestClient(app)
        execute = client.post(f"/api/v1/portfolio/backtests/{run_id}/execute")
        resume = client.post(f"/api/v1/portfolio/backtests/{run_id}/resume")
        cancel = client.post(f"/api/v1/portfolio/backtests/{run_id}/cancel")
        progress = client.get(f"/api/v1/portfolio/backtests/{run_id}/progress")
    finally:
        app.dependency_overrides.clear()

    assert execute.status_code == 202
    assert execute.json()["data"]["job_status"] == "QUEUED"
    assert resume.status_code == 202
    assert resume.json()["meta"]["resume"] is True
    assert cancel.status_code == 200
    assert cancel.json()["data"]["cancel_requested"] is True
    assert progress.status_code == 200
    assert progress.json()["data"]["current_phase"] == "CLOSE"
    assert progress.json()["data"]["completed_trade_days"] == 2


def test_duplicate_backtest_execute_returns_current_job_conflict(monkeypatch) -> None:
    run_id = uuid.uuid4()
    job_id = uuid.uuid4()

    class ConflictService:
        def __init__(self, _db) -> None:
            pass

        def execute(self, _run_id):
            raise portfolio_api.BacktestConflictError(
                "already active", job_id=job_id
            )

    monkeypatch.setattr(
        portfolio_api, "BacktestApplicationService", ConflictService
    )
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    try:
        response = TestClient(app).post(
            f"/api/v1/portfolio/backtests/{run_id}/execute"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BACKTEST_EXECUTION_CONFLICT"
    assert response.json()["detail"]["job_id"] == str(job_id)
