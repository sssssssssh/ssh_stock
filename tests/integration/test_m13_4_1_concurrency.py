from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Event

import pytest
import sqlalchemy as sa
from app.api.v1.portfolio import backtest_orders
from app.core.db import SessionLocal, engine
from app.models.job import JobRun
from app.models.portfolio import (
    PortfolioBacktestCheckpoint,
    PortfolioBacktestRun,
    PortfolioOrder,
    PortfolioRebalancePlan,
)
from app.services.job_worker import execute_claimed_job
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.backtest_application import (
    BacktestApplicationService,
    BacktestConflictError,
    BacktestOwnershipError,
    BacktestRecoveryRejectedError,
    BacktestRunner,
    recover_stale_backtest_jobs,
)


def test_cross_session_cancel_is_visible_with_expire_on_commit_disabled() -> None:
    name = "m13.4.1-cross-session-cancel"
    run_id = job_id = None
    try:
        with SessionLocal() as setup:
            run, job = _queued_running_job(setup, name, "worker-a")
            run_id, job_id = run.id, job.id
        with SessionLocal() as worker:
            assert worker.expire_on_commit is False
            runner = BacktestRunner(worker)
            _, cached_job, lease = runner._claim_run(job_id)
            assert cached_job.cancel_requested is False
            with SessionLocal() as requester:
                cancelled_run, requested_job = BacktestApplicationService(
                    requester
                ).cancel(run_id)
                assert cancelled_run.status == "RUNNING"
                assert requested_job is not None and requested_job.cancel_requested
            assert runner._cancel_requested(job_id) is True
            runner._finish_cancelled(lease)
        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            job = check.get(JobRun, job_id)
            assert run is not None and run.status == "CANCELLED"
            assert job is not None and job.status == "CANCELLED"
    finally:
        _cleanup(name)


def test_cancel_during_phase_commits_current_checkpoint_and_stops_next_phase() -> None:
    name = "m13.4.1-cancel-during-phase"
    run_id = job_id = None
    phase_locked = Event()
    cancel_started = Event()
    release_phase = Event()
    try:
        with SessionLocal() as setup:
            run, job = _queued_running_job(setup, name, "worker-phase")
            run_id, job_id = run.id, job.id
            _, _, lease = BacktestRunner(setup)._claim_run(job_id)

        def commit_open_phase() -> None:
            with SessionLocal() as phase_db:
                runner = BacktestRunner(phase_db)
                runner._assert_ownership(lease, allow_cancel=True)
                phase_db.add(
                    PortfolioBacktestCheckpoint(
                        run_id=run_id,
                        trade_date=date(2026, 1, 5),
                        phase="OPEN",
                        phase_status="COMPLETED",
                        input_identity={"hash": "open-input"},
                        result_identity={"hash": "open-result"},
                        started_at=datetime.now(UTC),
                        completed_at=datetime.now(UTC),
                        attempt=1,
                        version=1,
                        worker_owner=lease.worker_id,
                    )
                )
                phase_db.flush()
                phase_locked.set()
                assert release_phase.wait(timeout=10)
                phase_db.commit()

        def request_cancel() -> None:
            cancel_started.set()
            with SessionLocal() as requester:
                BacktestApplicationService(requester).cancel(run_id)

        with ThreadPoolExecutor(max_workers=2) as pool:
            phase_future = pool.submit(commit_open_phase)
            assert phase_locked.wait(timeout=10)
            cancel_future = pool.submit(request_cancel)
            assert cancel_started.wait(timeout=10)
            release_phase.set()
            phase_future.result(timeout=10)
            cancel_future.result(timeout=10)

        with SessionLocal() as finisher:
            runner = BacktestRunner(finisher)
            assert runner._cancel_requested(job_id)
            runner._finish_cancelled(lease)
        with SessionLocal() as check:
            open_checkpoint = check.scalar(
                sa.select(PortfolioBacktestCheckpoint).where(
                    PortfolioBacktestCheckpoint.run_id == run_id,
                    PortfolioBacktestCheckpoint.phase == "OPEN",
                )
            )
            close_checkpoint = check.scalar(
                sa.select(PortfolioBacktestCheckpoint).where(
                    PortfolioBacktestCheckpoint.run_id == run_id,
                    PortfolioBacktestCheckpoint.phase == "CLOSE",
                )
            )
            run = check.get(PortfolioBacktestRun, run_id)
            job = check.get(JobRun, job_id)
            assert open_checkpoint is not None
            assert open_checkpoint.phase_status == "COMPLETED"
            assert close_checkpoint is None
            assert run is not None and run.status == "CANCELLED"
            assert job is not None and job.status == "CANCELLED"
    finally:
        release_phase.set()
        _cleanup(name)


