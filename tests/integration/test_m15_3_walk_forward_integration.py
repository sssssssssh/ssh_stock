import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentTrialEvaluation,
)
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.models.performance import PortfolioPerformanceDaily
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import (
    PortfolioWalkForwardParameterStability,
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardValidationReport,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)
from app.services.experiment_evaluation import ExperimentEvaluationApplicationService
from app.services.performance.period_application import PerformancePeriodApplicationService
from app.services.walk_forward import (
    WalkForwardApplicationError,
    WalkForwardApplicationService,
)
from m14_4_support import seed_analytics_case
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session


def _calendar_dates() -> tuple[date, ...]:
    start = date(2081, 1, 2)
    return tuple(start + timedelta(days=index) for index in range(7))


def _seed_calendar(db: Session) -> tuple[date, ...]:
    dates = _calendar_dates()
    for index, value in enumerate(dates):
        db.add(
            TradeCalendar(
                cal_date=value,
                is_open=index != 3,
                exchange="SSE",
            )
        )
    db.flush()
    return tuple(value for index, value in enumerate(dates) if index != 3)


def test_study_freeze_and_bounded_advance_create_each_train_once() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            open_dates = _seed_calendar(db)
            service = WalkForwardApplicationService(db)
            created = service.create(
                name="m15.3-integration",
                start_date=_calendar_dates()[0],
                end_date=_calendar_dates()[-1],
                mode="ROLLING",
                train_trade_days=2,
                test_trade_days=2,
                step_trade_days=2,
                initial_cash=Decimal("1200000"),
                benchmark_code="000300.SH",
                grid={},
                train_evaluation_policy=None,
            )
            study_id = uuid.UUID(created["id"])
            assert created["window_count"] == 2
            assert created["unused_tail_trade_days"] == 0
            windows = db.scalars(
                sa.select(PortfolioWalkForwardWindow)
                .where(PortfolioWalkForwardWindow.study_id == study_id)
                .order_by(PortfolioWalkForwardWindow.window_no)
            ).all()
            assert [tuple(row.train_trade_dates) for row in windows] == [
                tuple(day.isoformat() for day in open_dates[0:2]),
                tuple(day.isoformat() for day in open_dates[2:4]),
            ]
            assert [tuple(row.test_trade_dates) for row in windows] == [
                tuple(day.isoformat() for day in open_dates[2:4]),
                tuple(day.isoformat() for day in open_dates[4:6]),
            ]

            drifted = get_settings().model_copy(deep=True)
            assert drifted.portfolio_config is not None
            drifted.portfolio_config = drifted.portfolio_config.model_copy(
                update={"initial_cash_cny": Decimal("9999999")}
            )
            progressed = WalkForwardApplicationService(db, settings=drifted).advance(
                study_id
            )
            assert [row["action"] for row in progressed["actions_performed"]] == [
                "CREATE_TRAIN_EXPERIMENT",
                "START_TRAIN_EXPERIMENT",
                "CREATE_TRAIN_EXPERIMENT",
                "START_TRAIN_EXPERIMENT",
            ]
            repeated = WalkForwardApplicationService(db, settings=drifted).advance(
                study_id
            )
            assert repeated["actions_performed"] == []

            experiments = db.scalars(
                sa.select(PortfolioExperiment).join(
                    PortfolioWalkForwardWindow,
                    PortfolioWalkForwardWindow.train_experiment_id
                    == PortfolioExperiment.id,
                )
            ).all()
            study = db.get(PortfolioWalkForwardStudy, study_id)
            assert study is not None
            assert len(experiments) == 2
            assert all(row.initial_cash == Decimal("1200000") for row in experiments)
            assert all(
                row.base_config_snapshot == study.base_config_snapshot
                for row in experiments
            )
            trials = db.scalars(
                sa.select(PortfolioExperimentTrial).where(
                    PortfolioExperimentTrial.experiment_id.in_(
                        [row.id for row in experiments]
                    )
                )
            ).all()
            assert len(trials) == 2
            run_ids = [row.run_id for row in trials]
            assert None not in run_ids
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(JobRun)
                .where(
                    JobRun.job_metadata["portfolio_run_id"].astext.in_(
                        [str(run_id) for run_id in run_ids]
                    )
                )
            ) == 2
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(PortfolioBacktestRun)
                .where(PortfolioBacktestRun.id.in_(run_ids))
            ) == 2
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(JobRun)
                .where(JobRun.job_type.like("portfolio_performance%"))
            ) == 0

            with pytest.raises(WalkForwardApplicationError) as not_ready:
                service.queue_validation(study_id)
            assert not_ready.value.code == "WALK_FORWARD_VALIDATION_NOT_READY"
        transaction.rollback()
    engine.dispose()


