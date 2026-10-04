from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models.job import JobRun
from app.models.performance_trade import (
    PortfolioPerformanceTradeDaily,
    PortfolioPerformanceTradeEpisode,
    PortfolioPerformanceTradeReport,
)
from app.models.portfolio import (
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrderAttempt,
    PortfolioPositionDaily,
)
from app.repositories.performance_trade import PerformanceTradeRepository
from app.services.auth.dependencies import require_authenticated_user
from app.services.job_worker import execute_claimed_job
from app.services.performance.trade_application import PerformanceTradeApplicationService
from app.services.performance.trade_source import PerformanceTradeSourceError
from fastapi.testclient import TestClient
from m14_3_support import cleanup_trade_case, seed_trade_case
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def test_postgresql_trade_e2e_reconciles_closed_open_cost_and_turnover() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2045, 1, day) for day in range(4, 11))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_trade_case(db, dates)
            artifact = PerformanceTradeApplicationService(db).calculate_now(
                case.run_id, case.performance_id
            )
            report = artifact.report
            daily = list(
                db.scalars(
                    select(PortfolioPerformanceTradeDaily)
                    .where(PortfolioPerformanceTradeDaily.trade_id == report.id)
                    .order_by(PortfolioPerformanceTradeDaily.trade_date)
                )
            )
            episodes = list(
                db.scalars(
                    select(PortfolioPerformanceTradeEpisode)
                    .where(PortfolioPerformanceTradeEpisode.trade_id == report.id)
                    .order_by(PortfolioPerformanceTradeEpisode.ts_code)
                )
            )

            assert artifact.reused is False
            assert len(daily) == report.trade_days == 7
            assert {(row.ts_code, row.status) for row in episodes} == {
                ("000001.SZ", "CLOSED"),
                ("000002.SZ", "CLOSED"),
                ("000003.SZ", "OPEN"),
            }
            by_code = {row.ts_code: row for row in episodes}
            assert by_code["000001.SZ"].realized_pnl == Decimal("-54.0000")
            assert by_code["000002.SZ"].realized_pnl == Decimal("98.0000")
            assert by_code["000003.SZ"].unrealized_pnl_end == Decimal("49.0000")
            assert report.closed_episode_count == 2
            assert report.open_episode_count == 1
            assert report.win_count == report.loss_count == 1
            assert report.closed_realized_pnl == Decimal("44.0000")
            assert report.open_unrealized_pnl_end == Decimal("49.0000")
            assert report.fill_count == sum(row.fill_count for row in daily)
            assert report.fill_count == sum(row.fill_count for row in episodes)
            assert report.traded_gross_amount == sum(
                (row.traded_gross_amount for row in daily), Decimal("0")
            )
            assert (
                report.total_execution_cost
                == sum((row.total_execution_cost for row in daily), Decimal("0"))
                == sum((row.total_execution_cost for row in episodes), Decimal("0"))
            )
            assert report.cash_fee_total == sum((row.cash_fee_total for row in daily), Decimal("0"))
            assert daily[0].turnover_denominator == Decimal("1000000.0000")
            assert all(row.turnover_denominator == Decimal("1000000.0000") for row in daily[1:])
            assert daily[-1].fill_count == 0
            assert daily[-1].daily_turnover == 0
        transaction.rollback()