def test_ownership_generation_fences_duplicate_and_old_worker_failure() -> None:
    name = "m13.4.1-fencing"
    run_id = old_job_id = new_job_id = None
    try:
        with SessionLocal() as setup:
            run, job = _queued_running_job(setup, name, "worker-a")
            run_id, old_job_id = run.id, job.id
        with SessionLocal() as worker_a:
            runner_a = BacktestRunner(worker_a)
            _, _, old_lease = runner_a._claim_run(old_job_id)
            with SessionLocal() as duplicate:
                with pytest.raises(BacktestOwnershipError):
                    BacktestRunner(duplicate)._claim_run(old_job_id)
                duplicate.rollback()
            with SessionLocal() as generic_worker_handler:
                execute_claimed_job(generic_worker_handler, old_job_id)
            with SessionLocal() as still_owned:
                active_job = still_owned.get(JobRun, old_job_id)
                active_run = still_owned.get(PortfolioBacktestRun, run_id)
                assert active_job is not None and active_job.status == "RUNNING"
                assert active_run is not None and active_run.status == "RUNNING"

            with SessionLocal() as transfer:
                old_job = transfer.execute(
                    sa.select(JobRun).where(JobRun.id == old_job_id).with_for_update()
                ).scalar_one()
                run = transfer.execute(
                    sa.select(PortfolioBacktestRun)
                    .where(PortfolioBacktestRun.id == run_id)
                    .with_for_update()
                ).scalar_one()
                old_job.status = "FAILED"
                old_job.finished_at = datetime.now(UTC)
                replacement = JobRun(
                    job_type="portfolio_backtest",
                    target_trade_date=run.end_date,
                    status="RUNNING",
                    worker_id="worker-b",
                    heartbeat_at=datetime.now(UTC),
                    cancel_requested=False,
                    job_metadata={"portfolio_run_id": str(run.id)},
                )
                transfer.add(replacement)
                transfer.flush()
                run.job_id = replacement.id
                run.owner_worker_id = "worker-b"
                run.ownership_version += 1
                replacement.job_metadata = {
                    **replacement.job_metadata,
                    "ownership_version": run.ownership_version,
                }
                new_job_id = replacement.id
                transfer.commit()

            with pytest.raises(BacktestOwnershipError):
                runner_a._assert_ownership(old_lease, allow_cancel=True)
            worker_a.rollback()
            runner_a._mark_run_failed(old_lease, RuntimeError("old worker error"))

        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            replacement = check.get(JobRun, new_job_id)
            assert run is not None
            assert (run.status, run.job_id, run.owner_worker_id) == (
                "RUNNING",
                new_job_id,
                "worker-b",
            )
            assert replacement is not None and replacement.status == "RUNNING"
    finally:
        _cleanup(name)


def test_stale_recovery_revalidates_heartbeat_under_lock_and_preserves_history() -> None:
    name = "m13.4.1-stale-recheck"
    run_id = job_id = None
    try:
        with SessionLocal() as setup:
            run, job = _queued_running_job(setup, name, "worker-stale")
            run_id, job_id = run.id, job.id
            _, _, _ = BacktestRunner(setup)._claim_run(job_id)
            job = setup.get(JobRun, job_id)
            assert job is not None
            job.heartbeat_at = datetime.now(UTC) - timedelta(minutes=30)
            setup.add(
                PortfolioBacktestCheckpoint(
                    run_id=run_id,
                    trade_date=date(2026, 1, 5),
                    phase="START_OF_DAY",
                    phase_status="COMPLETED",
                    input_identity={"hash": "history"},
                    result_identity={"hash": "history"},
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    attempt=1,
                    version=1,
                    worker_owner="worker-stale",
                )
            )
            setup.commit()

        refreshed_at = datetime.now(UTC)

        def refresh_after_discovery(_: object) -> None:
            with SessionLocal() as heartbeat:
                heartbeat.execute(
                    sa.update(JobRun)
                    .where(JobRun.id == job_id)
                    .values(heartbeat_at=refreshed_at)
                )
                heartbeat.commit()

        with SessionLocal() as recovery:
            assert (
                recover_stale_backtest_jobs(
                    recovery,
                    timeout_minutes=15,
                    now=refreshed_at,
                    before_lock_hook=refresh_after_discovery,
                )
                == 0
            )
        with SessionLocal() as make_stale:
            make_stale.execute(
                sa.update(JobRun)
                .where(JobRun.id == job_id)
                .values(heartbeat_at=refreshed_at - timedelta(minutes=30))
            )
            make_stale.commit()
        with SessionLocal() as recovery:
            assert (
                recover_stale_backtest_jobs(
                    recovery, timeout_minutes=15, now=refreshed_at
                )
                == 1
            )
        with SessionLocal() as check:
            run = check.get(PortfolioBacktestRun, run_id)
            job = check.get(JobRun, job_id)
            history = check.scalar(
                sa.select(sa.func.count())
                .select_from(PortfolioBacktestCheckpoint)
                .where(PortfolioBacktestCheckpoint.run_id == run_id)
            )
            assert run is not None and run.status == "FAILED"
            assert job is not None and job.status == "FAILED"
            assert history == 1
    finally:
        _cleanup(name)


