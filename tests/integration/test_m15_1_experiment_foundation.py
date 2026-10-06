import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier

import app.services.job_worker as job_worker_module
import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
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
from app.models.portfolio import PortfolioBacktestRun
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
from app.services.experiment import (
    ExperimentApplicationError,
    ExperimentApplicationService,
)
from app.services.job_worker import execute_claimed_job
from app.services.portfolio.backtest_application import BacktestApplicationService
from sqlalchemy.orm import Session


def test_create_start_read_filter_idempotence_and_cancel_use_authoritative_runs() -> None:
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, expire_on_commit=False) as db:
            service = ExperimentApplicationService(db)
            baseline_job_count = db.scalar(
                sa.select(sa.func.count()).select_from(JobRun)
            )
            created = service.create(
                name="m15.1-foundation",
                start_date=date(2037, 1, 5),
                end_date=date(2037, 1, 9),
                initial_cash=None,
                benchmark_code=None,
                grid={"candidate.min_score": [65, 70]},
            )
            experiment_id = uuid.UUID(created["id"])
            assert created["state"] == "CREATED"
            assert created["trial_count"] == 2
            assert created["planned_count"] == 2
            assert (
                db.scalar(sa.select(sa.func.count()).select_from(JobRun))
                == baseline_job_count
            )

            started = service.start(experiment_id)
            assert started["state"] == "RUNNING"
            assert started["trial_count"] == 2
            assert started["created_count"] == 2
            first_page, total = service.trials(
                experiment_id, state="CREATED", limit=1, offset=0
            )
            assert total == 2
            assert len(first_page) == 1
            assert first_page[0]["run_status"] == "CREATED"
            run_ids = {
                row.run_id
                for row in db.execute(
                    sa.select(PortfolioExperimentTrial).where(
                        PortfolioExperimentTrial.experiment_id == experiment_id
                    )
                ).scalars()
            }
            assert None not in run_ids
            assert len(run_ids) == 2
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(JobRun)
                .where(
                    JobRun.job_metadata["portfolio_run_id"].astext.in_(
                        [str(run_id) for run_id in run_ids]
                    )
                )
            ) == 2

            repeated = service.start(experiment_id)
            assert repeated["trial_count"] == 2
            repeated_run_ids = set(
                db.execute(
                    sa.select(PortfolioExperimentTrial.run_id).where(
                        PortfolioExperimentTrial.experiment_id == experiment_id
                    )
                ).scalars()
            )
            assert repeated_run_ids == run_ids
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(JobRun)
                .where(
                    JobRun.job_metadata["portfolio_run_id"].astext.in_(
                        [str(run_id) for run_id in run_ids]
                    )
                )
            ) == 2

            cancelled = service.cancel(experiment_id)
            assert cancelled["state"] == "CANCELLED"
            assert cancelled["cancel_requested"] is True
            assert cancelled["cancelled_count"] == 2
        transaction.rollback()
    engine.dispose()


