"""Real PG17 regressions for the opt-in business read optimization."""

from dataclasses import asdict
from datetime import date, timedelta

import pytest
from app.core.config import get_settings
from app.models import market_data as m
from app.repositories.upsert import upsert_rows
from app.services.factors.input_window import FactorInputWindow
from app.services.factors.service import FactorService
from app.services.quality.raw_completeness import check_raw_completeness
from app.services.quality.raw_range import check_raw_range
from pandas.testing import assert_frame_equal
from sqlalchemy import event, insert, text, update

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_data_publication import candidate, sample_row


@pytest.fixture
def isolated(monkeypatch):
    with isolated_v14_database(monkeypatch) as database:
        yield database


def seed(factory, *, include_closed=True, history_days=40):
    days = [date(2025, 1, 1) + timedelta(days=i) for i in range(history_days)]
    with factory() as db:
        db.execute(insert(m.StockBasic), [dict(ts_code="000001.SZ", list_date=days[0],
            exchange="SZSE", list_status="L"), dict(ts_code="000002.SZ", list_date=days[10],
            delist_date=days[25], exchange="SZSE", list_status="D")])
        db.execute(insert(m.TradeCalendar), [
            dict(cal_date=d, is_open=d.weekday() < 5) for d in days])
        db.add(m.Sector(sector_id=101, source="SW", source_code="BIZ",
                        name="synthetic", level="L1"))
        db.flush()
        db.add(m.SectorMember(sector_id=101, ts_code="000001.SZ", valid_from=days[0]))
        for day in days:
            if not include_closed and day.weekday() >= 5:
                continue
            for code in ["000001.SZ", "000002.SZ"]:
                db.add(m.StockDaily(trade_date=day, ts_code=code, close=20,
                    open=20, high=21, low=19, vol=100000, amount=1000000))
                db.add(m.StockAdjFactor(trade_date=day, ts_code=code, adj_factor=1))
                db.add(m.StockDailyBasic(trade_date=day, ts_code=code,
                    close=20, total_mv=100, circ_mv=100))
                db.add(m.StockLimitDaily(trade_date=day, ts_code=code, up_limit=22, down_limit=18))
            for code in get_settings().strategy["benchmark"]["market_indices"]:
                db.add(m.IndexDaily(trade_date=day, ts_code=code, close=100, pre_close=100))
            for dataset in ("stock_st", "suspend_d"):
                db.add(m.DataQualityDaily(trade_date=day, dataset=dataset,
                                          status="PASS", expected_rows=0, actual_rows=0))
        db.commit()
    return days


@pytest.mark.parametrize("case", range(10))
def test_batched_raw_preflight_matches_every_field_and_reduces_queries(isolated, case):
    factory, engine = isolated
    days = seed(factory)
    day = days[15]
    with factory() as db:
        if case == 1:
            db.execute(m.StockDaily.__table__.delete().where(m.StockDaily.trade_date == day))
        elif case == 2:
            db.execute(update(m.StockAdjFactor).where(m.StockAdjFactor.trade_date == day)
                       .values(adj_factor=-1))
        elif case == 3:
            db.execute(update(m.StockDailyBasic).where(m.StockDailyBasic.trade_date == day)
                       .values(close=None))
        elif case == 4:
            db.execute(update(m.IndexDaily).where(m.IndexDaily.trade_date == day)
                       .values(pre_close=None))
        elif case == 5:
            db.execute(m.DataQualityDaily.__table__.delete().where(
                m.DataQualityDaily.trade_date == day, m.DataQualityDaily.dataset == "stock_st"))
        elif case == 6:
            db.add(m.StockSuspendDaily(trade_date=day, ts_code="000001.SZ", suspend_type="S"))
        elif case == 7:
            db.execute(update(m.DataQualityDaily).where(m.DataQualityDaily.trade_date == day,
                m.DataQualityDaily.dataset == "suspend_d").values(status="WARNING"))
        elif case == 8:
            db.execute(update(m.StockLimitDaily).where(m.StockLimitDaily.trade_date == days[0])
                       .values(up_limit=0, down_limit=0))
        elif case == 9:
            db.add(m.DataQualityDaily(trade_date=day, dataset="stk_limit", status="WARNING",
                                      issue_codes={"source_warnings": ["synthetic"]}))
        db.commit()
    counts = []

    def count(*args):
        counts.append(1)

    event.listen(engine, "before_cursor_execute", count)
    try:
        with factory() as db:
            expected = [asdict(check_raw_completeness(db, d, strategy=get_settings().strategy))
                        for d in days]
            old_count = len(counts)
            counts.clear()
            actual = [asdict(row) for row in check_raw_range(db, days,
                                                            strategy=get_settings().strategy)]
            assert actual == expected
            assert len(counts) < old_count / 4
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_input_window_preserves_full_frame_dtypes_and_detects_source_change(isolated):
    factory, engine = isolated
    days = seed(factory)
    with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
        service = FactorService(db)
        window = FactorInputWindow(db, job.id, get_settings())
        for lo, hi in ((days[0], days[30]), (days[10], days[-1])):
            window.prepare(lo, hi)
            for method in ("_read_daily", "_read_adj_factor", "_read_trade_status",
                           "_read_index_daily", "_read_stock_basic"):
                reader = getattr(service, method)
                values = () if method == "_read_stock_basic" else (lo, hi)
                baseline = reader(*values)
                service.input_window = window
                actual = reader(*values)
                if not actual.empty:
                    order = [c for c in ("ts_code", "trade_date") if c in actual]
                    actual = actual.sort_values(order).reset_index(drop=True)
                    baseline = baseline.sort_values(order).reset_index(drop=True)
                assert_frame_equal(actual, baseline, check_exact=True)
                service.input_window = None
            db.commit()
        db.execute(update(m.StockDaily).where(m.StockDaily.trade_date == days[5]).values(close=25))
        db.commit()
        with pytest.raises(ValueError, match="FACTOR_INPUT_SOURCE_CHANGED"):
            window.prepare(days[10], days[-1])
        window.close()
        assert not window.entries


