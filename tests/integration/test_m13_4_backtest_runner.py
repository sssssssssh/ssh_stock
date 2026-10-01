from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.job import JobRun
from app.models.market_data import (
    MarketDaily,
    Sector,
    SectorFactorDaily,
    SectorMember,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockFactorDaily,
    StockLimitDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.models.portfolio import PortfolioBacktestRun, PortfolioRebalancePlan
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    SECTOR_CALC_VERSION,
    TRADE_STATUS_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.backtest_application import (
    PHASES,
    BacktestApplicationService,
    BacktestConflictError,
    BacktestOwnershipError,
    BacktestRecoveryRejectedError,
    BacktestRunner,
    recover_stale_backtest_jobs,
)
from app.services.portfolio.contracts import PortfolioSourceNotReadyError
from sqlalchemy.orm import Session


def test_five_day_runner_and_post_commit_recovery_are_equivalent() -> None:
    settings = get_settings()
    engine = sa.create_engine(settings.database_url)
    days = tuple(date(2026, 1, day) for day in range(5, 10))
    code = "600134.SH"
    _cleanup(engine, days, code)
    try:
        with Session(engine, expire_on_commit=False) as db:
                _seed_sources(db, days, code)
                normal = PortfolioApplicationService(db).create_backtest_definition(
                    start_date=days[0], end_date=days[-1], name="m13.4-normal"
                )
                recovered = PortfolioApplicationService(db).create_backtest_definition(
                    start_date=days[0], end_date=days[-1], name="m13.4-recovered"
                )
                preownership_recovered = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-preownership-recovered",
                )
                rolled_back = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0], end_date=days[-1], name="m13.4-rolled-back"
                )
                open_rolled_back = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-open-rolled-back",
                )
                rebalance_rolled_back = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-rebalance-rolled-back",
                )
                rebalance_postcommit = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-rebalance-postcommit",
                )
                source_drift = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-source-drift",
                )
                ledger_drift = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-ledger-drift",
                )
                incomplete = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-incomplete",
                )
                concurrent = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0],
                    end_date=days[-1],
                    name="m13.4-concurrent",
                )
                lifecycle = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0], end_date=days[-1], name="m13.4-lifecycle"
                )

                _, cancelled_job = BacktestApplicationService(db).execute(
                    lifecycle.id
                )
                cancelled_run, cancelled_job = BacktestApplicationService(db).cancel(
                    lifecycle.id
                )
                assert cancelled_run.status == "CANCELLED"
                assert cancelled_job is not None
                assert cancelled_job.status == "CANCELLED"
                same_cancelled_run, same_cancelled_job = BacktestApplicationService(
                    db
                ).cancel(lifecycle.id)
                assert same_cancelled_run.id == cancelled_run.id
                assert same_cancelled_job is not None
                assert same_cancelled_job.id == cancelled_job.id
                stale_run, stale_job = BacktestApplicationService(db).resume(
                    lifecycle.id
                )
                _claim(db, stale_job, "worker-stale")
                BacktestRunner(db)._claim_run(stale_job.id)
                stale_job.heartbeat_at = datetime.now(UTC) - timedelta(minutes=30)
                db.commit()
                assert recover_stale_backtest_jobs(
                    db, timeout_minutes=15, now=datetime.now(UTC)
                ) == 1
                db.refresh(stale_run)
                db.refresh(stale_job)
                assert stale_run.status == "FAILED"
                assert stale_job.status == "FAILED"
                assert stale_run.result_summary["error_code"] == (
                    "WORKER_HEARTBEAT_TIMEOUT"
                )

                barrier = Barrier(2)

                def submit_concurrently() -> tuple[str, str | None]:
                    with Session(engine) as contender:
                        barrier.wait()
                        try:
                            _, queued = BacktestApplicationService(contender).execute(
                                concurrent.id
                            )
                        except BacktestConflictError as exc:
                            contender.rollback()
                            return "CONFLICT", str(exc.job_id) if exc.job_id else None
                        return "QUEUED", str(queued.id)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = list(pool.map(lambda _: submit_concurrently(), range(2)))
                assert sorted(item[0] for item in outcomes) == ["CONFLICT", "QUEUED"]
                queued_ids = {item[1] for item in outcomes if item[1] is not None}
                assert len(queued_ids) == 1
                db.expire_all()
                concurrent_run, concurrent_job = BacktestApplicationService(db).cancel(
                    concurrent.id
                )
                assert concurrent_run.status == "CANCELLED"
                assert concurrent_job is not None
                assert str(concurrent_job.id) in queued_ids

                normal_job = _enqueue_and_claim(db, normal.id, "worker-normal")
                with pytest.raises(BacktestConflictError):
                    BacktestApplicationService(db).execute(normal.id)
                BacktestRunner(db).run_job(normal_job.id)

                _, first_generation_job = BacktestApplicationService(db).execute(
                    preownership_recovered.id
                )
                _claim(db, first_generation_job, "worker-preownership-a")
                _, _, first_generation_lease = BacktestRunner(db)._claim_run(
                    first_generation_job.id
                )
                BacktestRunner(db)._mark_run_failed(
                    first_generation_lease,
                    RuntimeError("injected first generation failure"),
                )
                db.refresh(preownership_recovered)
                db.refresh(first_generation_job)
                assert preownership_recovered.status == "FAILED"
                assert first_generation_job.status == "FAILED"
                assert preownership_recovered.ownership_version == 1

                _, preownership_job = BacktestApplicationService(db).resume(
                    preownership_recovered.id
                )
                _claim(db, preownership_job, "worker-preownership-old")
                preownership_job.heartbeat_at = datetime.now(UTC) - timedelta(
                    minutes=30
                )
                db.commit()
                old_preownership_job_id = preownership_job.id
                assert recover_stale_backtest_jobs(
                    db, timeout_minutes=15, now=datetime.now(UTC)
                ) == 1
                db.refresh(preownership_recovered)
                db.refresh(preownership_job)
                assert preownership_recovered.status == "FAILED"
                assert preownership_job.status == "FAILED"
                assert preownership_recovered.ownership_version == 1
                assert preownership_recovered.result_summary["error_code"] == (
                    "BACKTEST_PRE_OWNERSHIP_TIMEOUT"
                )
                assert PortfolioRepository(db).list_checkpoints(
                    preownership_recovered.id
                ) == []

                with Session(engine) as old_worker:
                    with pytest.raises(BacktestOwnershipError):
                        BacktestRunner(old_worker)._claim_run(
                            old_preownership_job_id
                        )

                _, preownership_resume_job = BacktestApplicationService(db).resume(
                    preownership_recovered.id
                )
                assert preownership_resume_job.id != old_preownership_job_id
                _claim(db, preownership_resume_job, "worker-preownership-new")
                BacktestRunner(db).run_job(preownership_resume_job.id)

                recovered_job = _enqueue_and_claim(
                    db, recovered.id, "worker-interrupted"
                )
                open_commits = 0

                def fail_after_second_open_commit(phase: str, point: str) -> None:
                    nonlocal open_commits
                    if phase == "OPEN" and point == "after_phase_commit":
                        open_commits += 1
                        if open_commits == 2:
                            raise RuntimeError("injected process loss after OPEN commit")

                with pytest.raises(RuntimeError, match="injected process loss"):
                    BacktestRunner(db, fault_hook=fail_after_second_open_commit).run_job(
                        recovered_job.id
                    )
                db.expire_all()
                interrupted = db.get(PortfolioBacktestRun, recovered.id)
                assert interrupted is not None
                assert interrupted.status == "FAILED"
                d2_open = PortfolioRepository(db).get_checkpoint(
                    recovered.id, days[1], "OPEN"
                )
                assert d2_open is not None
                assert d2_open.phase_status == "COMPLETED"

                _, resume_job = BacktestApplicationService(db).resume(recovered.id)
                _claim(db, resume_job, "worker-resume")
                BacktestRunner(db).run_job(resume_job.id)

                rollback_job = _enqueue_and_claim(
                    db, rolled_back.id, "worker-precommit"
                )

                def fail_before_first_close_checkpoint(
                    phase: str, point: str
                ) -> None:
                    if phase == "CLOSE" and point == "after_business_before_checkpoint":
                        raise RuntimeError("injected failure before CLOSE checkpoint")

                with pytest.raises(RuntimeError, match="before CLOSE checkpoint"):
                    BacktestRunner(
                        db, fault_hook=fail_before_first_close_checkpoint
                    ).run_job(rollback_job.id)
                assert PortfolioRepository(db).get_nav(
                    rolled_back.id, days[0]
                ) is None
                close_checkpoint = PortfolioRepository(db).get_checkpoint(
                    rolled_back.id, days[0], "CLOSE"
                )
                assert close_checkpoint is not None
                assert close_checkpoint.phase_status == "FAILED"
                _, rollback_resume_job = BacktestApplicationService(db).resume(
                    rolled_back.id
                )
                _claim(db, rollback_resume_job, "worker-precommit-resume")
                BacktestRunner(db).run_job(rollback_resume_job.id)

                open_rollback_job = _enqueue_and_claim(
                    db, open_rolled_back.id, "worker-open-precommit"
                )
                open_starts = 0

                def fail_before_second_open(phase: str, point: str) -> None:
                    nonlocal open_starts
                    if phase == "OPEN" and point == "before_business":
                        open_starts += 1
                        if open_starts == 2:
                            raise RuntimeError("injected failure before D2 OPEN")

                with pytest.raises(RuntimeError, match="before D2 OPEN"):
                    BacktestRunner(db, fault_hook=fail_before_second_open).run_job(
                        open_rollback_job.id
                    )
                assert not [
                    item
                    for item in PortfolioRepository(db).list_order_attempts(
                        open_rolled_back.id
                    )
                    if item.attempt_trade_date == days[1]
                ]
                assert not [
                    item
                    for item in PortfolioRepository(db).list_fills(open_rolled_back.id)
                    if item.trade_date == days[1]
                ]
                _, open_resume_job = BacktestApplicationService(db).resume(
                    open_rolled_back.id
                )
                _claim(db, open_resume_job, "worker-open-precommit-resume")
                BacktestRunner(db).run_job(open_resume_job.id)

                rebalance_rollback_job = _enqueue_and_claim(
                    db, rebalance_rolled_back.id, "worker-rebalance-precommit"
                )

                def fail_before_first_rebalance_checkpoint(
                    phase: str, point: str
                ) -> None:
                    if phase == "AFTER_CLOSE" and point == (
                        "after_business_before_checkpoint"
                    ):
                        raise RuntimeError(
                            "injected failure before AFTER_CLOSE checkpoint"
                        )

                with pytest.raises(RuntimeError, match="AFTER_CLOSE checkpoint"):
                    BacktestRunner(
                        db, fault_hook=fail_before_first_rebalance_checkpoint
                    ).run_job(rebalance_rollback_job.id)
                assert PortfolioRepository(db).get_rebalance_plan(
                    rebalance_rolled_back.id, days[0]
                ) is None
                _, rebalance_resume_job = BacktestApplicationService(db).resume(
                    rebalance_rolled_back.id
                )
                _claim(db, rebalance_resume_job, "worker-rebalance-precommit-resume")
                BacktestRunner(db).run_job(rebalance_resume_job.id)

                rebalance_postcommit_job = _enqueue_and_claim(
                    db, rebalance_postcommit.id, "worker-rebalance-postcommit"
                )

                def fail_after_first_rebalance_commit(
                    phase: str, point: str
                ) -> None:
                    if phase == "AFTER_CLOSE" and point == "after_phase_commit":
                        raise RuntimeError("injected failure after AFTER_CLOSE commit")

                with pytest.raises(RuntimeError, match="after AFTER_CLOSE commit"):
                    BacktestRunner(
                        db, fault_hook=fail_after_first_rebalance_commit
                    ).run_job(rebalance_postcommit_job.id)
                committed_plan = PortfolioRepository(db).get_rebalance_plan(
                    rebalance_postcommit.id, days[0]
                )
                committed_checkpoint = PortfolioRepository(db).get_checkpoint(
                    rebalance_postcommit.id, days[0], "AFTER_CLOSE"
                )
                assert committed_plan is not None
                assert committed_checkpoint is not None
                assert committed_checkpoint.phase_status == "COMPLETED"
                _, rebalance_postcommit_resume_job = BacktestApplicationService(db).resume(
                    rebalance_postcommit.id
                )
                _claim(
                    db,
                    rebalance_postcommit_resume_job,
                    "worker-rebalance-postcommit-resume",
                )
                BacktestRunner(db).run_job(rebalance_postcommit_resume_job.id)

                source_drift_job = _enqueue_and_claim(
                    db, source_drift.id, "worker-source-drift"
                )
                source_open_commits = 0

                def stop_after_second_open(phase: str, point: str) -> None:
                    nonlocal source_open_commits
                    if phase == "OPEN" and point == "after_phase_commit":
                        source_open_commits += 1
                        if source_open_commits == 2:
                            raise RuntimeError("pause after second OPEN")

                with pytest.raises(RuntimeError, match="pause after second OPEN"):
                    BacktestRunner(db, fault_hook=stop_after_second_open).run_job(
                        source_drift_job.id
                    )
                source_row = db.get(StockDaily, (days[1], code))
                assert source_row is not None
                original_open = source_row.open
                source_row.open = original_open + 0.01
                db.commit()
                _, drift_resume_job = BacktestApplicationService(db).resume(
                    source_drift.id
                )
                _claim(db, drift_resume_job, "worker-source-drift-audit")
                with pytest.raises(BacktestRecoveryRejectedError) as drift_error:
                    BacktestRunner(db).run_job(drift_resume_job.id)
                assert drift_error.value.code == "HISTORICAL_INPUT_DRIFT"
                source_row = db.get(StockDaily, (days[1], code))
                assert source_row is not None
                source_row.open = original_open
                db.commit()
                _, source_resume_job = BacktestApplicationService(db).resume(
                    source_drift.id
                )
                _claim(db, source_resume_job, "worker-source-drift-resume")
                BacktestRunner(db).run_job(source_resume_job.id)

                ledger_drift_job = _enqueue_and_claim(
                    db, ledger_drift.id, "worker-ledger-drift"
                )

                def stop_after_first_close(phase: str, point: str) -> None:
                    if phase == "CLOSE" and point == "after_phase_commit":
                        raise RuntimeError("pause after first CLOSE")

                with pytest.raises(RuntimeError, match="pause after first CLOSE"):
                    BacktestRunner(db, fault_hook=stop_after_first_close).run_job(
                        ledger_drift_job.id
                    )
                ledger_nav = PortfolioRepository(db).get_nav(
                    ledger_drift.id, days[0]
                )
                assert ledger_nav is not None
                original_nav = ledger_nav.nav
                ledger_nav.nav = original_nav + Decimal("1")
                db.commit()
                with pytest.raises(BacktestRecoveryRejectedError) as ledger_error:
                    BacktestApplicationService(db).resume(ledger_drift.id)
                assert ledger_error.value.code == "CHECKPOINT_EVIDENCE_MISMATCH"
                db.rollback()
                ledger_nav = PortfolioRepository(db).get_nav(
                    ledger_drift.id, days[0]
                )
                assert ledger_nav is not None
                ledger_nav.nav = original_nav
                db.commit()
                _, ledger_resume_job = BacktestApplicationService(db).resume(
                    ledger_drift.id
                )
                _claim(db, ledger_resume_job, "worker-ledger-drift-resume")
                BacktestRunner(db).run_job(ledger_resume_job.id)

                db.expire_all()
                normal_run = db.get(PortfolioBacktestRun, normal.id)
                recovered_run = db.get(PortfolioBacktestRun, recovered.id)
                preownership_recovered_run = db.get(
                    PortfolioBacktestRun, preownership_recovered.id
                )
                rolled_back_run = db.get(PortfolioBacktestRun, rolled_back.id)
                assert normal_run is not None and normal_run.status == "SUCCESS"
                assert recovered_run is not None and recovered_run.status == "SUCCESS"
                assert preownership_recovered_run is not None
                assert preownership_recovered_run.status == "SUCCESS"
                assert preownership_recovered_run.ownership_version == 2
                assert rolled_back_run is not None
                assert rolled_back_run.status == "SUCCESS"
                _assert_complete_protocol(db, normal.id, days)
                _assert_complete_protocol(db, recovered.id, days)
                _assert_complete_protocol(db, preownership_recovered.id, days)
                _assert_business_results_equal(db, normal.id, recovered.id)
                _assert_business_results_equal(
                    db, normal.id, preownership_recovered.id
                )
                _assert_business_results_equal(db, normal.id, rolled_back.id)
                _assert_business_results_equal(db, normal.id, open_rolled_back.id)
                _assert_business_results_equal(
                    db, normal.id, rebalance_rolled_back.id
                )
                _assert_business_results_equal(
                    db, normal.id, rebalance_postcommit.id
                )
                _assert_business_results_equal(db, normal.id, source_drift.id)
                _assert_business_results_equal(db, normal.id, ledger_drift.id)

                recovered_positions = PortfolioRepository(db).list_position_snapshot(
                    recovered.id, days[-1]
                )
                assert recovered_positions == []
                assert len(PortfolioRepository(db).list_nav(recovered.id)) == 5
                empty_target_plan = PortfolioRepository(db).get_rebalance_plan(
                    normal.id, days[-2]
                )
                assert empty_target_plan is not None
                assert empty_target_plan.target_snapshot["targets"] == []
                assert PortfolioRepository(db).get_rebalance_plan(
                    normal.id, days[-1]
                ) is None

                incomplete_source = db.get(
                    StockOpportunityDaily, (days[0], code, settings.algo_version)
                )
                assert incomplete_source is not None
                db.delete(incomplete_source)
                db.commit()
                incomplete_job = _enqueue_and_claim(
                    db, incomplete.id, "worker-incomplete"
                )
                with pytest.raises(PortfolioSourceNotReadyError):
                    BacktestRunner(db).run_job(incomplete_job.id)
                db.refresh(incomplete)
                assert incomplete.status == "FAILED"
                assert PortfolioRepository(db).get_rebalance_plan(
                    incomplete.id, days[0]
                ) is None
    finally:
        _cleanup(engine, days, code)