def test_trade_identity_reuses_then_versions_valid_source_revision() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2045, 2, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_trade_case(db, dates)
            service = PerformanceTradeApplicationService(db)
            first = service.calculate_now(case.run_id, case.performance_id)
            second = service.calculate_now(case.run_id, case.performance_id)
            assert first.reused is False
            assert second.reused is True
            assert second.report.id == first.report.id

            fill = db.get(PortfolioFill, case.fill_ids[0])
            attempt = db.get(PortfolioOrderAttempt, fill.attempt_id)
            nav = db.get(PortfolioNavDaily, (case.run_id, dates[0]))
            fill.reference_price = Decimal("9.9900")
            fill.slippage_cost = Decimal("1.0000")
            fill.total_cost = Decimal("2.0000")
            attempt.reference_price = fill.reference_price
            attempt.slippage_cost = fill.slippage_cost
            attempt.total_cost = fill.total_cost
            nav.trading_cost = Decimal("2.0000")
            db.flush()

            revised = service.calculate_now(case.run_id, case.performance_id)
            assert revised.reused is False
            assert revised.report.id != first.report.id
            assert revised.report.trade_source_hash != first.report.trade_source_hash
            assert revised.report.slippage_cost_total == Decimal("1.0000")
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioPerformanceTradeReport)
                    .where(PortfolioPerformanceTradeReport.performance_id == case.performance_id)
                )
                == 2
            )
            old_daily_cost = db.scalar(
                select(PortfolioPerformanceTradeDaily.total_execution_cost).where(
                    PortfolioPerformanceTradeDaily.trade_id == first.report.id,
                    PortfolioPerformanceTradeDaily.trade_date == dates[0],
                )
            )
            assert old_daily_cost == Decimal("1.0000")
        transaction.rollback()


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("avg_cost", Decimal("999"), "TRADE_POSITION_REPLAY_MISMATCH"),
        ("realized_pnl", Decimal("999"), "TRADE_POSITION_REPLAY_MISMATCH"),
    ],
)
def test_trade_position_replay_mismatch_leaves_no_artifact(
    field: str, value: Decimal, expected_code: str
) -> None:
    engine = sa.create_engine(get_settings().database_url)
    day_offset = 1 if field == "avg_cost" else 10
    dates = tuple(date(2045, 3, day_offset + index) for index in range(7))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_trade_case(db, dates)
            position = db.get(PortfolioPositionDaily, (case.run_id, dates[0], "000001.SZ"))
            setattr(position, field, value)
            db.flush()
            with pytest.raises(Exception) as exc_info:
                PerformanceTradeApplicationService(db).calculate_now(
                    case.run_id, case.performance_id
                )
            assert getattr(exc_info.value, "code", None) == expected_code
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioPerformanceTradeReport)
                    .where(PortfolioPerformanceTradeReport.performance_id == case.performance_id)
                )
                == 0
            )
        transaction.rollback()


def test_trade_daily_cost_mismatch_fails_before_persistence() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2045, 4, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_trade_case(db, dates)
            nav = db.get(PortfolioNavDaily, (case.run_id, dates[0]))
            nav.trading_cost = Decimal("999")
            db.flush()
            with pytest.raises(PerformanceTradeSourceError) as exc_info:
                PerformanceTradeApplicationService(db).calculate_now(
                    case.run_id, case.performance_id
                )
            assert exc_info.value.code == "TRADE_DAILY_COST_MISMATCH"
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioPerformanceTradeReport)
                    .where(PortfolioPerformanceTradeReport.performance_id == case.performance_id)
                )
                == 0
            )
        transaction.rollback()


def test_trade_report_daily_episode_persistence_is_atomic() -> None:
    class FailingRepository(PerformanceTradeRepository):
        def add_episodes(self, rows):
            raise RuntimeError("injected episode persistence failure")

    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2045, 5, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_trade_case(db, dates)
            savepoint = db.begin_nested()
            with pytest.raises(RuntimeError, match="injected"):
                PerformanceTradeApplicationService(
                    db, repository=FailingRepository(db)
                ).calculate_now(case.run_id, case.performance_id)
            savepoint.rollback()
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioPerformanceTradeReport)
                    .where(PortfolioPerformanceTradeReport.performance_id == case.performance_id)
                )
                == 0
            )
            assert db.scalar(select(func.count()).select_from(PortfolioPerformanceTradeDaily)) == 0
            assert (
                db.scalar(select(func.count()).select_from(PortfolioPerformanceTradeEpisode)) == 0
            )
        transaction.rollback()