def test_source_drift_and_prestart_cancel_create_no_runs_or_jobs() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_ids: list[uuid.UUID] = []
    try:
        with Session(engine, expire_on_commit=False) as db:
            service = ExperimentApplicationService(db)
            drifted = service.create(
                name="m15.1-drift",
                start_date=date(2037, 2, 1),
                end_date=date(2037, 2, 2),
                initial_cash=None,
                benchmark_code=None,
                grid={},
            )
            drift_id = uuid.UUID(drifted["id"])
            experiment_ids.append(drift_id)
            drift_settings = get_settings().model_copy(deep=True)
            drift_settings.algo_version = "unexpected-source-version"
            with pytest.raises(ExperimentApplicationError) as caught:
                ExperimentApplicationService(db, settings=drift_settings).start(
                    drift_id
                )
            assert caught.value.code == "EXPERIMENT_SOURCE_IDENTITY_DRIFT"
            assert _experiment_run_count(db, drift_id) == 0

            cancelled = service.create(
                name="m15.1-cancel-before-start",
                start_date=date(2037, 3, 1),
                end_date=date(2037, 3, 2),
                initial_cash=None,
                benchmark_code=None,
                grid={},
            )
            cancelled_id = uuid.UUID(cancelled["id"])
            experiment_ids.append(cancelled_id)
            assert service.cancel(cancelled_id)["state"] == "CANCELLED"
            with pytest.raises(ExperimentApplicationError) as cancelled_start:
                service.start(cancelled_id)
            assert cancelled_start.value.code == "EXPERIMENT_CANCELLED"
            assert _experiment_run_count(db, cancelled_id) == 0
    finally:
        for experiment_id in experiment_ids:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_concurrent_start_materializes_and_dispatches_each_trial_once() -> None:
    engine = sa.create_engine(get_settings().database_url)
    experiment_id = None
    try:
        with Session(engine, expire_on_commit=False) as db:
            created = ExperimentApplicationService(db).create(
                name="m15.1-concurrent-start",
                start_date=date(2038, 1, 4),
                end_date=date(2038, 1, 8),
                initial_cash=None,
                benchmark_code=None,
                grid={"candidate.min_score": [65, 70]},
            )
            experiment_id = uuid.UUID(created["id"])

        barrier = Barrier(2)

        def start() -> str:
            with Session(engine, expire_on_commit=False) as contender:
                barrier.wait()
                return ExperimentApplicationService(contender).start(experiment_id)[
                    "state"
                ]

        with ThreadPoolExecutor(max_workers=2) as pool:
            states = list(pool.map(lambda _: start(), range(2)))
        assert states == ["RUNNING", "RUNNING"]

        with Session(engine) as check:
            run_ids = list(
                check.execute(
                    sa.select(PortfolioExperimentTrial.run_id)
                    .where(
                        PortfolioExperimentTrial.experiment_id == experiment_id
                    )
                    .order_by(PortfolioExperimentTrial.trial_no)
                ).scalars()
            )
            assert len(run_ids) == len(set(run_ids)) == 2
            assert None not in run_ids
            jobs = list(
                check.execute(
                    sa.select(JobRun).where(
                        JobRun.job_metadata["portfolio_run_id"].astext.in_(
                            [str(run_id) for run_id in run_ids]
                        ),
                        JobRun.status.in_(("QUEUED", "RUNNING")),
                    )
                ).scalars()
            )
            assert len(jobs) == 2
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        engine.dispose()


