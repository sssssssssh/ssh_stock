import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.experiment_evaluation_config import EvaluationPolicyConfig
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentParameterSensitivity,
    PortfolioExperimentTrialEvaluation,
)
from app.models.job import JobRun
from app.models.market_data import IndexDaily, TradeCalendar
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.portfolio import PortfolioBacktestRun
from app.services.experiment import ExperimentApplicationService
from app.services.experiment_evaluation import (
    ExperimentEvaluationApplicationError,
    ExperimentEvaluationApplicationService,
    ExperimentEvaluationConflictError,
)
from app.services.experiment_evaluation.recovery import (
    recover_stale_experiment_evaluation_jobs,
)
from app.services.performance.period_application import PerformancePeriodApplicationService
from m14_3_support import seed_trade_case
from m14_4_support import seed_analytics_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session

DATES = tuple(date(2055, 1, day) for day in range(2, 9))
FENCING_DATES = tuple(date(2055, 2, day) for day in range(2, 9))


def _experiment(db: Session, trial_count: int) -> uuid.UUID:
    created = ExperimentApplicationService(db).create(
        name="m15.2-evaluation",
        start_date=DATES[0],
        end_date=DATES[-1],
        initial_cash=None,
        benchmark_code=None,
        grid={"candidate.min_score": [65 + index for index in range(trial_count)]},
    )
    return uuid.UUID(created["id"])


def _complete_case(db: Session):
    case = seed_analytics_case(db, DATES)
    period = PerformancePeriodApplicationService(db).calculate_now(
        case.run_id,
        performance_id=case.performance_id,
        risk_id=case.risk_id,
        trade_id=case.trade_id,
    )
    return case, period


def _bind(db: Session, experiment_id: uuid.UUID, run_ids: list[uuid.UUID]) -> None:
    trials = list(
        db.scalars(
            select(PortfolioExperimentTrial)
            .where(PortfolioExperimentTrial.experiment_id == experiment_id)
            .order_by(PortfolioExperimentTrial.trial_no)
        )
    )
    assert len(trials) == len(run_ids)
    for trial, run_id in zip(trials, run_ids, strict=True):
        trial.run_id = run_id
    db.commit()


def test_complete_evaluation_persists_reuses_and_exposes_detail_pages() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            first, _ = _complete_case(db)
            second, _ = _complete_case(db)
            experiment_id = _experiment(db, 2)
            _bind(db, experiment_id, [first.run_id, second.run_id])

            service = ExperimentEvaluationApplicationService(db)
            readiness = service.readiness(experiment_id)
            assert readiness["ready"] is True
            first_artifact = service.calculate_now(experiment_id)
            second_artifact = service.calculate_now(experiment_id)
            assert first_artifact.reused is False
            assert second_artifact.reused is True
            assert second_artifact.report.id == first_artifact.report.id
            assert first_artifact.report.trial_count == 2
            assert first_artifact.report.evaluated_trial_count == 2
            assert first_artifact.report.excluded_trial_count == 0
            assert first_artifact.report.selected_trial_id is not None

            detail = service.detail(experiment_id, first_artifact.report.id)
            assert detail["result_summary"]["selection_semantics"] == (
                "in_sample_research_candidate"
            )
            assert detail["shortlist"]
            rows, meta = service.trials(
                experiment_id,
                first_artifact.report.id,
                status="EVALUATED",
                feasible=True,
                shortlisted=None,
                pareto_front=None,
                limit=1,
                offset=0,
            )
            assert len(rows) == 1
            assert meta["total"] == 2
            sensitivity = service.sensitivity(
                experiment_id, first_artifact.report.id, None
            )
            assert {row["parameter_name"] for row in sensitivity} == {
                "candidate.min_score",
                "candidate.top_n",
                "construction.max_positions",
                "construction.max_single_position_weight",
                "construction.min_cash_ratio",
                "construction.max_new_positions_per_day",
            }
            history, total = service.history(experiment_id, limit=10, offset=0)
            assert total == 1
            assert history[0]["id"] == str(first_artifact.report.id)
            assert db.scalar(
                select(func.count()).select_from(PortfolioExperimentTrialEvaluation)
            ) == 2
            assert db.scalar(
                select(func.count()).select_from(
                    PortfolioExperimentParameterSensitivity
                )
            ) == 7
        transaction.rollback()
    engine.dispose()


