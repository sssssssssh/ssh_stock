import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.experiment_evaluation_config import EvaluationPolicyConfig
from app.domain.experiment.contracts import EXPERIMENT_PARAMETER_ORDER
from app.models.experiment import PortfolioExperimentTrial
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentParameterSensitivity,
    PortfolioExperimentTrialEvaluation,
)
from app.models.job import JobRun
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.performance_period import (
    PortfolioPerformancePeriod,
    PortfolioPerformancePeriodReport,
)
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun
from app.services.experiment import ExperimentApplicationService
from app.services.experiment_evaluation import (
    ExperimentEvaluationApplicationError,
    ExperimentEvaluationApplicationService,
    ExperimentEvaluationSourceError,
)
from app.services.performance.application import PerformanceApplicationService
from app.services.performance.period_application import PerformancePeriodApplicationService
from app.services.performance.risk_application import PerformanceRiskApplicationService
from app.services.performance.trade_application import PerformanceTradeApplicationService
from m14_3_support import seed_trade_case
from m14_4_support import seed_analytics_case
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

DATES = tuple(date(2056, 1, day) for day in range(2, 9))


@contextmanager
def _database():
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, expire_on_commit=False) as db:
                yield db
        finally:
            if transaction.is_active:
                transaction.rollback()
    engine.dispose()


def _experiment(db: Session, trial_count: int) -> uuid.UUID:
    created = ExperimentApplicationService(db).create(
        name="m15.2.1-integrity-closeout",
        start_date=DATES[0],
        end_date=DATES[-1],
        initial_cash=None,
        benchmark_code=None,
        grid={"candidate.min_score": [65 + index for index in range(trial_count)]},
    )
    return uuid.UUID(created["id"])


def _trials(db: Session, experiment_id: uuid.UUID) -> list[PortfolioExperimentTrial]:
    return list(
        db.scalars(
            select(PortfolioExperimentTrial)
            .where(PortfolioExperimentTrial.experiment_id == experiment_id)
            .order_by(PortfolioExperimentTrial.trial_no)
        )
    )


def _bind(db: Session, experiment_id: uuid.UUID, run_ids: list[uuid.UUID]) -> None:
    trials = _trials(db, experiment_id)
    assert len(trials) == len(run_ids)
    for trial, run_id in zip(trials, run_ids, strict=True):
        trial.run_id = run_id
    db.commit()


def _complete_case(db: Session):
    case = seed_analytics_case(db, DATES)
    period = PerformancePeriodApplicationService(db).calculate_now(
        case.run_id,
        performance_id=case.performance_id,
        risk_id=case.risk_id,
        trade_id=case.trade_id,
    )
    return case, period.report


def _run_with_status(db: Session, status: str, *, complete: bool = False) -> uuid.UUID:
    if complete:
        case, _ = _complete_case(db)
        run_id = case.run_id
    else:
        run_id = seed_trade_case(db, DATES).run_id
    run = db.get(PortfolioBacktestRun, run_id)
    assert run is not None
    run.status = status
    db.commit()
    return run_id


def _assert_readiness(
    result: dict[str, Any],
    *,
    ready: bool,
    trial: int,
    success: int,
    failed: int,
    cancelled: int,
    active: int,
    error_code: str | None,
) -> None:
    assert result["ready"] is ready
    assert result["trial_count"] == trial
    assert result["success_count"] == success
    assert result["failed_count"] == failed
    assert result["cancelled_count"] == cancelled
    assert result["active_count"] == active
    assert result["missing_analytics"] == []
    assert result.get("error_code") == error_code


def _model_values(row: Any, *, omit: set[str] | None = None) -> dict[str, Any]:
    omitted = omit or set()
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in omitted
    }