def _seed_sources(db: Session, days: tuple[date, ...], code: str) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    sector = Sector(
        source="SW",
        source_code="M134-SECTOR",
        name="M13.4 Sector",
        level="L1",
        is_active=True,
    )
    db.add(sector)
    db.flush()
    db.add_all(
        [
            StockBasic(
                ts_code=code,
                symbol="600134",
                name="M13.4",
                market="主板",
                exchange="SSE",
                list_status="L",
                list_date=date(2020, 1, 1),
            ),
            SectorMember(
                sector_id=sector.sector_id,
                ts_code=code,
                valid_from=date(2020, 1, 1),
                is_latest=True,
            ),
        ]
    )
    for index, trade_date in enumerate(days):
        price = 10 + index
        high_signal = index < 3
        db.add_all(
            [
                TradeCalendar(
                    cal_date=trade_date,
                    is_open=True,
                    pretrade_date=days[index - 1] if index else None,
                    exchange="SSE",
                ),
                StockDaily(
                    trade_date=trade_date,
                    ts_code=code,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    pre_close=price - 1,
                ),
                StockAdjFactor(
                    trade_date=trade_date, ts_code=code, adj_factor=1
                ),
                StockLimitDaily(
                    trade_date=trade_date,
                    ts_code=code,
                    pre_close=price - 1,
                    up_limit=price + 2,
                    down_limit=price - 2,
                    exchange="SSE",
                ),
                StockTradeStatusDaily(
                    trade_date=trade_date,
                    ts_code=code,
                    is_active=True,
                    is_suspended=False,
                    st_status_unknown=False,
                    tradable=True,
                    strategy_eligible=True,
                    calc_version=TRADE_STATUS_CALC_VERSION,
                    config_hash=strategy_hash,
                    calculated_at=now,
                ),
                StockFactorDaily(
                    trade_date=trade_date,
                    ts_code=code,
                    eligible=True,
                    calc_version=FACTOR_CALC_VERSION,
                    config_hash=strategy_hash,
                    calculated_at=now,
                ),
                MarketDaily(
                    trade_date=trade_date,
                    calc_version=MARKET_CALC_VERSION,
                    config_hash=strategy_hash,
                    calculated_at=now,
                ),
                SectorFactorDaily(
                    trade_date=trade_date,
                    sector_id=sector.sector_id,
                    member_count=1,
                    eligible_member_count=1,
                    calc_version=SECTOR_CALC_VERSION,
                    config_hash=strategy_hash,
                    calculated_at=now,
                ),
                StockStateDaily(
                    trade_date=trade_date,
                    ts_code=code,
                    algo_version=settings.algo_version,
                    state="S4",
                    is_new_state=False,
                    fast_transition=False,
                    opportunity_score=85 if high_signal else 10,
                    calc_version=TREND_CALC_VERSION,
                    config_hash=strategy_hash,
                    calculated_at=now,
                ),
                StockOpportunityDaily(
                    trade_date=trade_date,
                    ts_code=code,
                    algo_version=settings.algo_version,
                    state="S4",
                    left_reversal_new=False,
                    opportunity_stage="TREND",
                    opportunity_score=85 if high_signal else 10,
                    calc_version=OPPORTUNITY_CALC_VERSION,
                    config_hash=opportunity_hash,
                    source_strategy_config_hash=strategy_hash,
                    calculated_at=now,
                ),
            ]
        )
    db.commit()


