import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.services.experiment.application as experiment_module
import pytest
from app.core.config import get_settings
from app.repositories.experiment import ExperimentTrialRecord
from app.services.experiment.application import (
    ExperimentApplicationError,
    ExperimentApplicationService,
    _experiment_payload,
    _safe_log_fields,
)
from app.services.portfolio.backtest_application import BacktestConflictError


def test_experiment_state_projects_all_cancelled_as_cancelled() -> None:
    payload = _payload(["CANCELLED", "CANCELLED"])

    assert payload["state"] == "CANCELLED"
    assert payload["cancelled_count"] == 2


def test_experiment_state_projects_success_and_cancelled_as_completed_with_errors() -> None:
    assert _payload(["SUCCESS", "CANCELLED"])["state"] == "COMPLETED_WITH_ERRORS"


def test_experiment_state_projects_failed_and_cancelled_without_success_as_failed() -> None:
    assert _payload(["FAILED", "CANCELLED"])["state"] == "FAILED"


def test_parent_cancel_gate_projects_cancelled_when_no_child_is_active() -> None:
    assert _payload(["CREATED", "FAILED"], cancel_requested=True)["state"] == "CANCELLED"


def test_structured_log_allowlist_never_serializes_config_snapshots_or_secrets() -> None:
    experiment_id = uuid.uuid4()

    fields = _safe_log_fields(
        {
            "experiment_id": experiment_id,
            "trial_no": 2,
            "outcome": "DISPATCHED",
            "config_snapshot": {"token": "secret"},
            "parameter_space": {"candidate.min_score": [65, 70]},
            "tushare_token": "secret",
        }
    )

    assert fields == {
        "experiment_id": str(experiment_id),
        "trial_no": 2,
        "outcome": "DISPATCHED",
    }


def test_dispatch_cancel_gate_never_calls_m13_execute(monkeypatch) -> None:
    experiment_id = uuid.uuid4()
    trial_id = uuid.uuid4()
    trial = SimpleNamespace(
        id=trial_id,
        experiment_id=experiment_id,
        trial_no=1,
        run_id=uuid.uuid4(),
        parameter_hash="parameter-hash",
    )
    record = ExperimentTrialRecord(trial=trial, run=None, job=None)
    repository = SimpleNamespace(
        get_for_update=lambda _experiment_id: SimpleNamespace(
            id=experiment_id, cancel_requested=True
        ),
        get_trial_record=lambda _experiment_id, _trial_id: record,
    )
    db = MagicMock()
    db.bind = None
    service = object.__new__(ExperimentApplicationService)
    service.db = db
    service.repository = repository
    service.fault_hook = None
    execute = MagicMock()
    monkeypatch.setattr(
        experiment_module,
        "BacktestApplicationService",
        MagicMock(return_value=SimpleNamespace(execute=execute)),
    )

    outcome = service._dispatch_trial_if_allowed(experiment_id, trial_id)

    assert outcome == "CANCELLED_GATE"
    execute.assert_not_called()
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        (
            {
                "start_date": date(2040, 2, 2),
                "end_date": date(2040, 2, 1),
                "initial_cash": None,
                "benchmark_code": None,
                "grid": {},
            },
            "EXPERIMENT_CONFIG_INVALID",
        ),
        (
            {
                "start_date": date(2040, 2, 1),
                "end_date": date(2040, 2, 2),
                "initial_cash": Decimal("-1"),
                "benchmark_code": None,
                "grid": {},
            },
            "EXPERIMENT_CONFIG_INVALID",
        ),
        (
            {
                "start_date": date(2040, 2, 1),
                "end_date": date(2040, 2, 2),
                "initial_cash": None,
                "benchmark_code": None,
                "grid": {"execution.slippage_bps": [0]},
            },
            "EXPERIMENT_GRID_INVALID",
        ),
    ],
)
def test_create_maps_invalid_dates_base_config_and_grid_to_stable_errors(
    kwargs: dict[str, object], code: str
) -> None:
    service = ExperimentApplicationService(MagicMock(), settings=get_settings())

    with pytest.raises(ExperimentApplicationError) as caught:
        service.create(name="invalid", **kwargs)

    assert caught.value.code == code


def test_service_requires_all_experiment_and_backtest_configuration() -> None:
    settings = get_settings().model_copy(deep=True)
    settings.experiment_config = None

    with pytest.raises(RuntimeError, match="configuration must be loaded"):
        ExperimentApplicationService(MagicMock(), settings=settings)


def test_read_and_cancel_not_found_paths_return_stable_errors() -> None:
    experiment_id = uuid.uuid4()
    service = object.__new__(ExperimentApplicationService)
    service.db = MagicMock()
    service.db.bind = None
    service.repository = MagicMock()
    service.repository.get.return_value = None
    service.repository.get_for_update.return_value = None
    service.fault_hook = None

    for operation in (
        lambda: service.get(experiment_id),
        lambda: service.trials(experiment_id, state=None, limit=10, offset=0),
        lambda: service.trial(experiment_id, uuid.uuid4()),
        lambda: service.cancel(experiment_id),
    ):
        with pytest.raises(ExperimentApplicationError) as caught:
            operation()
        assert caught.value.code == "EXPERIMENT_NOT_FOUND"

    with pytest.raises(ExperimentApplicationError) as caught:
        service.trials(experiment_id, state="UNKNOWN", limit=10, offset=0)
    assert caught.value.code == "EXPERIMENT_CONFIG_INVALID"