def test_readiness_terminal_state_matrix() -> None:
    with _database() as db:
        service = ExperimentEvaluationApplicationService(db)

        planned = _experiment(db, 1)
        _assert_readiness(
            service.readiness(planned),
            ready=False,
            trial=1,
            success=0,
            failed=0,
            cancelled=0,
            active=1,
            error_code="EXPERIMENT_EVALUATION_NOT_READY",
        )

        for state in ("CREATED", "RUNNING"):
            experiment_id = _experiment(db, 1)
            _bind(db, experiment_id, [_run_with_status(db, state)])
            _assert_readiness(
                service.readiness(experiment_id),
                ready=False,
                trial=1,
                success=0,
                failed=0,
                cancelled=0,
                active=1,
                error_code="EXPERIMENT_EVALUATION_NOT_READY",
            )

        no_success = _experiment(db, 2)
        _bind(
            db,
            no_success,
            [
                _run_with_status(db, "FAILED"),
                _run_with_status(db, "CANCELLED"),
            ],
        )
        _assert_readiness(
            service.readiness(no_success),
            ready=False,
            trial=2,
            success=0,
            failed=1,
            cancelled=1,
            active=0,
            error_code="EXPERIMENT_EVALUATION_NO_SUCCESSFUL_TRIAL",
        )

        mixed = _experiment(db, 3)
        _bind(
            db,
            mixed,
            [
                _run_with_status(db, "SUCCESS", complete=True),
                _run_with_status(db, "FAILED"),
                _run_with_status(db, "CANCELLED"),
            ],
        )
        _assert_readiness(
            service.readiness(mixed),
            ready=True,
            trial=3,
            success=1,
            failed=1,
            cancelled=1,
            active=0,
            error_code=None,
        )

        all_success = _experiment(db, 2)
        first, _ = _complete_case(db)
        second, _ = _complete_case(db)
        _bind(db, all_success, [first.run_id, second.run_id])
        _assert_readiness(
            service.readiness(all_success),
            ready=True,
            trial=2,
            success=2,
            failed=0,
            cancelled=0,
            active=0,
            error_code=None,
        )


@pytest.mark.parametrize("missing_stage", ["performance", "risk", "trade", "period"])
def test_missing_m14_stage_matrix(missing_stage: str) -> None:
    with _database() as db:
        case, period = _complete_case(db)
        if missing_stage == "performance":
            target = db.get(PortfolioPerformanceReport, case.performance_id)
        elif missing_stage == "risk":
            target = db.get(PortfolioPerformanceRiskReport, case.risk_id)
        elif missing_stage == "trade":
            target = db.get(PortfolioPerformanceTradeReport, case.trade_id)
        else:
            target = db.get(PortfolioPerformancePeriodReport, period.id)
        assert target is not None
        db.delete(target)
        db.commit()

        experiment_id = _experiment(db, 1)
        _bind(db, experiment_id, [case.run_id])
        report_count = db.scalar(
            select(func.count()).select_from(PortfolioExperimentEvaluationReport)
        )
        job_count = db.scalar(
            select(func.count())
            .select_from(JobRun)
            .where(JobRun.job_type.like("portfolio_performance%"))
        )
        service = ExperimentEvaluationApplicationService(db)

        readiness = service.readiness(experiment_id)
        assert readiness["ready"] is False
        assert readiness["error_code"] == "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPLETE"
        assert readiness["missing_analytics"] == [
            {
                "trial_id": str(_trials(db, experiment_id)[0].id),
                "trial_no": 1,
                "run_id": str(case.run_id),
                "missing_stage": missing_stage,
            }
        ]
        for operation in (
            lambda: service.calculate_now(experiment_id),
            lambda: service.queue_calculation(experiment_id),
        ):
            with pytest.raises(
                (ExperimentEvaluationApplicationError, ExperimentEvaluationSourceError)
            ) as error:
                operation()
            assert error.value.code == "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPLETE"
            assert error.value.details["missing_analytics"][0]["missing_stage"] == missing_stage

        assert db.scalar(
            select(func.count()).select_from(PortfolioExperimentEvaluationReport)
        ) == report_count
        assert db.scalar(
            select(func.count()).select_from(PortfolioExperimentTrialEvaluation)
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(PortfolioExperimentParameterSensitivity)
        ) == 0
        assert db.scalar(
            select(func.count())
            .select_from(JobRun)
            .where(JobRun.job_type.like("portfolio_performance%"))
        ) == job_count