def _enqueue_and_claim(db: Session, run_id, worker_id: str) -> JobRun:
    _, job = BacktestApplicationService(db).execute(run_id)
    return _claim(db, job, worker_id)


def _claim(db: Session, job: JobRun, worker_id: str) -> JobRun:
    job.status = "RUNNING"
    job.worker_id = worker_id
    job.heartbeat_at = datetime.now(UTC)
    db.add(job)
    db.commit()
    return job


def _assert_complete_protocol(
    db: Session, run_id, days: tuple[date, ...]
) -> None:
    checkpoints = PortfolioRepository(db).list_checkpoints(run_id)
    assert len(checkpoints) == len(days) * len(PHASES)
    assert {
        (item.trade_date, item.phase, item.phase_status) for item in checkpoints
    } == {
        (trade_date, phase, "COMPLETED")
        for trade_date in days
        for phase in PHASES
    }


def _assert_business_results_equal(db: Session, left_id, right_id) -> None:
    repository = PortfolioRepository(db)
    assert _rows(repository.list_orders(left_id)) == _rows(
        repository.list_orders(right_id)
    )
    assert _rows(repository.list_order_attempts(left_id)) == _rows(
        repository.list_order_attempts(right_id)
    )
    assert _rows(repository.list_fills(left_id)) == _rows(
        repository.list_fills(right_id)
    )
    assert _rows(repository.list_positions(left_id)) == _rows(
        repository.list_positions(right_id)
    )
    assert _rows(repository.list_nav(left_id)) == _rows(repository.list_nav(right_id))
    left_plans = list(
        db.execute(
            sa.select(PortfolioRebalancePlan)
            .where(PortfolioRebalancePlan.run_id == left_id)
            .order_by(PortfolioRebalancePlan.signal_trade_date)
        ).scalars()
    )
    right_plans = list(
        db.execute(
            sa.select(PortfolioRebalancePlan)
            .where(PortfolioRebalancePlan.run_id == right_id)
            .order_by(PortfolioRebalancePlan.signal_trade_date)
        ).scalars()
    )
    assert _rows(left_plans) == _rows(right_plans)


