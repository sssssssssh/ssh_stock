import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import app.api.v1.walk_forward as walk_forward_api
import pytest
from app.core.db import get_db
from app.main import app
from app.models.walk_forward import (
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardValidationReport,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)
from app.services.auth.dependencies import require_authenticated_user
from app.services.job_worker import WORKER_JOB_TYPES
from app.services.walk_forward import (
    WalkForwardApplicationError,
    WalkForwardConflictError,
)
from app.services.walk_forward.application import WALK_FORWARD_VALIDATION_JOB_TYPE
from app.services.walk_forward.orchestration import WINDOW_STATES, WindowState
from app.services.walk_forward.recovery import (
    WALK_FORWARD_VALIDATION_HEARTBEAT_TIMEOUT_CODE,
    recover_stale_walk_forward_validation_jobs,
)
from fastapi.testclient import TestClient
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint


def _client() -> TestClient:
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def _definition() -> dict[str, object]:
    return {
        "name": "m15.3",
        "start_date": "2020-01-01",
        "end_date": "2026-01-01",
        "mode": "ROLLING",
        "train_trade_days": 252,
        "test_trade_days": 63,
        "step_trade_days": 63,
        "initial_cash_cny": "1000000",
        "benchmark_code": "000300.SH",
        "grid": {"candidate": {"min_score": [65, 70], "top_n": [30]}},
    }


def test_walk_forward_create_and_validation_queue_api_contract(monkeypatch) -> None:
    study_id, job_id = uuid.uuid4(), uuid.uuid4()

    class FakeService:
        def __init__(self, _db):
            pass

        def create(self, **values):
            assert values["mode"] == "ROLLING"
            assert values["grid"] == {
                "candidate.min_score": [65, 70],
                "candidate.top_n": [30],
            }
            assert values["train_evaluation_policy"] is None
            return {"id": str(study_id), "window_count": 4}

        def queue_validation(self, requested_study_id):
            assert requested_study_id == study_id
            return SimpleNamespace(
                id=job_id,
                status="QUEUED",
                job_metadata={
                    "walk_forward_version": "walk_forward_v1",
                    "policy_identity_version": "policy_v1",
                    "validation_policy_hash": "p" * 64,
                    "source_hash": "s" * 64,
                },
            )

    monkeypatch.setattr(
        walk_forward_api, "WalkForwardApplicationService", FakeService
    )
    try:
        client = _client()
        created = client.post("/api/v1/portfolio/walk-forwards", json=_definition())
        queued = client.post(
            f"/api/v1/portfolio/walk-forwards/{study_id}/validation/calculate"
        )
        rejected = client.post(
            "/api/v1/portfolio/walk-forwards",
            json={**_definition(), "unexpected": True},
        )
    finally:
        app.dependency_overrides.clear()
    assert created.status_code == 201
    assert created.json()["data"]["id"] == str(study_id)
    assert queued.status_code == 202
    assert queued.json()["data"] == {
        "study_id": str(study_id),
        "job_id": str(job_id),
        "job_status": "QUEUED",
        "walk_forward_version": "walk_forward_v1",
        "policy_identity_version": "policy_v1",
        "validation_policy_hash": "p" * 64,
        "source_hash": "s" * 64,
    }
    assert rejected.status_code == 422