def test_window_partial_binding_is_rejected_by_postgresql() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            _seed_calendar(db)
            created = WalkForwardApplicationService(db).create(
                name="m15.3-integrity",
                start_date=_calendar_dates()[0],
                end_date=_calendar_dates()[-1],
                mode="EXPANDING",
                train_trade_days=2,
                test_trade_days=2,
                step_trade_days=2,
                initial_cash=None,
                benchmark_code=None,
                grid={},
                train_evaluation_policy=None,
            )
            study_id = uuid.UUID(created["id"])
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(
                        sa.update(PortfolioWalkForwardWindow)
                        .where(
                            PortfolioWalkForwardWindow.study_id == study_id,
                            PortfolioWalkForwardWindow.window_no == 1,
                        )
                        .values(selected_parameter_hash="x" * 64)
                    )
                    db.flush()
            assert db.get(PortfolioWalkForwardStudy, study_id) is not None
        transaction.rollback()
    engine.dispose()


def _complete_bundle(db: Session, dates: tuple[date, ...]):
    case = seed_analytics_case(db, dates)
    period = PerformancePeriodApplicationService(db).calculate_now(
        case.run_id,
        performance_id=case.performance_id,
        risk_id=case.risk_id,
        trade_id=case.trade_id,
    ).report
    return case, period


def _align_run_snapshot(
    db: Session,
    run_id: uuid.UUID,
    experiment: PortfolioExperiment,
    trial: PortfolioExperimentTrial,
) -> PortfolioBacktestRun:
    run = db.get(PortfolioBacktestRun, run_id)
    assert run is not None
    run.config_snapshot = {
        "strategy": experiment.base_config_snapshot["strategy"],
        "opportunity": experiment.base_config_snapshot["opportunity"],
        "portfolio": trial.portfolio_config_snapshot,
        "execution": experiment.base_config_snapshot["execution"],
        "accounting": experiment.base_config_snapshot["accounting"],
    }
    return run