def test_terminal_success_is_not_rewritten_by_cancel() -> None:
    name = "m13.4.1-terminal-cancel"
    try:
        with SessionLocal() as db:
            run, job = _queued_running_job(db, name, "worker-terminal")
            run.status = "SUCCESS"
            run.owner_worker_id = None
            job.status = "SUCCESS"
            job.finished_at = datetime.now(UTC)
            db.commit()
            with pytest.raises(BacktestConflictError):
                BacktestApplicationService(db).cancel(run.id)
            db.rollback()
            db.refresh(run)
            db.refresh(job)
            assert run.status == job.status == "SUCCESS"
    finally:
        _cleanup(name)


def test_after_close_seals_cancelled_prior_order_but_allows_new_order_progress() -> None:
    name = "m13.4.1-after-close-cancel-evidence"
    day_one, day_two = date(2026, 1, 5), date(2026, 1, 6)
    try:
        with SessionLocal() as db:
            run = PortfolioApplicationService(db).create_backtest_definition(
                start_date=day_one, end_date=day_two, name=name
            )
            prior = PortfolioOrder(
                run_id=run.id,
                signal_trade_date=day_one,
                scheduled_trade_date=day_one,
                ts_code="600134.SH",
                side="BUY",
                order_type="NEXT_OPEN",
                target_weight=Decimal("0.5"),
                target_quantity=100,
                status="CANCELLED",
                reason_code="SUPERSEDED_BY_REBALANCE",
            )
            db.add(prior)
            db.flush()
            plan = PortfolioRebalancePlan(
                run_id=run.id,
                signal_trade_date=day_one,
                scheduled_trade_date=day_two,
                total_assets=Decimal("1000000"),
                portfolio_version="portfolio_v3",
                input_hash="m13-4-1-test",
                target_snapshot={},
                account_snapshot={},
                plan_snapshot={
                    "pre_plan_pending": [
                        {
                            "order_id": str(prior.id),
                            "ts_code": prior.ts_code,
                            "side": prior.side,
                            "quantity": prior.target_quantity,
                            "attempt_count": 0,
                        }
                    ],
                    "result": {
                        "pending_actions": [
                            {
                                "order_id": str(prior.id),
                                "action": "CANCEL",
                                "reason_code": "SUPERSEDED_BY_REBALANCE",
                            }
                        ]
                    },
                },
            )
            db.add(plan)
            db.flush()
            new_order = PortfolioOrder(
                run_id=run.id,
                rebalance_plan_id=plan.id,
                child_index=1,
                signal_trade_date=day_one,
                scheduled_trade_date=day_two,
                ts_code="600135.SH",
                side="BUY",
                order_type="NEXT_OPEN",
                target_weight=Decimal("0.5"),
                target_quantity=100,
                status="PENDING",
            )
            db.add(new_order)
            db.commit()

            runner = BacktestRunner(db)
            runner._dates = (day_one, day_two)
            sealed = runner._result_identity(run.id, day_one, "AFTER_CLOSE")
            assert sealed["evidence"]["cancelled_prior_orders"] == [
                {
                    "order_id": str(prior.id),
                    "run_id": str(run.id),
                    "decision": "CANCEL",
                    "status": "CANCELLED",
                    "reason_code": "SUPERSEDED_BY_REBALANCE",
                }
            ]
            checkpoint = PortfolioBacktestCheckpoint(
                run_id=run.id,
                trade_date=day_one,
                phase="AFTER_CLOSE",
                phase_status="COMPLETED",
                input_identity={},
                result_identity=sealed,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                attempt=1,
                version=1,
            )
            new_order.status = "EXECUTED"
            db.commit()
            runner._validate_checkpoint_result(checkpoint)

            prior.status = "PENDING"
            prior.reason_code = None
            db.commit()
            with pytest.raises(BacktestRecoveryRejectedError) as mismatch:
                runner._validate_checkpoint_result(checkpoint)
            assert mismatch.value.code == "AFTER_CLOSE_CANCEL_EVIDENCE_MISMATCH"

            legacy = runner._result_identity(
                run.id, day_one, "AFTER_CLOSE", legacy_after_close=True
            )
            checkpoint.result_identity = legacy
            with pytest.raises(BacktestRecoveryRejectedError) as incompatible:
                runner._validate_checkpoint_result(checkpoint)
            assert incompatible.value.code == (
                "LEGACY_AFTER_CLOSE_CANCEL_EVIDENCE_UNVERIFIABLE"
            )
    finally:
        _cleanup(name)


