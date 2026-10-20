from datetime import date, timedelta

import pytest
from app.api.v1.jobs import RecalculateJobRequest, enqueue_recalculate_job
from app.models.data_publication import DataPublication, DataPublicationRow
from app.models.job import JobRun
from app.models.market_data import TradeCalendar
from app.services.job_guard import create_queued_ingestion_job
from app.services.job_worker import claim_next_job, execute_claimed_job
from app.services.trading_calendar_guard import TradingCalendarError, require_recalculation_days
from fastapi import HTTPException
from sqlalchemy import func, select

from scripts.v14_test_database import isolated_v14_database


@pytest.fixture
def database(monkeypatch):
    with isolated_v14_database(monkeypatch) as value:
        yield value


@pytest.mark.parametrize("start,flags,expected", [
    (date(2025, 2, 1), [False]*4, "NO_TRADING_DAYS"),
    (date(2025, 2, 8), [False, False], "NO_TRADING_DAYS"),
    (date(2025, 2, 4), [False, True], None),
    (date(2024, 12, 31), [True, False, True], None),
    (date(2025, 2, 5), [True], None),  # any open session, including half day
    (date(2025, 2, 1), [], "TRADE_CALENDAR_UNVERIFIED"),
])
def test_complete_calendar_not_price_presence(database, start, flags, expected):
    factory, _ = database
    end = start + timedelta(days=max(len(flags), 1)-1)
    with factory() as db:
        db.add_all(TradeCalendar(cal_date=start+timedelta(days=i), is_open=flag)
                   for i, flag in enumerate(flags))
        db.commit()
        if expected:
            with pytest.raises(TradingCalendarError, match=expected):
                require_recalculation_days(db, start, end)
            with pytest.raises(HTTPException) as error:
                enqueue_recalculate_job(RecalculateJobRequest(start=start, end=end), db)
            assert error.value.status_code == 422
            assert error.value.detail == {"code": expected}
            assert db.scalar(select(func.count()).select_from(JobRun)) == 0
        else:
            assert require_recalculation_days(db, start, end) == tuple(
                start+timedelta(days=i) for i, flag in enumerate(flags) if flag)


def test_partial_calendar_and_reverse_range_refused(database):
    factory, _ = database
    with factory() as db:
        day = date(2025, 2, 1)
        db.add(TradeCalendar(cal_date=day, is_open=False))
        db.commit()
        with pytest.raises(TradingCalendarError, match="TRADE_CALENDAR_UNVERIFIED"):
            require_recalculation_days(db, day, day+timedelta(days=1))
        with pytest.raises(HTTPException) as error:
            enqueue_recalculate_job(RecalculateJobRequest(start=day, end=date(2025, 1, 31)), db)
        assert error.value.status_code == 400


@pytest.mark.parametrize("has_calendar,code", [
    (True, "NO_TRADING_DAYS"), (False, "TRADE_CALENDAR_UNVERIFIED"),
])
def test_worker_rejects_old_queue_before_workspace(database, monkeypatch, has_calendar, code):
    factory, _ = database
    monkeypatch.setattr("app.services.job_worker.SessionLocal", factory)
    with factory() as db:
        day = date(2025, 2, 1)
        if has_calendar:
            db.add(TradeCalendar(cal_date=day, is_open=False))
            db.commit()
        job = create_queued_ingestion_job(db, "recalculate", day, step="queued", metadata={
            "start": str(day), "end": str(day), "evaluate_signals": False})
        assert claim_next_job(db, "v14-test") == job.id
        db.refresh(job)
        execute_claimed_job(db, job.id, expected_worker=job.worker_id,
                           expected_token=job.execution_token)
        db.expire_all()
        assert db.get(JobRun, job.id).status == "FAILED"
        assert db.get(JobRun, job.id).error_message == code
        assert db.scalar(select(func.count()).select_from(DataPublication)) == 0
        assert db.scalar(select(func.count()).select_from(DataPublicationRow)) == 0