def test_missing_analytics_and_incompatible_bundles_fail_closed() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            incomplete = seed_trade_case(db, DATES)
            incomplete_experiment = _experiment(db, 1)
            _bind(db, incomplete_experiment, [incomplete.run_id])
            readiness = ExperimentEvaluationApplicationService(db).readiness(
                incomplete_experiment
            )
            assert readiness["ready"] is False
            assert readiness["missing_analytics"][0]["missing_stage"] == "risk"
            with pytest.raises(ExperimentEvaluationApplicationError) as missing:
                ExperimentEvaluationApplicationService(db).calculate_now(
                    incomplete_experiment
                )
            assert missing.value.code == "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPLETE"

            first, _ = _complete_case(db)
            second, _ = _complete_case(db)
            risk = db.get(PortfolioPerformanceRiskReport, second.risk_id)
            assert risk is not None
            risk.benchmark_code = "000905.SH"
            db.commit()
            incompatible_experiment = _experiment(db, 2)
            _bind(db, incompatible_experiment, [first.run_id, second.run_id])
            with pytest.raises(ExperimentEvaluationApplicationError) as incompatible:
                ExperimentEvaluationApplicationService(db).calculate_now(
                    incompatible_experiment
                )
            assert (
                incompatible.value.code
                == "EXPERIMENT_EVALUATION_ANALYTICS_INCOMPATIBLE"
            )
            assert "benchmark_code" in incompatible.value.details["mismatch_fields"]
            assert db.scalar(
                select(func.count()).select_from(PortfolioExperimentEvaluationReport)
            ) == 0
        transaction.rollback()
    engine.dispose()


def test_policy_identity_active_job_conflict_and_no_feasible_success() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            case, _ = _complete_case(db)
            experiment_id = _experiment(db, 1)
            _bind(db, experiment_id, [case.run_id])
            impossible = EvaluationPolicyConfig.model_validate(
                {
                    "primary_objective": "annualized_return",
                    "shortlist_size": 10,
                    "constraints": {"min_annualized_return": "999"},
                    "pareto_metrics": [
                        "annualized_return",
                        "max_drawdown_abs",
                        "annualized_turnover",
                    ],
                    "tie_breakers": [
                        "max_drawdown_abs",
                        "sharpe_ratio",
                        "annualized_turnover",
                    ],
                }
            )
            service = ExperimentEvaluationApplicationService(db)
            artifact = service.calculate_now(experiment_id, impossible)
            assert artifact.report.status == "SUCCESS"
            assert artifact.report.feasible_count == 0
            assert artifact.report.selected_trial_id is None
            assert "NO_FEASIBLE_TRIALS" in artifact.report.warnings

            job = service.queue_calculation(experiment_id, impossible)
            assert job.status == "QUEUED"
            with pytest.raises(ExperimentEvaluationConflictError) as conflict:
                service.queue_calculation(experiment_id, impossible)
            assert conflict.value.job_id == job.id
            assert db.scalar(
                select(func.count())
                .select_from(JobRun)
                .where(
                    JobRun.job_type == "portfolio_experiment_evaluation",
                    JobRun.status.in_(("QUEUED", "RUNNING")),
                )
            ) == 1
        transaction.rollback()
    engine.dispose()