def test_input_window_status_overlay_tombstone_and_root_identity(isolated):
    from app.models.job import JobRun

    factory, engine = isolated
    days = seed(factory)
    with factory() as db:
        old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
        db.add(old)
        db.flush()
        for day in days:
            row = sample_row(m.StockTradeStatusDaily, old.id, day=day)
            row.update(ts_code="000001.SZ", is_st=False, st_status_unknown=False)
            upsert_rows(db, m.StockTradeStatusDaily, [row], ["trade_date", "ts_code"])
        db.commit()
    with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
        root = db.info["publication_workspace"]
        payload = sample_row(m.StockTradeStatusDaily, job.id, day=days[15])
        payload.update(ts_code="000001.SZ", is_st=True)
        upsert_rows(db, m.StockTradeStatusDaily, [payload], ["trade_date", "ts_code"])
        root.delete_keys(m.StockTradeStatusDaily, [(days[20], "000001.SZ")])
        db.commit()
        service = FactorService(db)
        window = FactorInputWindow(db, job.id, get_settings())
        for lo, hi in ((days[0], days[30]), (days[10], days[-1])):
            window.prepare(lo, hi)
            baseline = service._read_trade_status(lo, hi)
            service.input_window = window
            actual = service._read_trade_status(lo, hi)
            for frame in (baseline, actual):
                frame.sort_values(["ts_code", "trade_date"], inplace=True, ignore_index=True)
            assert_frame_equal(actual, baseline, check_exact=True)
            assert days[20] not in set(actual.trade_date)
            assert actual.loc[actual.trade_date == days[15], "is_st"].item()
            service.input_window = None
            db.commit()
        db.info["calculation_job_id"] = old.id
        with pytest.raises(ValueError, match="IDENTITY_CHANGED"):
            window.prepare(days[10], days[-1])
        assert window.closed and not window.entries
        db.info["calculation_job_id"] = job.id


def test_input_window_memory_failure_closes_cursor_without_partial_frame(isolated):
    factory, engine = isolated
    days = seed(factory)
    with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
        service = FactorService(db)
        window = FactorInputWindow(db, job.id, get_settings(), max_bytes=1)
        service.input_window = window
        window.prepare(days[0], days[-1])
        with pytest.raises(MemoryError, match="FACTOR_INPUT_MEMORY_BUDGET_EXCEEDED"):
            service._read_daily(days[0], days[-1])
        assert window.closed and not window.entries
        assert not db.execute(text(
            "SELECT name FROM pg_cursors WHERE name LIKE 'c_%'"
        )).all()


def test_raw_preflight_rejects_unbounded_window():
    from app.services.quality.raw_range import RawRangeFacts

    with pytest.raises(ValueError, match="UNBOUNDED"):
        RawRangeFacts(None, date(2025, 1, 1), date(2025, 3, 1))