@pytest.mark.parametrize(
    "mismatch_field",
    [
        "performance_config_hash",
        "trade_date_set",
        "risk_config_hash",
        "benchmark_code",
        "trade_config_hash",
        "period_config_hash",
        "month_period_key_set",
        "year_period_key_set",
    ],
)
def test_analytics_compatibility_matrix(mismatch_field: str) -> None:
    with _database() as db:
        first, _ = _complete_case(db)
        second, second_period = _complete_case(db)
        experiment_id = _experiment(db, 2)
        _bind(db, experiment_id, [first.run_id, second.run_id])

        if mismatch_field == "performance_config_hash":
            row = db.get(PortfolioPerformanceReport, second.performance_id)
            assert row is not None
            row.performance_config_hash = "f" * 64
        elif mismatch_field == "trade_date_set":
            rows = list(
                db.scalars(
                    select(PortfolioPerformanceDaily)
                    .where(PortfolioPerformanceDaily.performance_id == second.performance_id)
                    .order_by(PortfolioPerformanceDaily.trade_date)
                )
            )
            old = rows[-1]
            replacement = PortfolioPerformanceDaily(
                **{
                    **_model_values(old, omit={"created_at"}),
                    "trade_date": date(2056, 1, 31),
                }
            )
            db.delete(old)
            db.flush()
            db.add(replacement)
        elif mismatch_field in {"risk_config_hash", "benchmark_code"}:
            row = db.get(PortfolioPerformanceRiskReport, second.risk_id)
            assert row is not None
            setattr(
                row,
                mismatch_field,
                "r" * 64 if mismatch_field == "risk_config_hash" else "000905.SH",
            )
        elif mismatch_field == "trade_config_hash":
            row = db.get(PortfolioPerformanceTradeReport, second.trade_id)
            assert row is not None
            row.trade_config_hash = "t" * 64
        elif mismatch_field == "period_config_hash":
            row = db.get(PortfolioPerformancePeriodReport, second_period.id)
            assert row is not None
            row.period_config_hash = "p" * 64
        else:
            period_type = "MONTH" if mismatch_field.startswith("month") else "YEAR"
            row = db.scalar(
                select(PortfolioPerformancePeriod).where(
                    PortfolioPerformancePeriod.period_id == second_period.id,
                    PortfolioPerformancePeriod.period_type == period_type,
                )
            )
            assert row is not None
            values = _model_values(row, omit={"created_at"})
            values["period_key"] = "2056-02" if period_type == "MONTH" else "2057"
            db.delete(row)
            db.flush()
            db.add(PortfolioPerformancePeriod(**values))
        db.commit()

        service = ExperimentEvaluationApplicationService(db)
        readiness = service.readiness(experiment_id)
        assert readiness["ready"] is False
        assert readiness["error_code"] == "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPATIBLE"
        assert readiness["mismatch_fields"] == [mismatch_field]
        with pytest.raises(ExperimentEvaluationApplicationError) as error:
            service.calculate_now(experiment_id)
        assert error.value.code == "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPATIBLE"
        assert error.value.details["mismatch_fields"] == [mismatch_field]
        assert db.scalar(
            select(func.count()).select_from(PortfolioExperimentEvaluationReport)
        ) == 0