def test_concurrent_queue_old_worker_fencing_and_replacement_success() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    try:
        with Session(engine, expire_on_commit=False) as setup:
            case = seed_analytics_case(setup, FENCING_DATES)
            run_id = case.run_id
            PerformancePeriodApplicationService(setup).calculate_now(
                case.run_id,
                performance_id=case.performance_id,
                risk_id=case.risk_id,
                trade_id=case.trade_id,
            )
            created = ExperimentApplicationService(setup).create(
                name="m15.2-fencing",
                start_date=FENCING_DATES[0],
                end_date=FENCING_DATES[-1],
                initial_cash=None,
                benchmark_code=None,
                grid={},
            )
            experiment_id = uuid.UUID(created["id"])
            _bind(setup, experiment_id, [case.run_id])

        barrier = Barrier(2)

        def queue() -> tuple[str, uuid.UUID]:
            with Session(engine) as contender:
                barrier.wait()
                try:
                    job = ExperimentEvaluationApplicationService(
                        contender
                    ).queue_calculation(experiment_id)
                    return "QUEUED", job.id
                except ExperimentEvaluationConflictError as exc:
                    assert exc.job_id is not None
                    return "CONFLICT", exc.job_id

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: queue(), range(2)))
        assert sorted(status for status, _ in outcomes) == ["CONFLICT", "QUEUED"]
        assert len({job_id for _, job_id in outcomes}) == 1
        job_id = outcomes[0][1]

        with Session(engine) as claim:
            job = claim.get(JobRun, job_id)
            assert job is not None
            job.status = "RUNNING"
            job.worker_id = "m15.2-old-worker"
            job.heartbeat_at = datetime.now(UTC)
            claim.commit()

        def lose_ownership(_lease, _artifact) -> None:
            with Session(engine) as recovery:
                job = recovery.get(JobRun, job_id)
                assert job is not None
                job.status = "FAILED"
                job.finished_at = datetime.now(UTC)
                job.job_metadata = {
                    **dict(job.job_metadata or {}),
                    "stage": "FAILED",
                    "error_code": "EXPERIMENT_EVALUATION_WORKER_HEARTBEAT_TIMEOUT",
                }
                recovery.commit()

        with Session(engine) as old_worker:
            with pytest.raises(ExperimentEvaluationApplicationError) as lost:
                ExperimentEvaluationApplicationService(
                    old_worker, before_terminal_hook=lose_ownership
                ).run_job(job_id)
            assert lost.value.code == "EXPERIMENT_EVALUATION_OWNERSHIP_LOST"

        with Session(engine) as check:
            assert check.get(JobRun, job_id).status == "FAILED"
            assert check.scalar(
                select(func.count())
                .select_from(PortfolioExperimentEvaluationReport)
                .where(
                    PortfolioExperimentEvaluationReport.experiment_id
                    == experiment_id
                )
            ) == 0

        with Session(engine) as replacement_session:
            replacement = ExperimentEvaluationApplicationService(
                replacement_session
            ).queue_calculation(experiment_id)
            replacement.status = "RUNNING"
            replacement.worker_id = "m15.2-replacement-worker"
            replacement.heartbeat_at = datetime.now(UTC)
            replacement_session.commit()
            artifact = ExperimentEvaluationApplicationService(
                replacement_session
            ).run_job(replacement.id)
            assert artifact.reused is False

        with Session(engine) as check:
            assert check.scalar(
                select(func.count())
                .select_from(PortfolioExperimentEvaluationReport)
                .where(
                    PortfolioExperimentEvaluationReport.experiment_id
                    == experiment_id
                )
            ) == 1
    finally:
        if experiment_id is not None:
            with Session(engine) as cleanup:
                cleanup.execute(
                    sa.delete(JobRun).where(
                        JobRun.job_metadata["experiment_id"].astext
                        == str(experiment_id)
                    )
                )
                experiment = cleanup.get(PortfolioExperiment, experiment_id)
                if experiment is not None:
                    cleanup.delete(experiment)
                cleanup.commit()
        if run_id is not None:
            with Session(engine) as cleanup:
                run = cleanup.get(PortfolioBacktestRun, run_id)
                if run is not None:
                    cleanup.delete(run)
                cleanup.execute(
                    sa.delete(IndexDaily).where(
                        IndexDaily.trade_date.in_(FENCING_DATES)
                    )
                )
                cleanup.execute(
                    sa.delete(TradeCalendar).where(
                        TradeCalendar.cal_date.in_(FENCING_DATES)
                    )
                )
                cleanup.commit()
        engine.dispose()


def test_recovery_rechecks_fresh_heartbeat_before_marking_failed() -> None:
    engine = sa.create_engine(get_settings().database_url)
    now = datetime.now(UTC)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            job = JobRun(
                job_type="portfolio_experiment_evaluation",
                status="RUNNING",
                worker_id="m15.2-recovery-worker",
                heartbeat_at=now - timedelta(minutes=30),
                job_metadata={"experiment_id": str(uuid.uuid4())},
            )
            db.add(job)
            db.commit()

            def heartbeat_wins(job_id: uuid.UUID) -> None:
                refreshed = db.get(JobRun, job_id)
                assert refreshed is not None
                refreshed.heartbeat_at = now
                db.flush()

            assert recover_stale_experiment_evaluation_jobs(
                db,
                timeout_minutes=15,
                now=now,
                before_lock_hook=heartbeat_wins,
            ) == 0
            db.expire_all()
            assert db.get(JobRun, job.id).status == "RUNNING"

            stale = db.get(JobRun, job.id)
            stale.heartbeat_at = now - timedelta(minutes=30)
            db.commit()
            assert recover_stale_experiment_evaluation_jobs(
                db, timeout_minutes=15, now=now
            ) == 1
            db.expire_all()
            failed = db.get(JobRun, job.id)
            assert failed.status == "FAILED"
            assert failed.job_metadata["error_code"] == (
                "EXPERIMENT_EVALUATION_WORKER_HEARTBEAT_TIMEOUT"
            )
        transaction.rollback()
    engine.dispose()
