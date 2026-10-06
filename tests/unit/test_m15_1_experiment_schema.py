import importlib.util
import inspect
from pathlib import Path

import pytest
from app.domain.experiment import grid
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from sqlalchemy import UniqueConstraint


def test_experiment_domain_has_no_infrastructure_dependencies() -> None:
    source = inspect.getsource(grid)
    for forbidden in (
        "sqlalchemy",
        "Session",
        "app.models",
        "FastAPI",
        "JobRun",
        "PortfolioBacktestRun",
    ):
        assert forbidden not in source


def test_trial_schema_has_only_authoritative_identity_and_run_pointer() -> None:
    assert set(PortfolioExperimentTrial.__table__.columns.keys()) == {
        "id",
        "experiment_id",
        "trial_no",
        "parameter_values",
        "parameter_hash",
        "portfolio_config_snapshot",
        "portfolio_config_hash",
        "run_id",
        "created_at",
        "updated_at",
    }
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in PortfolioExperimentTrial.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("experiment_id", "trial_no") in unique_columns
    assert ("experiment_id", "parameter_hash") in unique_columns
    assert ("run_id",) in unique_columns
    foreign_keys = {
        key.parent.name: (key.target_fullname, key.ondelete)
        for key in PortfolioExperimentTrial.__table__.foreign_keys
    }
    assert foreign_keys == {
        "experiment_id": ("portfolio_experiment.id", "CASCADE"),
        "run_id": ("portfolio_backtest_run.id", "RESTRICT"),
    }
    assert PortfolioExperiment.__table__.name == "portfolio_experiment"


def test_migration_0041_downgrade_fails_closed_with_artifacts(monkeypatch) -> None:
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261004_0041_m15_1_experiment_foundation.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0041", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Connection:
        @staticmethod
        def scalar(_statement):
            return 1

    monkeypatch.setattr(module.op, "get_bind", lambda: Connection())
    with pytest.raises(
        RuntimeError,
        match="cannot downgrade M15.1 while experiment artifacts exist",
    ):
        module.downgrade()