def test_two_trial_experiment_reaches_success_through_actual_worker_path(
    monkeypatch,
) -> None:
    engine = sa.create_engine(get_settings().database_url)
    days = (date(2090, 1, 2),)
    code = "M15101.SZ"
    experiment_id: uuid.UUID | None = None
    try:
        monkeypatch.setattr(
            job_worker_module,
            "_run_heartbeat_loop",
            lambda *args, **kwargs: None,
        )
        with Session(engine, expire_on_commit=False) as db:
            _seed_backtest_sources(db, days, code)
            created = ExperimentApplicationService(db).create(
                name="m15.1-two-trial-e2e",
                start_date=days[0],
                end_date=days[-1],
                initial_cash=None,
                benchmark_code=None,
                grid={"candidate.min_score": [65, 70]},
            )
            experiment_id = uuid.UUID(created["id"])
            ExperimentApplicationService(db).start(experiment_id)
            jobs = list(
                db.execute(
                    sa.select(JobRun)
                    .join(PortfolioBacktestRun, PortfolioBacktestRun.job_id == JobRun.id)
                    .join(
                        PortfolioExperimentTrial,
                        PortfolioExperimentTrial.run_id == PortfolioBacktestRun.id,
                    )
                    .where(
                        PortfolioExperimentTrial.experiment_id == experiment_id
                    )
                    .order_by(PortfolioExperimentTrial.trial_no)
                ).scalars()
            )
            assert len(jobs) == 2
            trials = list(
                db.execute(
                    sa.select(PortfolioExperimentTrial)
                    .where(PortfolioExperimentTrial.experiment_id == experiment_id)
                    .order_by(PortfolioExperimentTrial.trial_no)
                ).scalars()
            )
            runs = [db.get(PortfolioBacktestRun, trial.run_id) for trial in trials]
            assert [trial.parameter_values["candidate.min_score"] for trial in trials] == [
                "65",
                "70",
            ]
            assert all(run is not None for run in runs)
            first_run, second_run = runs
            assert first_run is not None and second_run is not None
            assert first_run.id != second_run.id
            assert first_run.portfolio_config_hash != second_run.portfolio_config_hash
            assert (
                first_run.source_strategy_config_hash
                == second_run.source_strategy_config_hash
            )
            assert (
                first_run.opportunity_config_hash
                == second_run.opportunity_config_hash
            )
            assert first_run.execution_config_hash == second_run.execution_config_hash
            assert first_run.accounting_config_hash == second_run.accounting_config_hash
            assert first_run.portfolio_version == second_run.portfolio_version == "portfolio_v3"
            assert (
                first_run.backtest_engine_version
                == second_run.backtest_engine_version
                == "backtest_v7"
            )
            assert (
                first_run.start_date,
                first_run.end_date,
                first_run.initial_cash,
                first_run.benchmark_code,
            ) == (
                second_run.start_date,
                second_run.end_date,
                second_run.initial_cash,
                second_run.benchmark_code,
            )
            assert {
                key: value
                for key, value in first_run.config_snapshot.items()
                if key != "portfolio"
            } == {
                key: value
                for key, value in second_run.config_snapshot.items()
                if key != "portfolio"
            }
            first_portfolio = dict(first_run.config_snapshot["portfolio"])
            second_portfolio = dict(second_run.config_snapshot["portfolio"])
            assert first_portfolio.pop("candidate")["min_score"] == "65"
            assert second_portfolio.pop("candidate")["min_score"] == "70"
            first_candidate = dict(first_run.config_snapshot["portfolio"]["candidate"])
            second_candidate = dict(second_run.config_snapshot["portfolio"]["candidate"])
            first_candidate.pop("min_score")
            second_candidate.pop("min_score")
            assert first_candidate == second_candidate
            assert first_portfolio == second_portfolio
            original_job_ids = {job.id for job in jobs}
            for index, job in enumerate(jobs, start=1):
                job.status = "RUNNING"
                job.worker_id = f"m15.1-e2e-worker-{index}"
                job.heartbeat_at = datetime.now(UTC)
                db.commit()
                execute_claimed_job(db, job.id)

            detail = ExperimentApplicationService(db).get(experiment_id)
            assert detail["state"] == "SUCCESS"
            assert detail["success_count"] == 2
            assert detail["terminal_count"] == 2
            assert detail["progress_pct"] == 100.0
            repeated = ExperimentApplicationService(db).start(experiment_id)
            assert repeated["state"] == "SUCCESS"
            repeated_jobs = list(
                db.execute(
                    sa.select(JobRun).where(
                        JobRun.job_metadata["portfolio_run_id"].astext.in_(
                            [str(run.id) for run in runs if run is not None]
                        )
                    )
                ).scalars()
            )
            assert {job.id for job in repeated_jobs} == original_job_ids
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        _cleanup_backtest_sources(engine, days, code)
        engine.dispose()