def test_walk_forward_readiness_api_preserves_all_blockers(monkeypatch) -> None:
    study_id = uuid.uuid4()
    blockers = [
        {
            "code": "WALK_FORWARD_VALIDATION_NOT_READY",
            "window_no": 1,
            "scope": "TRAIN",
            "missing_stage": "performance",
            "action": "CALCULATE_M14_PERFORMANCE_EXTERNALLY",
        },
        {
            "code": "WALK_FORWARD_VALIDATION_NOT_READY",
            "window_no": 2,
            "scope": "OOS",
            "missing_stage": "risk",
            "action": "CALCULATE_M14_RISK_EXTERNALLY",
        },
    ]

    class FakeService:
        def __init__(self, _db):
            pass

        def validation_readiness(self, requested_study_id):
            assert requested_study_id == study_id
            return {
                "study_id": str(study_id),
                "ready": False,
                "error_code": blockers[0]["code"],
                "details": {
                    key: value for key, value in blockers[0].items() if key != "code"
                },
                "blockers": blockers,
            }

    monkeypatch.setattr(walk_forward_api, "WalkForwardApplicationService", FakeService)
    try:
        response = _client().get(
            f"/api/v1/portfolio/walk-forwards/{study_id}/validation/readiness"
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["data"]["blockers"] == blockers


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("WALK_FORWARD_NOT_FOUND", 404),
        ("WALK_FORWARD_CONFIG_INVALID", 422),
        ("WALK_FORWARD_CALENDAR_INCOMPLETE", 422),
        ("WALK_FORWARD_INSUFFICIENT_WINDOWS", 422),
        ("WALK_FORWARD_WINDOW_LIMIT_EXCEEDED", 422),
        ("WALK_FORWARD_VALIDATION_NOT_READY", 409),
    ],
)
def test_walk_forward_error_mapping(monkeypatch, code, expected_status) -> None:
    class FakeService:
        def __init__(self, _db):
            pass

        def get(self, _study_id):
            raise WalkForwardApplicationError(code, "failed", window_no=2)

    monkeypatch.setattr(
        walk_forward_api, "WalkForwardApplicationService", FakeService
    )
    try:
        response = _client().get(
            f"/api/v1/portfolio/walk-forwards/{uuid.uuid4()}"
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == expected_status
    assert response.json()["detail"] == {
        "code": code,
        "message": "failed",
        "window_no": 2,
    }


def test_validation_conflict_exposes_active_job_identity(monkeypatch) -> None:
    study_id, job_id = uuid.uuid4(), uuid.uuid4()

    class FakeService:
        def __init__(self, _db):
            pass

        def queue_validation(self, _study_id):
            raise WalkForwardConflictError("active", job_id=job_id)

    monkeypatch.setattr(
        walk_forward_api, "WalkForwardApplicationService", FakeService
    )
    try:
        response = _client().post(
            f"/api/v1/portfolio/walk-forwards/{study_id}/validation/calculate"
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409
    assert response.json()["detail"]["job_id"] == str(job_id)


def test_walk_forward_schema_freezes_unique_and_composite_owners() -> None:
    study_checks = {
        constraint.name
        for constraint in PortfolioWalkForwardStudy.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_walk_forward_study_step" in study_checks
    window_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in PortfolioWalkForwardWindow.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("train_experiment_id",) in window_uniques
    assert ("train_evaluation_id",) in window_uniques
    assert ("oos_run_id",) in window_uniques
    window_foreign_keys = {
        tuple(element.parent.name for element in constraint.elements)
        for constraint in PortfolioWalkForwardWindow.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert ("train_evaluation_id", "train_experiment_id") in window_foreign_keys
    assert ("selected_trial_id", "train_experiment_id") in window_foreign_keys
    assert (
        "oos_period_id",
        "oos_performance_id",
        "oos_risk_id",
        "oos_trade_id",
        "oos_run_id",
    ) in window_foreign_keys
    report_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in PortfolioWalkForwardValidationReport.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert (
        "study_id",
        "walk_forward_version",
        "policy_identity_version",
        "validation_policy_hash",
        "source_hash",
    ) in report_uniques
    validation_fks = {
        tuple(element.parent.name for element in constraint.elements)
        for constraint in PortfolioWalkForwardWindowValidation.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert ("validation_id", "study_id") in validation_fks
    assert ("study_id", "window_no") in validation_fks
    assert ("selected_trial_id", "selected_train_run_id") in validation_fks
    assert (
        "train_period_id",
        "train_performance_id",
        "train_risk_id",
        "train_trade_id",
        "selected_train_run_id",
    ) in validation_fks


def test_window_state_api_contract_has_a_single_complete_source() -> None:
    assert tuple(get_args(WindowState)) == WINDOW_STATES


def test_migration_0043_downgrade_fails_closed(monkeypatch) -> None:
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261007_0043_m15_3_walk_forward_validation.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0043", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Connection:
        @staticmethod
        def scalar(_statement):
            return 1

    monkeypatch.setattr(module.op, "get_bind", lambda: Connection())
    with pytest.raises(RuntimeError, match="cannot downgrade M15.3"):
        module.downgrade()


def test_migration_0044_downgrade_fails_closed(monkeypatch) -> None:
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261009_0044_m15_3_1_walk_forward_integrity.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0044", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Connection:
        @staticmethod
        def scalar(_statement):
            return 1

    monkeypatch.setattr(module.op, "get_bind", lambda: Connection())
    with pytest.raises(RuntimeError, match="cannot downgrade M15.3.1"):
        module.downgrade()


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _RecoverySession:
    def __init__(self, job):
        self.job = job
        self.added = []
        self.committed = False

    def execute(self, _statement):
        return _Rows(
            [(self.job.id, self.job.worker_id, self.job.job_metadata)]
        )

    def scalar(self, _statement):
        return self.job

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True


def test_walk_forward_validation_recovery_rechecks_lease_and_heartbeat() -> None:
    now = datetime(2026, 10, 7, tzinfo=UTC)
    job = SimpleNamespace(
        id=uuid.uuid4(),
        job_type=WALK_FORWARD_VALIDATION_JOB_TYPE,
        status="RUNNING",
        worker_id="worker-1",
        heartbeat_at=now - timedelta(minutes=20),
        job_metadata={"source_hash": "s" * 64},
        cancel_requested=False,
        finished_at=None,
        step=None,
        error_message=None,
    )
    db = _RecoverySession(job)
    assert recover_stale_walk_forward_validation_jobs(
        db, timeout_minutes=15, now=now
    ) == 1
    assert job.status == "FAILED"
    assert (
        job.job_metadata["error_code"]
        == WALK_FORWARD_VALIDATION_HEARTBEAT_TIMEOUT_CODE
    )
    assert db.committed

    fresh = SimpleNamespace(**{**job.__dict__, "status": "RUNNING"})
    fresh.heartbeat_at = now - timedelta(minutes=20)
    db = _RecoverySession(fresh)

    def refresh_heartbeat(_job_id):
        fresh.heartbeat_at = now

    assert recover_stale_walk_forward_validation_jobs(
        db,
        timeout_minutes=15,
        now=now,
        before_lock_hook=refresh_heartbeat,
    ) == 0
    assert fresh.status == "RUNNING"
    assert WALK_FORWARD_VALIDATION_JOB_TYPE in WORKER_JOB_TYPES