def test_new_read_paths_are_off_by_default():
    from app.core.config import Settings

    settings = Settings(_env_file=None)
    assert not settings.factor_input_reuse_enabled
    assert not settings.raw_preflight_batch_enabled
    assert not settings.factor_cpu_optimization_enabled
    assert not settings.ab_merge_read_enabled


def test_final_source_verification_uses_original_publication_budget(isolated):
    factory, engine = isolated
    days = seed(factory)
    with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
        window = FactorInputWindow(db, job.id, get_settings())
        window.prepare(days[0], days[-1])
        window.close()
        charges = []
        window.verify(publish_budget=lambda: charges.append(1))
        assert len(charges) == 7  # SHARE lock, five public scans, candidate scan.

        def exhausted():
            raise ValueError("PUBLICATION_TIME_BUDGET_EXCEEDED")

        with pytest.raises(ValueError, match="PUBLICATION_TIME_BUDGET_EXCEEDED"):
            window.verify(publish_budget=exhausted)


def test_cached_inputs_require_reverification_after_checkpoint_commit(isolated):
    factory, engine = isolated
    days = seed(factory)
    with candidate(factory, engine, start=days[0], end=days[-1]) as (db, job):
        service = FactorService(db)
        window = FactorInputWindow(db, job.id, get_settings())
        service.input_window = window
        window.prepare(days[0], days[-1])
        service._read_daily(days[0], days[-1])
        db.commit()
        with pytest.raises(ValueError, match="FACTOR_INPUT_WINDOW_NOT_PREPARED"):
            service._read_daily(days[0], days[-1])
        assert window.closed and not window.entries


@pytest.mark.parametrize("outcome", ["publish", "cancel", "source_change", "memory"])
def test_opt_in_real_worker_financial_quality_and_atomic_terminal_state(
    isolated, monkeypatch, outcome, request,
):
    from app.models.data_publication import DataPublication
    from app.models.job import JobRun
    from app.services import job_worker
    from app.services.recalculation import create_recalculation_job
    from sqlalchemy import func, select

    factory, engine = isolated
    days = seed(factory, include_closed=False, history_days=420)
    settings = get_settings()
    for field in ("factor_input_reuse_enabled", "factor_cpu_optimization_enabled",
                  "raw_preflight_batch_enabled"):
        monkeypatch.setattr(settings, field, True)
    monkeypatch.setattr(job_worker, "SessionLocal", factory)
    original = FactorService.recalc

    def real_calculation_with_fault(service, start, end, calc_run_id=None):
        count = original(service, start, end, calc_run_id=calc_run_id)
        if end == days[-1] and outcome != "publish":
            if outcome == "memory":
                raise MemoryError("PRIVATE_SYNTHETIC_BATCH_SENTINEL")
            with factory() as observer:
                if outcome == "cancel":
                    observer.execute(update(JobRun).where(JobRun.id == calc_run_id)
                                     .values(cancel_requested=True))
                else:
                    observer.execute(update(m.StockDaily).where(
                        m.StockDaily.trade_date == days[15]).values(vol=100001))
                observer.commit()
        return count

    monkeypatch.setattr(FactorService, "recalc", real_calculation_with_fault)
    messages = []
    sink = job_worker.logger.add(lambda message: messages.append(str(message)), format="{message}")
    request.addfinalizer(lambda: job_worker.logger.remove(sink))
    with factory() as db:
        job = create_recalculation_job(db, start=days[-30], end=days[-1],
                                      evaluate_signals=False, mode="manual")
        assert job_worker.claim_next_job(db, "biz-perf-regression") == job.id
        db.refresh(job)
        job_worker.execute_claimed_job(db, job.id, expected_worker=job.worker_id,
                                      expected_token=job.execution_token)
        db.expire_all()
        result = db.get(JobRun, job.id)
        ledger = db.get(DataPublication, job.id)
        published = outcome == "publish"
        assert result.status == {"publish": "SUCCESS", "cancel": "CANCELLED",
                                 "source_change": "FAILED", "memory": "FAILED"}[outcome]
        assert ledger.state == ("PUBLISHED" if published else "ABORTED")
        count = db.scalar(select(func.count()).select_from(m.StockFactorDaily))
        assert (count > 0) is published
        if outcome == "source_change":
            assert "FACTOR_INPUT_SOURCE_CHANGED" in result.error_message
        if outcome == "memory":
            assert "PRIVATE_SYNTHETIC_BATCH_SENTINEL" not in "".join(messages)