def test_m13_manual_resume_is_observed_dynamically_by_experiment(monkeypatch) -> None:
    engine = sa.create_engine(get_settings().database_url)
    days = (date(2091, 1, 3),)
    code = "M151R1.SZ"
    experiment_id: uuid.UUID | None = None
    try:
        monkeypatch.setattr(
            job_worker_module,
            "_run_heartbeat_loop",
            lambda *args, **kwargs: None,
        )
        with Session(engine, expire_on_commit=False) as db:
            _seed_backtest_sources(db, days, code)
            created = ExperimentApplicationService(db).create(
                name="m15.1.1-manual-resume",
                start_date=days[0],
                end_date=days[-1],
                initial_cash=None,
                benchmark_code=None,
                grid={},
            )
            experiment_id = uuid.UUID(created["id"])
            ExperimentApplicationService(db).start(experiment_id)
            trial = db.execute(
                sa.select(PortfolioExperimentTrial).where(
                    PortfolioExperimentTrial.experiment_id == experiment_id
                )
            ).scalar_one()
            assert trial.run_id is not None
            run = db.get(PortfolioBacktestRun, trial.run_id)
            assert run is not None and run.job_id is not None
            failed_job = db.get(JobRun, run.job_id)
            assert failed_job is not None
            now = datetime.now(UTC)
            run.status = "FAILED"
            run.finished_at = now
            failed_job.status = "FAILED"
            failed_job.finished_at = now
            failed_job.error_message = "injected recoverable failure"
            db.commit()

            resumed_run, resumed_job = BacktestApplicationService(db).resume(run.id)
            assert resumed_run.id == run.id
            assert resumed_job.id != failed_job.id
            resumed_job.status = "RUNNING"
            resumed_job.worker_id = "m15.1.1-resume-worker"
            resumed_job.heartbeat_at = datetime.now(UTC)
            db.commit()

            execute_claimed_job(db, resumed_job.id)

            detail = ExperimentApplicationService(db).get(experiment_id)
            trial_detail = ExperimentApplicationService(db).trial(
                experiment_id, trial.id
            )
            assert trial_detail["state"] == "SUCCESS"
            assert detail["state"] == "SUCCESS"
            assert detail["success_count"] == 1
            assert detail["terminal_count"] == 1
            assert detail["progress_pct"] == 100.0
            generations = list(
                db.execute(
                    sa.select(JobRun).where(
                        JobRun.job_metadata["portfolio_run_id"].astext
                        == str(run.id)
                    )
                ).scalars()
            )
            assert len(generations) == 2
    finally:
        if experiment_id is not None:
            _cleanup_experiment(engine, experiment_id)
        _cleanup_backtest_sources(engine, days, code)
        engine.dispose()


def _experiment_run_count(db: Session, experiment_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            sa.select(sa.func.count(PortfolioExperimentTrial.run_id)).where(
                PortfolioExperimentTrial.experiment_id == experiment_id,
                PortfolioExperimentTrial.run_id.is_not(None),
            )
        )
        or 0
    )


def _cleanup_experiment(engine: sa.Engine, experiment_id: uuid.UUID) -> None:
    with Session(engine) as db:
        run_ids = list(
            db.execute(
                sa.select(PortfolioExperimentTrial.run_id).where(
                    PortfolioExperimentTrial.experiment_id == experiment_id,
                    PortfolioExperimentTrial.run_id.is_not(None),
                )
            ).scalars()
        )
        job_ids = list(
            db.execute(
                sa.select(JobRun.id).where(
                    JobRun.job_metadata["portfolio_run_id"].astext.in_(
                        [str(run_id) for run_id in run_ids]
                    )
                )
            ).scalars()
        )
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


def _seed_backtest_sources(
    db: Session, days: tuple[date, ...], code: str
) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    sector = Sector(
        source="SW",
        source_code="M151-E2E-SECTOR",
        name="M15.1 E2E Sector",
        level="L1",
        is_active=True,
    )
    db.add(sector)
    db.flush()
    db.add_all(
        [
            StockBasic(
                ts_code=code,
                symbol="M15101",
                name="M15.1 E2E",
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
                    opportunity_score=85,
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
                    opportunity_score=85,
                    calc_version=OPPORTUNITY_CALC_VERSION,
                    config_hash=opportunity_hash,
                    source_strategy_config_hash=strategy_hash,
                    calculated_at=now,
                ),
            ]
        )
    db.commit()


def _cleanup_backtest_sources(
    engine: sa.Engine, days: tuple[date, ...], code: str
) -> None:
    with Session(engine) as db:
        sector_ids = list(
            db.execute(
                sa.select(Sector.sector_id).where(
                    Sector.source == "SW",
                    Sector.source_code == "M151-E2E-SECTOR",
                )
            ).scalars()
        )
        for model in (
            StockOpportunityDaily,
            StockStateDaily,
            StockTradeStatusDaily,
            StockFactorDaily,
            StockLimitDaily,
            StockAdjFactor,
            StockDaily,
        ):
            db.execute(sa.delete(model).where(model.ts_code == code))
        db.execute(sa.delete(MarketDaily).where(MarketDaily.trade_date.in_(days)))
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
        db.execute(sa.delete(StockBasic).where(StockBasic.ts_code == code))
        db.execute(sa.delete(TradeCalendar).where(TradeCalendar.cal_date.in_(days)))
        db.commit()