def test_identity_and_snapshot_validation_fail_closed_with_structured_event() -> None:
    experiment = SimpleNamespace(
        id=uuid.uuid4(),
        base_config_snapshot={},
    )
    trial = SimpleNamespace(
        id=uuid.uuid4(),
        trial_no=1,
        run_id=uuid.uuid4(),
        parameter_hash="parameter-hash",
        parameter_values={},
    )
    service = object.__new__(ExperimentApplicationService)
    service.repository = SimpleNamespace(get_run=lambda _run_id: None)

    with pytest.raises(ExperimentApplicationError) as identity:
        service._raise_identity_mismatch(
            experiment,
            "identity mismatch",
            trial=trial,
            mismatch_fields=("portfolio_config_hash",),
        )
    assert identity.value.code == "EXPERIMENT_TRIAL_IDENTITY_MISMATCH"

    with pytest.raises(ExperimentApplicationError) as snapshot:
        service._validate_base_snapshot(experiment)
    assert snapshot.value.code == "EXPERIMENT_TRIAL_CONFIG_INVALID"

    with pytest.raises(ExperimentApplicationError) as incomplete_trial:
        service._validate_trial(experiment, trial)
    assert incomplete_trial.value.code == "EXPERIMENT_TRIAL_IDENTITY_MISMATCH"

    with pytest.raises(ExperimentApplicationError) as missing_run:
        service._validate_bound_run(experiment, trial, {})
    assert missing_run.value.code == "EXPERIMENT_TRIAL_IDENTITY_MISMATCH"


def test_parent_cancel_does_not_hide_an_active_running_child() -> None:
    assert _payload(["RUNNING"], cancel_requested=True)["state"] == "RUNNING"


def test_start_and_dispatch_fail_closed_when_parent_or_trial_disappears() -> None:
    experiment_id = uuid.uuid4()
    trial_id = uuid.uuid4()
    service = object.__new__(ExperimentApplicationService)
    service.db = MagicMock()
    service.db.bind = None
    service.repository = MagicMock()
    service.repository.get_for_update.return_value = None
    service.fault_hook = None

    with pytest.raises(ExperimentApplicationError) as missing_start:
        service.start(experiment_id)
    assert missing_start.value.code == "EXPERIMENT_NOT_FOUND"

    with pytest.raises(ExperimentApplicationError) as missing_dispatch:
        service._dispatch_trial_if_allowed(experiment_id, trial_id)
    assert missing_dispatch.value.code == "EXPERIMENT_NOT_FOUND"

    experiment = SimpleNamespace(id=experiment_id, cancel_requested=False)
    service.repository.get_for_update.return_value = experiment
    service.repository.get_trial_record.return_value = None
    with pytest.raises(ExperimentApplicationError) as missing_trial:
        service._dispatch_trial_if_allowed(experiment_id, trial_id)
    assert missing_trial.value.code == "EXPERIMENT_TRIAL_IDENTITY_MISMATCH"


def test_child_cancel_conflict_keeps_parent_gate_committed(monkeypatch) -> None:
    experiment_id = uuid.uuid4()
    trial = SimpleNamespace(
        id=uuid.uuid4(),
        experiment_id=experiment_id,
        trial_no=1,
        run_id=uuid.uuid4(),
        parameter_hash="parameter-hash",
    )
    record = ExperimentTrialRecord(
        trial=trial,
        run=SimpleNamespace(id=trial.run_id, status="RUNNING"),
        job=None,
    )
    experiment = SimpleNamespace(
        id=experiment_id,
        cancel_requested=False,
        updated_at=datetime.now(UTC),
    )
    service = object.__new__(ExperimentApplicationService)
    service.db = MagicMock()
    service.db.bind = None
    service.settings = get_settings()
    service.repository = SimpleNamespace(
        get_for_update=lambda _experiment_id: experiment,
        list_records=lambda _experiment_id: [record],
    )
    service.get = MagicMock(return_value={"state": "CANCELLED"})
    cancel = MagicMock(
        side_effect=BacktestConflictError("child changed", job_id=None)
    )
    monkeypatch.setattr(
        experiment_module,
        "BacktestApplicationService",
        MagicMock(return_value=SimpleNamespace(cancel=cancel)),
    )

    result = service.cancel(experiment_id)

    assert result == {"state": "CANCELLED"}
    assert experiment.cancel_requested is True
    cancel.assert_called_once_with(trial.run_id)
    assert service.db.commit.call_count == 1
    service.db.rollback.assert_called_once()


def _payload(
    statuses: list[str], *, cancel_requested: bool = False
) -> dict[str, object]:
    now = datetime.now(UTC)
    experiment_id = uuid.uuid4()
    experiment = SimpleNamespace(
        id=experiment_id,
        name="state-projection",
        experiment_version="experiment_v1",
        search_method="GRID",
        start_date=date(2040, 1, 1),
        end_date=date(2040, 1, 2),
        initial_cash=100_000,
        benchmark_code="000300.SH",
        definition_hash="definition-hash",
        parameter_space_hash="space-hash",
        parameter_space={},
        trial_count=len(statuses),
        cancel_requested=cancel_requested,
        started_at=now,
        created_at=now,
        updated_at=now,
        base_algo_version="algo-v1",
        base_source_strategy_config_hash="strategy-hash",
        base_opportunity_calc_version="opportunity-v1",
        base_opportunity_config_hash="opportunity-hash",
        base_portfolio_version="portfolio_v3",
        base_portfolio_config_hash="portfolio-hash",
        base_execution_version="execution_v3",
        base_execution_config_hash="execution-hash",
        base_accounting_version="accounting_v3",
        base_accounting_config_hash="accounting-hash",
        base_backtest_engine_version="backtest_v7",
    )
    records = [
        ExperimentTrialRecord(
            trial=SimpleNamespace(id=uuid.uuid4()),
            run=SimpleNamespace(status=status),
            job=None,
        )
        for status in statuses
    ]
    return _experiment_payload(experiment, records)