def _rows(rows) -> list[dict[str, object]]:
    ignored = {
        "id",
        "run_id",
        "order_id",
        "attempt_id",
        "rebalance_plan_id",
        "plan_snapshot",
        "created_at",
        "updated_at",
    }
    return [
        {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name not in ignored
        }
        for row in rows
    ]


def _cleanup(engine, days: tuple[date, ...], code: str) -> None:
    with Session(engine) as db:
        runs = list(
            db.execute(
                sa.select(PortfolioBacktestRun).where(
                    PortfolioBacktestRun.name.in_(
                        (
                            "m13.4-normal",
                            "m13.4-recovered",
                            "m13.4-preownership-recovered",
                            "m13.4-rolled-back",
                            "m13.4-open-rolled-back",
                            "m13.4-rebalance-rolled-back",
                            "m13.4-rebalance-postcommit",
                            "m13.4-source-drift",
                            "m13.4-ledger-drift",
                            "m13.4-incomplete",
                            "m13.4-concurrent",
                            "m13.4-lifecycle",
                        )
                    )
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
        sector_ids = list(
            db.execute(
                sa.select(Sector.sector_id).where(
                    Sector.source == "SW", Sector.source_code == "M134-SECTOR"
                )
            ).scalars()
        )
        db.execute(
            sa.delete(StockOpportunityDaily).where(
                StockOpportunityDaily.ts_code == code
            )
        )
        db.execute(sa.delete(StockStateDaily).where(StockStateDaily.ts_code == code))
        db.execute(
            sa.delete(StockTradeStatusDaily).where(
                StockTradeStatusDaily.ts_code == code
            )
        )
        if sector_ids:
            db.execute(
                sa.delete(SectorFactorDaily).where(
                    SectorFactorDaily.sector_id.in_(sector_ids)
                )
            )
            db.execute(
                sa.delete(SectorMember).where(
                    SectorMember.sector_id.in_(sector_ids)
                )
            )
            db.execute(sa.delete(Sector).where(Sector.sector_id.in_(sector_ids)))
        db.execute(sa.delete(StockFactorDaily).where(StockFactorDaily.ts_code == code))
        db.execute(sa.delete(MarketDaily).where(MarketDaily.trade_date.in_(days)))
        db.execute(sa.delete(StockLimitDaily).where(StockLimitDaily.ts_code == code))
        db.execute(sa.delete(StockAdjFactor).where(StockAdjFactor.ts_code == code))
        db.execute(sa.delete(StockDaily).where(StockDaily.ts_code == code))
        db.execute(sa.delete(StockBasic).where(StockBasic.ts_code == code))
        db.execute(sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_(days)))
        db.commit()
