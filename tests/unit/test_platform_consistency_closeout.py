from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import app.jobs.catchup_job as catchup_module
import app.services.ingestion.service as ingestion_module
import app.services.quality.daily_quality as daily_quality_module
import app.services.recalculation as recalculation_module
import pandas as pd
import pytest
from app.models.market_data import (
    DataQualityDaily,
    Sector,
    SectorMember,
    StockBasic,
    StockStDaily,
    StockSuspendDaily,
    TradeCalendar,
)
from app.services.ingestion.service import IngestionService
from app.services.job_guard import recover_stale_ingestion_jobs
from app.services.quality.daily_quality import DataQualityError, expected_stock_daily_codes
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class _EmptyEventProvider:
    def get_stock_st(self, trade_date: date) -> pd.DataFrame:
        return pd.DataFrame()

    def get_suspend_daily(self, trade_date: date) -> pd.DataFrame:
        return pd.DataFrame()


@pytest.mark.parametrize(
    ("model", "existing", "method", "dataset"),
    [
        (
            StockStDaily,
            StockStDaily(
                trade_date=date(2026, 9, 10),
                ts_code="000001.SZ",
                name="ST A",
                st_type="ST",
            ),
            "sync_stock_st",
            "stock_st",
        ),
        (
            StockSuspendDaily,
            StockSuspendDaily(
                trade_date=date(2026, 9, 10),
                ts_code="000001.SZ",
                suspend_type="S",
            ),
            "sync_suspend_daily",
            "suspend_d",
        ),
    ],
)
def test_empty_event_snapshot_removes_stale_row_and_records_pass(
    monkeypatch, model, existing, method, dataset
) -> None:
    engine = create_engine("sqlite:///:memory:")
    model.__table__.create(engine)
    quality_rows = []
    dirty_calls = []

    def fake_upsert(db, target_model, rows, *args, **kwargs):
        payload = list(rows)
        if target_model is DataQualityDaily:
            quality_rows.extend(payload)
        return len(payload)

    monkeypatch.setattr(ingestion_module, "upsert_rows", fake_upsert)
    monkeypatch.setattr(daily_quality_module, "upsert_rows", fake_upsert)
    monkeypatch.setattr(
        ingestion_module,
        "record_dirty_range",
        lambda db, **kwargs: dirty_calls.append(kwargs),
    )
    with Session(engine) as db:
        db.add(existing)
        db.commit()

        count = getattr(IngestionService(db, _EmptyEventProvider()), method)(
            date(2026, 9, 10)
        )

        assert count == 0
        assert db.execute(select(model)).scalars().all() == []

    quality = next(row for row in quality_rows if row["dataset"] == dataset)
    assert quality["status"] == "PASS"
    assert quality["actual_rows"] == 0
    assert dirty_calls[0]["dirty_dates"] == {date(2026, 9, 10)}