def test_policy_change_creates_new_immutable_evaluation_artifact() -> None:
    with _database() as db:
        first, _ = _complete_case(db)
        second, _ = _complete_case(db)
        experiment_id = _experiment(db, 2)
        _bind(db, experiment_id, [first.run_id, second.run_id])
        service = ExperimentEvaluationApplicationService(db)

        evaluation_a = service.calculate_now(experiment_id)
        detail_a = service.detail(experiment_id, evaluation_a.report.id)
        trials_a, _ = service.trials(
            experiment_id,
            evaluation_a.report.id,
            status=None,
            feasible=None,
            shortlisted=None,
            pareto_front=None,
            limit=200,
            offset=0,
        )
        sensitivity_a = service.sensitivity(experiment_id, evaluation_a.report.id, None)
        default = get_settings().experiment_evaluation_config.default_policy
        policy_b = EvaluationPolicyConfig.model_validate(
            {**default.model_dump(mode="python"), "shortlist_size": 1}
        )
        evaluation_b = service.calculate_now(experiment_id, policy_b)
        reused_b = service.calculate_now(experiment_id, policy_b)

        assert evaluation_a.report.policy_hash != evaluation_b.report.policy_hash
        assert evaluation_a.report.source_hash == evaluation_b.report.source_hash
        assert evaluation_a.report.id != evaluation_b.report.id
        assert reused_b.reused is True
        assert reused_b.report.id == evaluation_b.report.id
        assert service.detail(experiment_id, evaluation_a.report.id) == detail_a
        assert service.trials(
            experiment_id,
            evaluation_a.report.id,
            status=None,
            feasible=None,
            shortlisted=None,
            pareto_front=None,
            limit=200,
            offset=0,
        )[0] == trials_a
        assert service.sensitivity(experiment_id, evaluation_a.report.id, None) == sensitivity_a
        assert service.detail(experiment_id, evaluation_b.report.id)["identity"] == {
            "evaluation_id": str(evaluation_b.report.id),
            "experiment_id": str(experiment_id),
            "evaluation_version": "experiment_eval_v1",
            "evaluation_config_hash": evaluation_b.report.evaluation_config_hash,
            "policy_hash": evaluation_b.report.policy_hash,
            "source_hash": evaluation_b.report.source_hash,
        }


def test_m14_generation_change_creates_new_evaluation_artifact() -> None:
    with _database() as db:
        case, _ = _complete_case(db)
        experiment_id = _experiment(db, 1)
        _bind(db, experiment_id, [case.run_id])
        evaluation_service = ExperimentEvaluationApplicationService(db)
        evaluation_a = evaluation_service.calculate_now(experiment_id)
        trial_a = db.get(
            PortfolioExperimentTrialEvaluation,
            (evaluation_a.report.id, _trials(db, experiment_id)[0].id),
        )
        assert trial_a is not None
        generation_a_ids = (
            trial_a.performance_id,
            trial_a.risk_id,
            trial_a.trade_id,
            trial_a.period_id,
        )

        settings = get_settings()
        performance_config = settings.performance_config.model_copy(
            update={
                "annualization_trade_days": (
                    settings.performance_config.annualization_trade_days + 1
                )
            }
        )
        generation_settings = settings.model_copy(
            update={"performance_config": performance_config}
        )
        performance_b = PerformanceApplicationService(
            db, settings=generation_settings
        ).calculate_now(case.run_id)
        performance_a = db.get(PortfolioPerformanceReport, generation_a_ids[0])
        assert performance_a is not None
        performance_b.report.calculated_at = performance_a.calculated_at + timedelta(
            seconds=1
        )
        db.commit()
        risk_b = PerformanceRiskApplicationService(db).calculate_now(
            case.run_id, performance_b.report.id
        )
        trade_b = PerformanceTradeApplicationService(db).calculate_now(
            case.run_id, performance_b.report.id
        )
        period_b = PerformancePeriodApplicationService(db).calculate_now(
            case.run_id,
            performance_id=performance_b.report.id,
            risk_id=risk_b.report.id,
            trade_id=trade_b.report.id,
        )
        generation_b_ids = (
            performance_b.report.id,
            risk_b.report.id,
            trade_b.report.id,
            period_b.report.id,
        )
        assert generation_b_ids != generation_a_ids

        evaluation_b = evaluation_service.calculate_now(experiment_id)
        trial_b = db.get(
            PortfolioExperimentTrialEvaluation,
            (evaluation_b.report.id, _trials(db, experiment_id)[0].id),
        )
        assert trial_b is not None
        assert evaluation_a.report.policy_hash == evaluation_b.report.policy_hash
        assert evaluation_a.report.source_hash != evaluation_b.report.source_hash
        assert evaluation_a.report.id != evaluation_b.report.id
        assert (
            trial_b.performance_id,
            trial_b.risk_id,
            trial_b.trade_id,
            trial_b.period_id,
        ) == generation_b_ids
        db.expire_all()
        immutable_a = db.get(
            PortfolioExperimentTrialEvaluation,
            (evaluation_a.report.id, _trials(db, experiment_id)[0].id),
        )
        assert immutable_a is not None
        assert (
            immutable_a.performance_id,
            immutable_a.risk_id,
            immutable_a.trade_id,
            immutable_a.period_id,
        ) == generation_a_ids


