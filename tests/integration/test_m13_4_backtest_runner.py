from datetime import UTC, date, datetime, timedelta

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
    BacktestRunner,
    recover_stale_backtest_jobs,
)
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
                rolled_back = PortfolioApplicationService(
                    db
                ).create_backtest_definition(
                    start_date=days[0], end_date=days[-1], name="m13.4-rolled-back"
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
                stale_run, stale_job = BacktestApplicationService(db).resume(
                    lifecycle.id
                )
                _claim(db, stale_job, "worker-stale")
                stale_run.status = "RUNNING"
                stale_run.owner_worker_id = "worker-stale"
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

                normal_job = _enqueue_and_claim(db, normal.id, "worker-normal")
                with pytest.raises(BacktestConflictError):
                    BacktestApplicationService(db).execute(normal.id)
                BacktestRunner(db).run_job(normal_job.id)

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

                db.expire_all()
                normal_run = db.get(PortfolioBacktestRun, normal.id)
                recovered_run = db.get(PortfolioBacktestRun, recovered.id)
                rolled_back_run = db.get(PortfolioBacktestRun, rolled_back.id)
                assert normal_run is not None and normal_run.status == "SUCCESS"
                assert recovered_run is not None and recovered_run.status == "SUCCESS"
                assert rolled_back_run is not None
                assert rolled_back_run.status == "SUCCESS"
                _assert_complete_protocol(db, normal.id, days)
                _assert_complete_protocol(db, recovered.id, days)
                _assert_business_results_equal(db, normal.id, recovered.id)
                _assert_business_results_equal(db, normal.id, rolled_back.id)

                recovered_positions = PortfolioRepository(db).list_position_snapshot(
                    recovered.id, days[-1]
                )
                assert recovered_positions == []
                assert len(PortfolioRepository(db).list_nav(recovered.id)) == 5
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
                            "m13.4-rolled-back",
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