def test_database_rejects_cross_owner_trade_daily_and_episode_rows() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates_a = tuple(date(2045, 6, day) for day in range(1, 8))
    dates_b = tuple(date(2045, 6, day) for day in range(11, 18))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case_a = seed_trade_case(db, dates_a)
            case_b = seed_trade_case(db, dates_b)
            source = (
                PerformanceTradeApplicationService(db)
                .calculate_now(case_a.run_id, case_a.performance_id)
                .report
            )
            values = {
                column.name: getattr(source, column.name)
                for column in source.__table__.columns
                if column.name not in {"id", "calculated_at", "created_at", "updated_at"}
            }
            values["trade_source_hash"] = "f" * 64
            empty = PortfolioPerformanceTradeReport(**values)
            db.add(empty)
            db.flush()

            daily_source = db.scalar(
                select(PortfolioPerformanceTradeDaily).where(
                    PortfolioPerformanceTradeDaily.trade_id == source.id
                )
            )
            daily_values = {
                column.name: getattr(daily_source, column.name)
                for column in daily_source.__table__.columns
                if column.name != "created_at"
            }
            daily_values.update(
                trade_id=empty.id,
                performance_id=case_a.performance_id,
                run_id=case_b.run_id,
            )
            savepoint = db.begin_nested()
            db.add(PortfolioPerformanceTradeDaily(**daily_values))
            with pytest.raises(sa.exc.IntegrityError):
                db.flush()
            savepoint.rollback()

            episode_source = db.scalar(
                select(PortfolioPerformanceTradeEpisode).where(
                    PortfolioPerformanceTradeEpisode.trade_id == source.id
                )
            )
            episode_values = {
                column.name: getattr(episode_source, column.name)
                for column in episode_source.__table__.columns
                if column.name != "created_at"
            }
            episode_values.update(
                trade_id=empty.id,
                performance_id=case_a.performance_id,
                run_id=case_b.run_id,
            )
            savepoint = db.begin_nested()
            db.add(PortfolioPerformanceTradeEpisode(**episode_values))
            with pytest.raises(sa.exc.IntegrityError):
                db.flush()
            savepoint.rollback()
        transaction.rollback()


def test_postgresql_trade_api_calculate_report_daily_and_episode_pagination() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2045, 7, day) for day in range(1, 8))
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as db:
            case = seed_trade_case(db, dates)
            PerformanceTradeApplicationService(db).calculate_now(
                case.run_id, case.performance_id
            )
            app.dependency_overrides[require_authenticated_user] = (
                lambda: SimpleNamespace(username="trade-api-test")
            )
            app.dependency_overrides[get_db] = lambda: db
            try:
                client = TestClient(app)
                queued = client.post(
                    f"/api/v1/portfolio/backtests/{case.run_id}"
                    "/performance/trade/calculate",
                    json={"performance_id": str(case.performance_id)},
                )
                report = client.get(
                    f"/api/v1/portfolio/backtests/{case.run_id}/performance/trade",
                    params={"performance_id": str(case.performance_id)},
                )
                daily = client.get(
                    f"/api/v1/portfolio/backtests/{case.run_id}"
                    "/performance/trade/daily",
                    params={
                        "performance_id": str(case.performance_id),
                        "limit": 2,
                        "offset": 1,
                    },
                )
                episodes = client.get(
                    f"/api/v1/portfolio/backtests/{case.run_id}"
                    "/performance/trade/episodes",
                    params={
                        "performance_id": str(case.performance_id),
                        "status": "CLOSED",
                        "limit": 1,
                        "offset": 0,
                    },
                )
            finally:
                app.dependency_overrides.clear()

            assert queued.status_code == 202
            assert queued.json()["data"]["trade_version"] == "trade_v1"
            assert report.status_code == 200
            assert report.json()["data"]["closed_episode_count"] == 2
            assert daily.status_code == 200
            assert len(daily.json()["data"]) == 2
            assert daily.json()["meta"]["total"] == 7
            assert daily.json()["meta"]["offset"] == 1
            assert episodes.status_code == 200
            assert len(episodes.json()["data"]) == 1
            assert episodes.json()["meta"]["total"] == 2
            assert episodes.json()["meta"]["status"] == "CLOSED"
        transaction.rollback()


def test_invalid_trade_source_fails_worker_without_partial_artifact() -> None:
    engine = sa.create_engine(get_settings().database_url)
    dates = tuple(date(2045, 8, day) for day in range(1, 8))
    with Session(engine) as db:
        case = seed_trade_case(db, dates)
        nav = db.get(PortfolioNavDaily, (case.run_id, dates[0]))
        nav.trading_cost = Decimal("999")
        job = PerformanceTradeApplicationService(db).queue_calculation(
            case.run_id, case.performance_id
        )
        job.status = "RUNNING"
        job.worker_id = "trade-test-worker"
        job.heartbeat_at = datetime.now(UTC)
        db.commit()
        job_id = job.id

    try:
        with Session(engine) as db:
            execute_claimed_job(db, job_id)
        with Session(engine) as db:
            failed = db.get(JobRun, job_id)
            assert failed.status == "FAILED"
            assert failed.job_metadata["error_code"] == "TRADE_DAILY_COST_MISMATCH"
            assert db.scalar(
                select(func.count())
                .select_from(PortfolioPerformanceTradeReport)
                .where(
                    PortfolioPerformanceTradeReport.performance_id
                    == case.performance_id
                )
            ) == 0
    finally:
        cleanup_trade_case(engine, case)
