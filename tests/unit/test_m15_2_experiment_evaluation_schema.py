import importlib.util
from pathlib import Path

import pytest
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentParameterSensitivity,
    PortfolioExperimentTrialEvaluation,
)
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint


def test_evaluation_schema_has_identity_and_composite_owners() -> None:
    report_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in PortfolioExperimentEvaluationReport.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert (
        "experiment_id",
        "evaluation_version",
        "evaluation_config_hash",
        "policy_hash",
        "source_hash",
    ) in report_uniques
    assert ("id", "experiment_id") in report_uniques

    trial_foreign_keys = {
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.target_fullname for element in constraint.elements),
        )
        for constraint in PortfolioExperimentTrialEvaluation.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert (
        ("evaluation_id", "experiment_id"),
        (
            "portfolio_experiment_evaluation_report.id",
            "portfolio_experiment_evaluation_report.experiment_id",
        ),
    ) in trial_foreign_keys
    assert (
        ("trial_id", "experiment_id"),
        ("portfolio_experiment_trial.id", "portfolio_experiment_trial.experiment_id"),
    ) in trial_foreign_keys

    sensitivity_foreign_keys = {
        tuple(element.parent.name for element in constraint.elements)
        for constraint in PortfolioExperimentParameterSensitivity.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert ("evaluation_id", "experiment_id") in sensitivity_foreign_keys


def test_migration_0042_downgrade_fails_closed_with_artifacts(monkeypatch) -> None:
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261006_0042_m15_2_experiment_evaluation.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0042", path)
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
        match="cannot downgrade M15.2 while experiment evaluation artifacts exist",
    ):
        module.downgrade()
