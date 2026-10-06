import uuid
from types import SimpleNamespace

import app.api.v1.experiments as experiments_api
from app.core.db import get_db
from app.main import app
from app.services.auth.dependencies import require_authenticated_user
from app.services.experiment_evaluation import ExperimentEvaluationApplicationError
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app.dependency_overrides[require_authenticated_user] = lambda: SimpleNamespace(
        username="test"
    )
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def test_evaluation_endpoints_forward_filters_and_return_contract(monkeypatch) -> None:
    experiment_id, evaluation_id, job_id = (uuid.uuid4() for _ in range(3))

    class FakeService:
        def __init__(self, _db):
            pass

        def readiness(self, requested_experiment_id):
            assert requested_experiment_id == experiment_id
            return {"experiment_id": str(experiment_id), "ready": True}

        def queue_calculation(self, requested_experiment_id, policy):
            assert requested_experiment_id == experiment_id
            assert policy.primary_objective == "annualized_return"
            return SimpleNamespace(
                id=job_id,
                status="QUEUED",
                job_metadata={
                    "evaluation_version": "experiment_eval_v1",
                    "policy_hash": "p" * 64,
                },
            )

        def detail(self, requested_experiment_id, requested_evaluation_id):
            assert (requested_experiment_id, requested_evaluation_id) == (
                experiment_id,
                evaluation_id,
            )
            return {"id": str(evaluation_id), "shortlist": []}

        def trials(self, requested_experiment_id, requested_evaluation_id, **filters):
            assert (requested_experiment_id, requested_evaluation_id) == (
                experiment_id,
                evaluation_id,
            )
            assert filters == {
                "status": "EVALUATED",
                "feasible": True,
                "shortlisted": False,
                "pareto_front": 2,
                "limit": 20,
                "offset": 5,
            }
            return [], {"total": 0}

        def sensitivity(
            self, requested_experiment_id, requested_evaluation_id, parameter_name
        ):
            assert (requested_experiment_id, requested_evaluation_id) == (
                experiment_id,
                evaluation_id,
            )
            assert parameter_name == "candidate.min_score"
            return [{"parameter_name": parameter_name, "parameter_value": "70"}]

        def history(self, requested_experiment_id, **page):
            assert requested_experiment_id == experiment_id
            assert page == {"limit": 10, "offset": 2}
            return [{"id": str(evaluation_id)}], 1

    monkeypatch.setattr(
        experiments_api, "ExperimentEvaluationApplicationService", FakeService
    )
    policy = {
        "primary_objective": "annualized_return",
        "shortlist_size": 3,
        "constraints": {},
        "pareto_metrics": ["annualized_return", "max_drawdown_abs"],
        "tie_breakers": ["sharpe_ratio"],
    }
    try:
        client = _client()
        readiness = client.get(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluation/readiness"
        )
        calculate = client.post(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluations/calculate",
            json={"policy": policy},
        )
        detail = client.get(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluations/{evaluation_id}"
        )
        trials = client.get(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluations/"
            f"{evaluation_id}/trials",
            params={
                "status": "EVALUATED",
                "feasible": "true",
                "shortlisted": "false",
                "pareto_front": 2,
                "limit": 20,
                "offset": 5,
            },
        )
        sensitivity = client.get(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluations/"
            f"{evaluation_id}/sensitivity",
            params={"parameter_name": "candidate.min_score"},
        )
        history = client.get(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluations",
            params={"limit": 10, "offset": 2},
        )
    finally:
        app.dependency_overrides.clear()
    assert readiness.status_code == 200 and readiness.json()["data"]["ready"]
    assert calculate.status_code == 202
    assert calculate.json()["data"]["evaluation_job_id"] == str(job_id)
    assert detail.status_code == 200
    assert trials.status_code == 200 and trials.json()["meta"]["total"] == 0
    assert sensitivity.status_code == 200
    assert history.status_code == 200 and history.json()["meta"]["total"] == 1


def test_evaluation_errors_map_to_fixed_http_statuses(monkeypatch) -> None:
    experiment_id = uuid.uuid4()

    class FakeService:
        def __init__(self, _db):
            pass

        def queue_calculation(self, _experiment_id, _policy):
            raise ExperimentEvaluationApplicationError(
                "EXPERIMENT_EVALUATION_POLICY_INVALID", "invalid policy"
            )

        def detail(self, _experiment_id, _evaluation_id):
            raise ExperimentEvaluationApplicationError(
                "EXPERIMENT_EVALUATION_NOT_FOUND", "not found"
            )

        def readiness(self, _experiment_id):
            raise ExperimentEvaluationApplicationError(
                "EXPERIMENT_EVALUATION_NOT_READY", "not ready"
            )

    monkeypatch.setattr(
        experiments_api, "ExperimentEvaluationApplicationService", FakeService
    )
    try:
        client = _client()
        invalid = client.post(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluations/calculate",
            json={},
        )
        missing = client.get(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluations/{uuid.uuid4()}"
        )
        not_ready = client.get(
            f"/api/v1/portfolio/experiments/{experiment_id}/evaluation/readiness"
        )
    finally:
        app.dependency_overrides.clear()
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "EXPERIMENT_EVALUATION_POLICY_INVALID"
    assert missing.status_code == 404
    assert not_ready.status_code == 409
