import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Event, Lock
from time import sleep

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.job import JobRun
from app.models.portfolio import PortfolioBacktestRun
from app.services.experiment import (
    ExperimentApplicationError,
    ExperimentApplicationService,
)
from sqlalchemy.orm import Session


def test_materialization_mid_failure_rolls_back_every_run_binding_and_job() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id: uuid.UUID | None = None
    baseline_runs: int
    baseline_jobs: int
    try:
        with Session(engine) as db:
            baseline_runs = _count(db, PortfolioBacktestRun)
            baseline_jobs = _count(db, JobRun)
            experiment_id = _create_experiment(db, "m15.1.1-materialize-rollback", 4)

            def fail_third(
                stage: str, trial: PortfolioExperimentTrial | None
            ) -> None:
                if stage == "before_materialize_trial" and trial is not None:
                    if trial.trial_no == 3:
                        raise RuntimeError("injected materialization failure")

            with pytest.raises(ExperimentApplicationError) as caught:
                ExperimentApplicationService(db, fault_hook=fail_third).start(
                    experiment_id
                )
            assert caught.value.code == "EXPERIMENT_MATERIALIZATION_FAILED"

        with Session(engine) as check:
            experiment = check.get(PortfolioExperiment, experiment_id)
            assert experiment is not None and experiment.started_at is None
            assert _run_ids(check, experiment_id) == [None, None, None, None]
            assert _count(check, PortfolioBacktestRun) == baseline_runs
            assert _count(check, JobRun) == baseline_jobs
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_phase_a_crash_retry_reuses_runs_and_dispatches_exactly_one_job_each() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id: uuid.UUID | None = None
    crashed = False
    try:
        with Session(engine) as db:
            experiment_id = _create_experiment(db, "m15.1.1-phase-a-crash", 4)

            def crash_after_phase_a(
                stage: str, _trial: PortfolioExperimentTrial | None
            ) -> None:
                nonlocal crashed
                if stage == "after_materialization_commit" and not crashed:
                    crashed = True
                    raise RuntimeError("injected crash after phase A")

            with pytest.raises(RuntimeError, match="injected crash after phase A"):
                ExperimentApplicationService(
                    db, fault_hook=crash_after_phase_a
                ).start(experiment_id)

        with Session(engine) as check:
            run_ids_before = _run_ids(check, experiment_id)
            assert None not in run_ids_before
            assert len(set(run_ids_before)) == 4
            assert _jobs_for_runs(check, run_ids_before) == []

        with Session(engine) as retry:
            ExperimentApplicationService(retry).start(experiment_id)

        with Session(engine) as check:
            run_ids_after = _run_ids(check, experiment_id)
            jobs = _jobs_for_runs(check, run_ids_after)
            assert run_ids_after == run_ids_before
            assert len(jobs) == 4
            assert all(job.status == "QUEUED" for job in jobs)
            assert {job.job_metadata["portfolio_run_id"] for job in jobs} == {
                str(run_id) for run_id in run_ids_after
            }
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_partial_dispatch_crash_retry_does_not_duplicate_existing_jobs() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id: uuid.UUID | None = None
    try:
        with Session(engine) as db:
            experiment_id = _create_experiment(db, "m15.1.1-partial-dispatch", 4)

            def fail_third_dispatch(
                stage: str, trial: PortfolioExperimentTrial | None
            ) -> None:
                if stage == "after_dispatch_gate" and trial is not None:
                    if trial.trial_no == 3:
                        raise RuntimeError("injected dispatch failure")

            with pytest.raises(ExperimentApplicationError) as caught:
                ExperimentApplicationService(
                    db, fault_hook=fail_third_dispatch
                ).start(experiment_id)
            assert caught.value.code == "EXPERIMENT_DISPATCH_CONFLICT"

        with Session(engine) as check:
            run_ids_before = _run_ids(check, experiment_id)
            first_jobs = _jobs_for_runs(check, run_ids_before)
            first_job_ids = {job.id for job in first_jobs}
            assert len(first_jobs) == 2

        with Session(engine) as retry:
            ExperimentApplicationService(retry).start(experiment_id)

        with Session(engine) as check:
            run_ids_after = _run_ids(check, experiment_id)
            jobs = _jobs_for_runs(check, run_ids_after)
            assert run_ids_after == run_ids_before
            assert len(jobs) == 4
            assert first_job_ids < {job.id for job in jobs}
            assert len(
                {job.job_metadata["portfolio_run_id"] for job in jobs}
            ) == 4
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_start_skips_failed_and_cancelled_children_and_only_executes_created() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id: uuid.UUID | None = None
    crashed = False
    try:
        with Session(engine) as db:
            experiment_id = _create_experiment(db, "m15.1.1-terminal-skip", 3)

            def stop_before_dispatch(
                stage: str, _trial: PortfolioExperimentTrial | None
            ) -> None:
                nonlocal crashed
                if stage == "after_materialization_commit" and not crashed:
                    crashed = True
                    raise RuntimeError("stop before dispatch")

            with pytest.raises(RuntimeError):
                ExperimentApplicationService(db, fault_hook=stop_before_dispatch).start(
                    experiment_id
                )

        with Session(engine) as mutate:
            runs = _runs(mutate, experiment_id)
            runs[0].status = "FAILED"
            runs[1].status = "CANCELLED"
            mutate.commit()

        with Session(engine) as retry:
            ExperimentApplicationService(retry).start(experiment_id)

        with Session(engine) as check:
            runs = _runs(check, experiment_id)
            jobs = _jobs_for_runs(check, [run.id for run in runs])
            assert [run.status for run in runs] == ["FAILED", "CANCELLED", "CREATED"]
            assert len(jobs) == 1
            assert jobs[0].job_metadata["portfolio_run_id"] == str(runs[2].id)
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_cancel_racing_dispatch_never_creates_job_after_cancel_gate() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_ids: list[uuid.UUID] = []
    try:
        cancel_wins_id = _create_in_new_session(
            engine, "m15.1.1-race-cancel-wins"
        )
        experiment_ids.append(cancel_wins_id)
        before_lock = Event()
        release_start = Event()
        hook_once = Lock()
        hook_used = False

        def pause_before_dispatch(
            stage: str, _trial: PortfolioExperimentTrial | None
        ) -> None:
            nonlocal hook_used
            if stage != "before_dispatch_lock":
                return
            with hook_once:
                if hook_used:
                    return
                hook_used = True
            before_lock.set()
            assert release_start.wait(10)

        def start_cancel_wins() -> dict[str, object]:
            with Session(engine) as db:
                return ExperimentApplicationService(
                    db, fault_hook=pause_before_dispatch
                ).start(cancel_wins_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            start_future = pool.submit(start_cancel_wins)
            assert before_lock.wait(10)
            with Session(engine) as cancel_db:
                cancelled = ExperimentApplicationService(cancel_db).cancel(
                    cancel_wins_id
                )
            release_start.set()
            started = start_future.result(timeout=10)
        assert cancelled["state"] == "CANCELLED"
        assert started["state"] == "CANCELLED"
        with Session(engine) as check:
            assert _jobs_for_runs(check, _run_ids(check, cancel_wins_id)) == []

        dispatch_wins_id = _create_in_new_session(
            engine, "m15.1.1-race-dispatch-wins"
        )
        experiment_ids.append(dispatch_wins_id)
        gate_checked = Event()
        release_dispatch = Event()

        def pause_after_gate(
            stage: str, _trial: PortfolioExperimentTrial | None
        ) -> None:
            if stage == "after_dispatch_gate":
                gate_checked.set()
                assert release_dispatch.wait(10)

        def start_dispatch_wins() -> dict[str, object]:
            with Session(engine) as db:
                return ExperimentApplicationService(
                    db, fault_hook=pause_after_gate
                ).start(dispatch_wins_id)

        def cancel_after_dispatch_gate() -> dict[str, object]:
            with Session(engine) as db:
                return ExperimentApplicationService(db).cancel(dispatch_wins_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            start_future = pool.submit(start_dispatch_wins)
            assert gate_checked.wait(10)
            cancel_future = pool.submit(cancel_after_dispatch_gate)
            sleep(0.1)
            release_dispatch.set()
            start_future.result(timeout=10)
            cancelled = cancel_future.result(timeout=10)
        assert cancelled["state"] == "CANCELLED"
        with Session(engine) as check:
            jobs = _jobs_for_runs(check, _run_ids(check, dispatch_wins_id))
            assert len(jobs) == 1
            assert jobs[0].status == "CANCELLED"
            assert jobs[0].cancel_requested is True
    finally:
        for experiment_id in experiment_ids:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_running_prelease_child_cancel_reuses_m13_generation_aware_cancel() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id: uuid.UUID | None = None
    try:
        with Session(engine) as db:
            experiment_id = _create_experiment(db, "m15.1.1-prelease-cancel", 1)
            ExperimentApplicationService(db).start(experiment_id)
            run = _runs(db, experiment_id)[0]
            assert run.job_id is not None
            job = db.get(JobRun, run.job_id)
            assert job is not None
            job.status = "RUNNING"
            job.worker_id = "m15.1.1-prelease-worker"
            job.heartbeat_at = datetime.now(UTC)
            db.commit()

            result = ExperimentApplicationService(db).cancel(experiment_id)
            assert result["state"] == "CANCELLED"

        with Session(engine) as check:
            run = _runs(check, experiment_id)[0]
            job = check.get(JobRun, run.job_id)
            assert run.status == "CANCELLED"
            assert job is not None and job.status == "CANCELLED"
            assert job.step == "cancelled before execution lease"
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_source_drift_after_materialization_preserves_bindings_and_creates_no_job() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id: uuid.UUID | None = None
    crashed = False
    try:
        with Session(engine) as db:
            experiment_id = _create_experiment(db, "m15.1.1-post-phase-a-drift", 2)

            def stop_after_phase_a(
                stage: str, _trial: PortfolioExperimentTrial | None
            ) -> None:
                nonlocal crashed
                if stage == "after_materialization_commit" and not crashed:
                    crashed = True
                    raise RuntimeError("stop after phase A")

            with pytest.raises(RuntimeError):
                ExperimentApplicationService(db, fault_hook=stop_after_phase_a).start(
                    experiment_id
                )

        with Session(engine) as check:
            run_ids = _run_ids(check, experiment_id)
            assert None not in run_ids

        drifted = get_settings().model_copy(deep=True)
        drifted.algo_version = "m15.1.1-drifted-source"
        with Session(engine) as retry:
            with pytest.raises(ExperimentApplicationError) as caught:
                ExperimentApplicationService(retry, settings=drifted).start(
                    experiment_id
                )
            assert caught.value.code == "EXPERIMENT_SOURCE_IDENTITY_DRIFT"

        with Session(engine) as check:
            assert _run_ids(check, experiment_id) == run_ids
            assert _jobs_for_runs(check, run_ids) == []
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def _create_in_new_session(engine: sa.Engine, name: str) -> uuid.UUID:
    with Session(engine) as db:
        return _create_experiment(db, name, 1)


def _create_experiment(db: Session, name: str, trial_count: int) -> uuid.UUID:
    min_scores = [65 + index for index in range(trial_count)]
    created = ExperimentApplicationService(db).create(
        name=name,
        start_date=date(2041, 1, 6),
        end_date=date(2041, 1, 10),
        initial_cash=None,
        benchmark_code=None,
        grid={"candidate.min_score": min_scores},
    )
    return uuid.UUID(created["id"])


def _count(db: Session, model: type[object]) -> int:
    return int(db.scalar(sa.select(sa.func.count()).select_from(model)) or 0)


def _run_ids(
    db: Session, experiment_id: uuid.UUID
) -> list[uuid.UUID | None]:
    return list(
        db.execute(
            sa.select(PortfolioExperimentTrial.run_id)
            .where(PortfolioExperimentTrial.experiment_id == experiment_id)
            .order_by(PortfolioExperimentTrial.trial_no)
        ).scalars()
    )


def _runs(db: Session, experiment_id: uuid.UUID) -> list[PortfolioBacktestRun]:
    return list(
        db.execute(
            sa.select(PortfolioBacktestRun)
            .join(
                PortfolioExperimentTrial,
                PortfolioExperimentTrial.run_id == PortfolioBacktestRun.id,
            )
            .where(PortfolioExperimentTrial.experiment_id == experiment_id)
            .order_by(PortfolioExperimentTrial.trial_no)
        ).scalars()
    )


def _jobs_for_runs(
    db: Session, run_ids: list[uuid.UUID | None]
) -> list[JobRun]:
    ids = [str(run_id) for run_id in run_ids if run_id is not None]
    if not ids:
        return []
    return list(
        db.execute(
            sa.select(JobRun)
            .where(JobRun.job_metadata["portfolio_run_id"].astext.in_(ids))
            .order_by(JobRun.started_at, JobRun.id)
        ).scalars()
    )


def _cleanup_experiment(engine: sa.Engine, experiment_id: uuid.UUID) -> None:
    with Session(engine) as db:
        run_ids = [
            run_id
            for run_id in _run_ids(db, experiment_id)
            if run_id is not None
        ]
        job_ids = [job.id for job in _jobs_for_runs(db, run_ids)]
        db.execute(
            sa.delete(PortfolioExperiment).where(
                PortfolioExperiment.id == experiment_id
            )
        )
        if run_ids:
            db.execute(
                sa.delete(PortfolioBacktestRun).where(
                    PortfolioBacktestRun.id.in_(run_ids)
                )
            )
        if job_ids:
            db.execute(sa.delete(JobRun).where(JobRun.id.in_(job_ids)))
        db.commit()