def test_postgres_rejects_cross_experiment_trial_evaluation() -> None:
    with _database() as db:
        first, _ = _complete_case(db)
        second, _ = _complete_case(db)
        experiment_a = _experiment(db, 1)
        experiment_b = _experiment(db, 1)
        _bind(db, experiment_a, [first.run_id])
        _bind(db, experiment_b, [second.run_id])
        report = ExperimentEvaluationApplicationService(db).calculate_now(
            experiment_a
        ).report
        source = db.get(
            PortfolioExperimentTrialEvaluation,
            (report.id, _trials(db, experiment_a)[0].id),
        )
        foreign_trial = _trials(db, experiment_b)[0]
        assert source is not None
        values = _model_values(source, omit={"created_at"})
        values.update(
            trial_id=foreign_trial.id,
            trial_no=foreign_trial.trial_no,
            run_id=foreign_trial.run_id,
            parameter_hash=foreign_trial.parameter_hash,
            parameter_values=foreign_trial.parameter_values,
        )
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(PortfolioExperimentTrialEvaluation(**values))
                db.flush()


def _replace_trial_row_and_expect_integrity_error(
    db: Session,
    evaluation_id: uuid.UUID,
    trial_id: uuid.UUID,
    **updates: Any,
) -> None:
    current = db.get(PortfolioExperimentTrialEvaluation, (evaluation_id, trial_id))
    assert current is not None
    values = _model_values(current, omit={"created_at"})
    values.update(updates)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.delete(current)
            db.flush()
            db.add(PortfolioExperimentTrialEvaluation(**values))
            db.flush()
    db.expire_all()


def test_postgres_rejects_invalid_excluded_and_shortlist_rows() -> None:
    with _database() as db:
        case, _ = _complete_case(db)
        experiment_id = _experiment(db, 1)
        _bind(db, experiment_id, [case.run_id])
        report = ExperimentEvaluationApplicationService(db).calculate_now(
            experiment_id
        ).report
        trial_id = _trials(db, experiment_id)[0].id

        _replace_trial_row_and_expect_integrity_error(
            db,
            report.id,
            trial_id,
            status="EXCLUDED",
            feasible=False,
            shortlisted=False,
            selection_rank=1,
            pareto_front=None,
        )
        _replace_trial_row_and_expect_integrity_error(
            db,
            report.id,
            trial_id,
            status="EXCLUDED",
            feasible=False,
            shortlisted=False,
            selection_rank=None,
            pareto_front=1,
        )
        _replace_trial_row_and_expect_integrity_error(
            db,
            report.id,
            trial_id,
            status="EVALUATED",
            feasible=False,
            shortlisted=True,
            selection_rank=1,
            pareto_front=1,
        )


def test_postgres_rejects_duplicate_trial_and_sensitivity_rows() -> None:
    with _database() as db:
        case, _ = _complete_case(db)
        experiment_id = _experiment(db, 1)
        _bind(db, experiment_id, [case.run_id])
        report = ExperimentEvaluationApplicationService(db).calculate_now(
            experiment_id
        ).report
        trial = db.get(
            PortfolioExperimentTrialEvaluation,
            (report.id, _trials(db, experiment_id)[0].id),
        )
        sensitivity = db.scalar(
            select(PortfolioExperimentParameterSensitivity).where(
                PortfolioExperimentParameterSensitivity.evaluation_id == report.id
            )
        )
        assert trial is not None and sensitivity is not None
        for table, values in (
            (
                PortfolioExperimentTrialEvaluation.__table__,
                _model_values(trial, omit={"created_at"}),
            ),
            (
                PortfolioExperimentParameterSensitivity.__table__,
                _model_values(sensitivity, omit={"created_at"}),
            ),
        ):
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(sa.insert(table).values(**values))
                    db.flush()

        report_values = _model_values(report, omit={"created_at", "updated_at"})
        report_values.update(
            id=uuid.uuid4(),
            source_hash=uuid.uuid4().hex * 2,
            trial_count=2,
            success_trial_count=1,
            evaluated_trial_count=1,
            excluded_trial_count=0,
        )
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(PortfolioExperimentEvaluationReport(**report_values))
                db.flush()