def test_order_page_batches_associations_for_only_the_current_page() -> None:
    name = "m13.4.1-order-page"
    statements: list[tuple[str, dict[str, object]]] = []
    try:
        with SessionLocal() as setup:
            run = PortfolioApplicationService(setup).create_backtest_definition(
                start_date=date(2026, 1, 5), end_date=date(2026, 1, 5), name=name
            )
            setup.add_all(
                [
                    PortfolioOrder(
                        run_id=run.id,
                        signal_trade_date=date(2026, 1, 5),
                        scheduled_trade_date=date(2026, 1, 6),
                        ts_code=f"{600000 + index}.SH",
                        side="BUY",
                        order_type="NEXT_OPEN",
                        target_weight=Decimal("0.01"),
                        target_quantity=100,
                        status="PENDING",
                    )
                    for index in range(40)
                ]
            )
            setup.commit()
            run_id = run.id

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            parameters: dict[str, object],
            _context: object,
            _executemany: bool,
        ) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append((statement, parameters))

        sa.event.listen(engine, "before_cursor_execute", capture)
        try:
            with SessionLocal() as db:
                response = backtest_orders(run_id, limit=7, offset=14, db=db)
        finally:
            sa.event.remove(engine, "before_cursor_execute", capture)

        assert len(response["data"]) == 7
        assert response["meta"] == {"limit": 7, "offset": 14, "total": 40}
        # Run existence, page, count, attempts batch, fills batch: fixed query count.
        assert len(statements) == 5
        association_queries = [
            statement
            for statement, _ in statements
            if "portfolio_order_attempt" in statement or "portfolio_fill" in statement
        ]
        assert len(association_queries) == 2
        assert all("order_id IN" in statement for statement in association_queries)
    finally:
        _cleanup(name)


def _queued_running_job(
    db: object, name: str, worker_id: str
) -> tuple[PortfolioBacktestRun, JobRun]:
    run = PortfolioApplicationService(db).create_backtest_definition(
        start_date=date(2026, 1, 5), end_date=date(2026, 1, 5), name=name
    )
    run, job = BacktestApplicationService(db).execute(run.id)
    job.status = "RUNNING"
    job.worker_id = worker_id
    job.heartbeat_at = datetime.now(UTC)
    db.commit()
    return run, job


def _cleanup(name: str) -> None:
    with SessionLocal() as db:
        runs = list(
            db.execute(
                sa.select(PortfolioBacktestRun).where(
                    PortfolioBacktestRun.name == name
                )
            ).scalars()
        )
        run_ids = [str(run.id) for run in runs]
        job_ids = list(
            db.execute(
                sa.select(JobRun.id).where(
                    JobRun.job_type == "portfolio_backtest",
                    JobRun.job_metadata["portfolio_run_id"].astext.in_(run_ids),
                )
            ).scalars()
        )
        for run in runs:
            db.delete(run)
        db.flush()
        if job_ids:
            db.execute(sa.delete(JobRun).where(JobRun.id.in_(job_ids)))
        db.commit()