def test_complete_pinned_source_validation_job_persists_and_reuses_artifact() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            dates = tuple(date(2082, 1, 2) + timedelta(days=index) for index in range(21))
            for value in dates:
                db.add(TradeCalendar(cal_date=value, is_open=True, exchange="SSE"))
            db.flush()
            service = WalkForwardApplicationService(db)
            created = service.create(
                name="m15.3-validation",
                start_date=dates[0],
                end_date=dates[-1],
                mode="ROLLING",
                train_trade_days=7,
                test_trade_days=7,
                step_trade_days=7,
                initial_cash=None,
                benchmark_code=None,
                grid={},
                train_evaluation_policy=None,
            )
            study_id = uuid.UUID(created["id"])
            study = db.get(PortfolioWalkForwardStudy, study_id)
            assert study is not None
            windows = list(
                db.scalars(
                    sa.select(PortfolioWalkForwardWindow)
                    .where(PortfolioWalkForwardWindow.study_id == study_id)
                    .order_by(PortfolioWalkForwardWindow.window_no)
                )
            )
            assert len(windows) == 2

            for window in windows:
                train_dates = tuple(
                    date.fromisoformat(value) for value in window.train_trade_dates
                )
                train_case, _ = _complete_bundle(db, train_dates)
                experiment = service._frozen_experiment_service(
                    study
                ).create_from_frozen_base(
                    name=f"train-{window.window_no}",
                    start_date=window.train_start_date,
                    end_date=window.train_end_date,
                    grid=study.parameter_space,
                    base_config_snapshot=study.base_config_snapshot,
                    base_identities={
                        name: getattr(study, name)
                        for name in (
                            "base_algo_version",
                            "base_source_strategy_config_hash",
                            "base_opportunity_calc_version",
                            "base_opportunity_config_hash",
                            "base_portfolio_version",
                            "base_portfolio_config_hash",
                            "base_execution_version",
                            "base_execution_config_hash",
                            "base_accounting_version",
                            "base_accounting_config_hash",
                            "base_backtest_engine_version",
                        )
                    },
                    commit=False,
                )
                window.train_experiment_id = experiment.id
                db.flush()
                trial = db.scalar(
                    sa.select(PortfolioExperimentTrial).where(
                        PortfolioExperimentTrial.experiment_id == experiment.id
                    )
                )
                assert trial is not None
                trial.run_id = train_case.run_id
                _align_run_snapshot(db, train_case.run_id, experiment, trial)
                db.commit()

                evaluation = ExperimentEvaluationApplicationService(db).calculate_now(
                    experiment.id
                ).report
                assert evaluation.selected_trial_id == trial.id
                service._freeze_selection(window, experiment, evaluation)

                test_dates = tuple(
                    date.fromisoformat(value) for value in window.test_trade_dates
                )
                oos_case, period = _complete_bundle(db, test_dates)
                _align_run_snapshot(db, oos_case.run_id, experiment, trial)
                window.oos_run_id = oos_case.run_id
                db.flush()
                bundle = service.bundle_resolver.resolve(
                    oos_case.run_id,
                    performance_id=oos_case.performance_id,
                    risk_id=oos_case.risk_id,
                    trade_id=oos_case.trade_id,
                    period_id=period.id,
                    require_period=True,
                )
                service._pin_oos_bundle(window, bundle)
                db.commit()

            readiness = service.validation_readiness(study_id)
            assert readiness["ready"] is True
            assert readiness["window_count"] == 2

            first_evaluation = db.scalar(
                sa.select(PortfolioExperimentTrialEvaluation).where(
                    PortfolioExperimentTrialEvaluation.evaluation_id
                    == windows[0].train_evaluation_id,
                    PortfolioExperimentTrialEvaluation.trial_id
                    == windows[0].selected_trial_id,
                )
            )
            assert first_evaluation is not None
            assert first_evaluation.performance_id is not None
            train_daily = db.scalar(
                sa.select(PortfolioPerformanceDaily)
                .where(
                    PortfolioPerformanceDaily.performance_id
                    == first_evaluation.performance_id
                )
                .order_by(PortfolioPerformanceDaily.trade_date)
                .offset(1)
                .limit(1)
            )
            assert train_daily is not None
            nested = db.begin_nested()
            db.delete(train_daily)
            db.flush()
            drifted_readiness = service.validation_readiness(study_id)
            assert drifted_readiness["ready"] is False
            assert (
                drifted_readiness["error_code"]
                == "WALK_FORWARD_TRAIN_DATE_SET_MISMATCH"
            )
            assert drifted_readiness["window_no"] == windows[0].window_no
            assert drifted_readiness["scope"] == "TRAIN"
            assert drifted_readiness["missing_stage"] == "date_set"
            nested.rollback()
            db.expire_all()

            job = service.queue_validation(study_id)
            job.status = "RUNNING"
            job.worker_id = "m15.3-test-worker"
            db.commit()
            report, reused = service.run_validation_job(job.id)
            assert reused is False
            assert report.window_count == 2
            assert report.total_oos_trade_days == 14
            assert report.policy_identity_version == "policy_v1"
            assert report.validation_policy_hash != report.walk_forward_config_hash
            assert report.transition_count == 1
            assert report.switch_count == 0
            assert report.switch_rate == Decimal("0")
            assert report.result_summary["semantics"] == (
                "time-separated out-of-sample validation evidence for research use"
            )
            repeated, reused = service.calculate_now(study_id)
            assert reused is True
            assert repeated.id == report.id
            assert db.scalar(
                sa.select(sa.func.count()).select_from(
                    PortfolioWalkForwardValidationReport
                )
            ) == 1
            assert db.scalar(
                sa.select(sa.func.count()).select_from(
                    PortfolioWalkForwardWindowValidation
                )
            ) == 2
            validation_windows = list(
                db.scalars(
                    sa.select(PortfolioWalkForwardWindowValidation)
                    .where(
                        PortfolioWalkForwardWindowValidation.validation_id
                        == report.id
                    )
                    .order_by(PortfolioWalkForwardWindowValidation.window_no)
                )
            )
            assert len(validation_windows) == 2
            assert validation_windows[0].identity_snapshot["schema_version"] == (
                "walk_forward_window_validation_identity_v1"
            )
            assert validation_windows[0].train_date_hash == windows[0].train_date_hash
            assert validation_windows[0].test_date_hash == windows[0].test_date_hash
            assert validation_windows[0].selected_train_run_id == (
                first_evaluation.run_id
            )
            assert db.scalar(
                sa.select(sa.func.count()).select_from(
                    PortfolioWalkForwardParameterStability
                )
            ) == 6
            assert db.scalar(
                sa.select(sa.func.count()).select_from(
                    PortfolioExperimentEvaluationReport
                )
            ) == 2

            def rejected(statement) -> None:
                with pytest.raises(IntegrityError):
                    with db.begin_nested():
                        db.execute(statement)
                        db.flush()

            def clone_insert(model, row, **overrides):
                excluded = {"created_at", "updated_at", "calculated_at"}
                values = {
                    column.name: getattr(row, column.name)
                    for column in model.__table__.columns
                    if column.name not in excluded
                }
                values.update(overrides)
                return sa.insert(model).values(**values)

            first, second = windows
            rejected(clone_insert(PortfolioWalkForwardWindow, first))
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == second.window_no,
                )
                .values(train_experiment_id=first.train_experiment_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == second.window_no,
                )
                .values(oos_run_id=first.oos_run_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == first.window_no,
                )
                .values(train_evaluation_id=second.train_evaluation_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == first.window_no,
                )
                .values(selected_trial_id=second.selected_trial_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == first.window_no,
                )
                .values(oos_performance_id=second.oos_performance_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == first.window_no,
                )
                .values(oos_risk_id=second.oos_risk_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == first.window_no,
                )
                .values(oos_trade_id=second.oos_trade_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == first.window_no,
                )
                .values(oos_period_id=second.oos_period_id)
                .execution_options(synchronize_session=False)
            )
            rejected(
                sa.update(PortfolioWalkForwardWindow)
                .where(
                    PortfolioWalkForwardWindow.study_id == study_id,
                    PortfolioWalkForwardWindow.window_no == first.window_no,
                )
                .values(oos_risk_id=None)
                .execution_options(synchronize_session=False)
            )
            rejected(
                clone_insert(
                    PortfolioWalkForwardValidationReport,
                    report,
                    id=uuid.uuid4(),
                )
            )
            stability_row = db.scalar(
                sa.select(PortfolioWalkForwardParameterStability).limit(1)
            )
            assert stability_row is not None
            rejected(
                clone_insert(PortfolioWalkForwardParameterStability, stability_row)
            )

            for statement in (
                sa.update(PortfolioWalkForwardValidationReport)
                .where(PortfolioWalkForwardValidationReport.id == report.id)
                .values(switch_count=1),
                sa.update(PortfolioWalkForwardWindowValidation)
                .where(
                    PortfolioWalkForwardWindowValidation.validation_id == report.id,
                    PortfolioWalkForwardWindowValidation.window_no == 1,
                )
                .values(selected_parameter_hash="z" * 64),
                sa.delete(PortfolioWalkForwardParameterStability).where(
                    PortfolioWalkForwardParameterStability.validation_id == report.id
                ),
            ):
                with pytest.raises(DBAPIError):
                    with db.begin_nested():
                        db.execute(statement)
                        db.flush()

            cross_owner_report_id = uuid.uuid4()
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(
                        clone_insert(
                            PortfolioWalkForwardValidationReport,
                            report,
                            id=cross_owner_report_id,
                            source_hash="z" * 64,
                        )
                    )
                    db.execute(
                        clone_insert(
                            PortfolioWalkForwardWindowValidation,
                            validation_windows[0],
                            validation_id=cross_owner_report_id,
                            selected_train_run_id=(
                                validation_windows[1].selected_train_run_id
                            ),
                        )
                    )
                    db.flush()

            db.expire(report)
            round_tripped = db.get(PortfolioWalkForwardValidationReport, report.id)
            assert round_tripped is not None
            assert abs(
                round_tripped.stitched_oos_annualized_return
                - report.stitched_oos_annualized_return
            ) <= Decimal("1e-18")
        transaction.rollback()
    engine.dispose()