def test_partial_experiment_excludes_failed_cancelled_from_selection() -> None:
    with _database() as db:
        first, _ = _complete_case(db)
        second, _ = _complete_case(db)
        failed = _run_with_status(db, "FAILED")
        cancelled = _run_with_status(db, "CANCELLED")
        experiment_id = _experiment(db, 4)
        _bind(db, experiment_id, [first.run_id, second.run_id, failed, cancelled])

        service = ExperimentEvaluationApplicationService(db)
        artifact = service.calculate_now(experiment_id)
        report = artifact.report
        assert report.trial_count == 4
        assert report.success_trial_count == 2
        assert report.evaluated_trial_count == 2
        assert report.excluded_trial_count == 2
        rows, meta = service.trials(
            experiment_id,
            report.id,
            status=None,
            feasible=None,
            shortlisted=None,
            pareto_front=None,
            limit=200,
            offset=0,
        )
        assert meta["total"] == 4
        by_no = {row["trial_no"]: row for row in rows}
        assert by_no[1]["status"] == "EVALUATED"
        assert by_no[2]["status"] == "EVALUATED"
        assert by_no[3]["status"] == "EXCLUDED"
        assert by_no[3]["exclusion_reason"] == "RUN_FAILED"
        assert by_no[4]["status"] == "EXCLUDED"
        assert by_no[4]["exclusion_reason"] == "RUN_CANCELLED"
        persisted = list(
            db.scalars(
                select(PortfolioExperimentTrialEvaluation).where(
                    PortfolioExperimentTrialEvaluation.evaluation_id == report.id
                )
            )
        )
        excluded = [row for row in persisted if row.status == "EXCLUDED"]
        assert len(excluded) == 2
        for row in excluded:
            assert row.performance_id is None
            assert row.risk_id is None
            assert row.trade_id is None
            assert row.period_id is None
            assert row.feasible is False
            assert row.pareto_front is None
            assert row.selection_rank is None
            assert row.shortlisted is False
        assert all(row.status == "EVALUATED" for row in persisted if row.pareto_front)
        assert all(row.status == "EVALUATED" for row in persisted if row.selection_rank)
        sensitivity = service.sensitivity(experiment_id, report.id, None)
        for parameter_name in EXPERIMENT_PARAMETER_ORDER:
            parameter_rows = [
                row for row in sensitivity if row["parameter_name"] == parameter_name
            ]
            assert sum(row["trial_count"] for row in parameter_rows) == 4
            assert sum(row["evaluated_count"] for row in parameter_rows) == 2
        assert "EXPERIMENT_CONTAINS_FAILED_TRIALS" in report.warnings
        assert "EXPERIMENT_CONTAINS_CANCELLED_TRIALS" in report.warnings


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        ("key_set", "trial parameter set is incomplete"),
        ("hash", "trial parameter hash mismatch"),
    ],
)
def test_trial_parameter_identity_tampering_fails_closed(
    tamper: str, reason: str
) -> None:
    with _database() as db:
        case, _ = _complete_case(db)
        experiment_id = _experiment(db, 1)
        _bind(db, experiment_id, [case.run_id])
        trial = _trials(db, experiment_id)[0]
        if tamper == "key_set":
            values = dict(trial.parameter_values)
            values.pop(EXPERIMENT_PARAMETER_ORDER[-1])
            trial.parameter_values = values
        else:
            trial.parameter_hash = "0" * 64
        db.commit()

        service = ExperimentEvaluationApplicationService(db)
        readiness = service.readiness(experiment_id)
        assert readiness["ready"] is False
        assert readiness["error_code"] == "EXPERIMENT_EVALUATION_SOURCE_INVALID"
        assert readiness["reason"] == reason
        with pytest.raises(ExperimentEvaluationApplicationError) as error:
            service.calculate_now(experiment_id)
        assert error.value.code == "EXPERIMENT_EVALUATION_SOURCE_INVALID"
        assert error.value.details["reason"] == reason
        assert db.scalar(
            select(func.count()).select_from(PortfolioExperimentEvaluationReport)
        ) == 0