def test_empty_event_snapshot_on_empty_database_is_success(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    StockStDaily.__table__.create(engine)
    quality_rows = []
    monkeypatch.setattr(
        ingestion_module,
        "upsert_rows",
        lambda db, model, rows, *args, **kwargs: quality_rows.extend(list(rows)) or 0,
    )
    monkeypatch.setattr(
        daily_quality_module,
        "upsert_rows",
        lambda db, model, rows, *args, **kwargs: quality_rows.extend(list(rows)) or 0,
    )
    monkeypatch.setattr(ingestion_module, "record_dirty_range", lambda *args, **kwargs: None)

    with Session(engine) as db:
        assert IngestionService(db, _EmptyEventProvider()).sync_stock_st(date(2026, 9, 10)) == 0

    assert quality_rows[0]["status"] == "PASS"


def test_expected_daily_universe_excludes_suspended_stock() -> None:
    engine = create_engine("sqlite:///:memory:")
    StockBasic.__table__.create(engine)
    StockSuspendDaily.__table__.create(engine)
    target = date(2026, 9, 10)
    with Session(engine) as db:
        db.add_all(
            [
                StockBasic(ts_code=code, list_date=date(2020, 1, 1), list_status="L")
                for code in ("A", "B", "C")
            ]
        )
        db.add(
            StockSuspendDaily(
                trade_date=target,
                ts_code="C",
                suspend_type="S",
            )
        )
        db.commit()

        assert expected_stock_daily_codes(db, target) == {"A", "B"}


def test_recalculation_raw_gate_reports_failed_date_and_datasets(monkeypatch) -> None:
    target = date(2026, 9, 10)

    class Result:
        is_complete = False

        @staticmethod
        def as_metadata():
            return {
                "current_day_datasets": {
                    "stock_daily": "PASS",
                    "adj_factor": "PASS",
                    "daily_basic": "PASS",
                    "index_daily": "PASS",
                    "stock_st": "ERROR",
                    "suspend_d": "ERROR",
                    "stk_limit": "PASS",
                }
            }

    class QueryResult:
        def scalars(self):
            return self

        def all(self):
            return [target]

    monkeypatch.setattr(
        recalculation_module,
        "check_raw_completeness",
        lambda *args, **kwargs: Result(),
    )

    with pytest.raises(DataQualityError) as exc_info:
        recalculation_module.validate_recalculation_raw_prerequisites(
            SimpleNamespace(execute=lambda statement: QueryResult()),
            target,
            target,
            strategy={},
        )

    message = str(exc_info.value)
    assert "trade_date=2026-09-10" in message
    assert "stock_st" in message
    assert "suspend_d" in message
    assert "run backfill first" in message


def test_recalculation_gate_runs_before_trade_status(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        recalculation_module,
        "_factor_warmup_start",
        lambda db, start: start,
    )
    monkeypatch.setattr(
        recalculation_module,
        "validate_recalculation_raw_prerequisites",
        lambda *args, **kwargs: (_ for _ in ()).throw(DataQualityError("raw missing")),
    )
    monkeypatch.setattr(
        recalculation_module,
        "TradeStatusService",
        lambda db: SimpleNamespace(recalc=lambda *args, **kwargs: calls.append("trade_status")),
    )
    job = SimpleNamespace(
        id="job-1",
        status="RUNNING",
        step=None,
        row_count=0,
        error_message=None,
        finished_at=None,
        job_metadata={},
    )
    db = SimpleNamespace(add=lambda row: None, commit=lambda: None, refresh=lambda row: None)

    with pytest.raises(DataQualityError, match="raw missing"):
        recalculation_module.run_recalculation(
            db,
            job,
            date(2026, 9, 10),
            date(2026, 9, 10),
            evaluate_signals=False,
        )

    assert calls == []


def test_catchup_synchronous_recalculation_starts_running(monkeypatch) -> None:
    captured = []
    monkeypatch.setattr(
        catchup_module,
        "start_job",
        lambda db, job_type, target, **kwargs: captured.append(kwargs)
        or SimpleNamespace(id="sub-job"),
    )
    monkeypatch.setattr(catchup_module, "run_recalculation", lambda *args, **kwargs: None)
    job = catchup_module.CatchUpJob.__new__(catchup_module.CatchUpJob)
    job.db = object()

    job._run_analysis_repair(
        date(2026, 9, 1),
        date(2026, 9, 10),
        mode="catchup_analysis",
    )

    assert captured[0]["status"] == "RUNNING"
    assert captured[0]["metadata"]["execution_owner"] == "catchup"


def test_running_recovery_uses_heartbeat_minute_boundary() -> None:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    fresh = SimpleNamespace(
        id="fresh",
        job_type="daily",
        status="RUNNING",
        started_at=now - timedelta(hours=2),
        heartbeat_at=now - timedelta(minutes=10),
        finished_at=None,
        error_message=None,
    )
    stale = SimpleNamespace(
        id="stale",
        job_type="daily",
        status="RUNNING",
        started_at=now - timedelta(hours=2),
        heartbeat_at=now - timedelta(minutes=16),
        finished_at=None,
        error_message=None,
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [fresh, stale]

    db = SimpleNamespace(
        execute=lambda statement: Result(),
        add=lambda row: None,
        commit=lambda: None,
    )

    recovered = recover_stale_ingestion_jobs(
        db,
        queued_stale_hours=24,
        running_heartbeat_timeout_minutes=15,
        now=now,
    )

    assert recovered == 1
    assert fresh.status == "RUNNING"
    assert stale.status == "FAILED"


def test_sector_member_successful_snapshot_deletes_stale_sw_member(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Sector.__table__.create(engine)
    SectorMember.__table__.create(engine)

    class Provider:
        def get_sector_members(self):
            return pd.DataFrame(
                [
                    {
                        "l1_code": "801010.SI",
                        "con_code": "000001.SZ",
                        "in_date": "20200101",
                        "is_new": "Y",
                    }
                ]
            )

    monkeypatch.setattr(
        ingestion_module,
        "upsert_rows",
        lambda db, model, rows, *args, **kwargs: len(list(rows)),
    )
    with Session(engine) as db:
        sector = Sector(
            source="SW",
            source_code="801010.SI",
            name="Sector",
            is_active=True,
        )
        db.add(sector)
        db.flush()
        db.add_all(
            [
                SectorMember(
                    sector_id=sector.sector_id,
                    ts_code="000001.SZ",
                    valid_from=date(2020, 1, 1),
                ),
                SectorMember(
                    sector_id=sector.sector_id,
                    ts_code="STALE.SZ",
                    valid_from=date(2020, 1, 1),
                ),
            ]
        )
        db.commit()

        assert IngestionService(db, Provider()).sync_sector_members() == 1
        codes = set(db.execute(select(SectorMember.ts_code)).scalars().all())

    assert codes == {"000001.SZ"}


def test_sector_member_provider_failure_does_not_delete_existing() -> None:
    engine = create_engine("sqlite:///:memory:")
    Sector.__table__.create(engine)
    SectorMember.__table__.create(engine)

    class Provider:
        def get_sector_members(self):
            raise RuntimeError("batch failed")

    with Session(engine) as db:
        sector = Sector(
            source="SW",
            source_code="801010.SI",
            name="Sector",
            is_active=True,
        )
        db.add(sector)
        db.flush()
        db.add(
            SectorMember(
                sector_id=sector.sector_id,
                ts_code="OLD.SZ",
                valid_from=date(2020, 1, 1),
            )
        )
        db.commit()

        with pytest.raises(RuntimeError, match="batch failed"):
            IngestionService(db, Provider()).sync_sector_members()
        assert db.execute(select(SectorMember.ts_code)).scalar_one() == "OLD.SZ"


def test_factor_warmup_uses_previous_250_open_dates() -> None:
    engine = create_engine("sqlite:///:memory:")
    TradeCalendar.__table__.create(engine)
    start = date(2026, 9, 16)
    with Session(engine) as db:
        for offset in range(300):
            day = start - timedelta(days=offset)
            db.add(
                TradeCalendar(
                    cal_date=day,
                    is_open=True,
                    exchange="SSE",
                )
            )
        db.commit()

        warmup_start = recalculation_module._factor_warmup_start(db, start)

    assert warmup_start == start - timedelta(days=250)
