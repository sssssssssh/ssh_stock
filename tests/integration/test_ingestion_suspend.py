from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa
from app.models.market_data import (
    DataDirtyRange,
    DataQualityDaily,
    StockBasic,
    StockDaily,
    StockSuspendDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.services.ingestion import service as ingestion_module
from app.services.ingestion.service import IngestionService
from app.services.trade_status import TradeStatusService
from sqlalchemy.exc import DataError

from tests.integration.test_suspend_timing_schema import suspend_db as suspend_db

DAY = date(2024, 9, 13)


class Provider:
    def __init__(self, frame):
        self.frame = frame

    def get_suspend_daily(self, trade_date):
        return self.frame


def frame(*, target=DAY, code="T001.SZ", kind="S", timing="全天"):
    return pd.DataFrame([dict(trade_date=target.strftime("%Y%m%d"), ts_code=code,
                              suspend_type=kind, suspend_timing=timing)], dtype=object)


def records(db):
    return db.execute(sa.select(StockSuspendDaily.__table__).order_by(
        StockSuspendDaily.trade_date, StockSuspendDaily.ts_code, StockSuspendDaily.suspend_type,
    )).all()


def quality(db, target=DAY):
    return db.scalar(sa.select(DataQualityDaily).where(
        DataQualityDaily.trade_date == target, DataQualityDaily.dataset == "suspend_d",
    ).execution_options(populate_existing=True))


def dirty_count(db):
    return db.scalar(sa.select(sa.func.count()).select_from(DataDirtyRange))


def test_real_shape_nan_and_long_text_batch_persists_sql_nulls_and_sr(suspend_db):
    factory, _ = suspend_db
    source = pd.DataFrame([
        dict(trade_date="20240913", ts_code=f"T{i:03}.SZ", suspend_type="S",
             suspend_timing=np.nan if i < 12 else "时段;Mixed 文本 " * 40)
        for i in range(13)
    ], dtype=object)
    source.loc[0, "suspend_timing"] = pd.NA
    with factory() as db:
        assert IngestionService(db, Provider(source)).sync_suspend_daily(DAY) == 13
        stored = records(db)
        assert len(stored) == 13
        assert sum(row.suspend_timing is None for row in stored) == 12
        assert stored[-1].suspend_timing == source.iloc[-1]["suspend_timing"]
        assert quality(db).status == "PASS"
        assert quality(db).actual_rows == 13
        assert quality(db).issue_codes["raw_issues"] == []


def test_upsert_idempotency_full_update_and_null_replacement(suspend_db):
    factory, _ = suspend_db
    provider = Provider(frame(timing="中" * 33))
    with factory() as db:
        service = IngestionService(db, provider)
        assert service.sync_suspend_daily(DAY) == 1
        assert dirty_count(db) == 1
        assert service.sync_suspend_daily(DAY) == 1
        assert len(records(db)) == 1
        assert dirty_count(db) == 1
        provider.frame = frame(timing="  原文;Mixed 文本 " * 40)
        assert service.sync_suspend_daily(DAY) == 1
        assert records(db)[0].suspend_timing == provider.frame.iloc[0]["suspend_timing"]
        assert dirty_count(db) == 2
        provider.frame = frame(timing=np.nan)
        assert service.sync_suspend_daily(DAY) == 1
        assert records(db)[0].suspend_timing is None
        assert dirty_count(db) == 3
        assert quality(db).status == "PASS"


@pytest.mark.parametrize("column,value", [
    ("suspend_type", None), ("suspend_type", np.nan), ("suspend_type", pd.NA),
    ("suspend_type", "X"), ("suspend_type", ""), ("suspend_timing", {"bad": "value"}),
    ("suspend_timing", ["全天"]), ("ts_code", None), ("ts_code", np.nan),
    ("ts_code", "x" * 17), ("trade_date", "20240230"), ("trade_date", None),
    ("trade_date", "20240912"),
])
def test_invalid_snapshot_commits_error_without_reconciling_or_partial_rows(
    suspend_db, column, value,
):
    factory, _ = suspend_db
    with factory() as db:
        service = IngestionService(db, Provider(frame()))
        service.sync_suspend_daily(DAY)
        before = records(db)
        before_dirty = dirty_count(db)
        incoming = pd.concat([frame(code="T002.SZ"), frame()], ignore_index=True)
        incoming.at[1, column] = value
        service.provider = Provider(incoming)
        with pytest.raises(ValueError, match="suspend_d quality check failed"):
            service.sync_suspend_daily(DAY)
        assert records(db) == before
        assert dirty_count(db) == before_dirty
        assert quality(db).status == "ERROR"
        assert quality(db).error_count > 0
        assert quality(db).issue_codes["raw_issues"]
    with factory() as db:
        assert quality(db).status == "ERROR"
        assert records(db) == before


@pytest.mark.parametrize("warning", [False, True])
def test_duplicate_or_truncated_snapshot_does_not_destroy_existing_rows(suspend_db, warning):
    factory, _ = suspend_db
    with factory() as db:
        service = IngestionService(db, Provider(frame()))
        service.sync_suspend_daily(DAY)
        before = records(db)
        incoming = frame() if warning else pd.concat([frame(), frame()], ignore_index=True)
        if warning:
            incoming.attrs["provider_warning"] = "POSSIBLE_TRUNCATION"
        service.provider = Provider(incoming)
        with pytest.raises(ValueError, match="quality check failed"):
            service.sync_suspend_daily(DAY)
        assert records(db) == before
        q = quality(db)
        assert q.status == "ERROR"
        assert ("POSSIBLE_TRUNCATION" if warning else "DUPLICATE_NATURAL_KEY") in (
            q.issue_codes["raw_issues"]
        )
        assert q.duplicate_count == (0 if warning else 1)


def test_partial_upsert_database_failure_rolls_back_snapshot_quality_and_dirty(
    suspend_db, monkeypatch,
):
    factory, _ = suspend_db
    previous = DAY - timedelta(days=1)
    with factory() as db:
        service = IngestionService(db, Provider(frame(target=previous)))
        service.sync_suspend_daily(previous)
        service.provider = Provider(frame())
        service.sync_suspend_daily(DAY)
        before = records(db)
        before_dirty = dirty_count(db)
        old_quality = db.execute(sa.select(DataQualityDaily.__table__).order_by(
            DataQualityDaily.id,
        )).all()
        real_upsert = ingestion_module.upsert_rows

        def fail_after_first_row(db, model, rows, *args, **kwargs):
            if model is StockSuspendDaily:
                real_upsert(db, model, list(rows)[:1], *args, **kwargs)
                db.execute(sa.text("SELECT 1 / 0"))
            return real_upsert(db, model, rows, *args, **kwargs)

        monkeypatch.setattr(ingestion_module, "upsert_rows", fail_after_first_row)
        service.provider = Provider(pd.concat([
            frame(code="T002.SZ", timing="长" * 500), frame(code="T003.SZ"),
        ], ignore_index=True))
        with pytest.raises(DataError):
            service.sync_suspend_daily(DAY)
        assert records(db) == before
        assert dirty_count(db) == before_dirty
        assert db.execute(sa.select(DataQualityDaily.__table__).order_by(
            DataQualityDaily.id,
        )).all() == old_quality
        assert quality(db, previous).status == "PASS"
    with factory() as db:
        assert records(db) == before


def test_provider_failure_is_not_treated_as_empty_success(suspend_db):
    factory, _ = suspend_db

    class FailingProvider:
        def get_suspend_daily(self, trade_date):
            raise RuntimeError("synthetic upstream failure")

    with factory() as db:
        service = IngestionService(db, Provider(frame()))
        service.sync_suspend_daily(DAY)
        before = records(db)
        service.provider = FailingProvider()
        with pytest.raises(RuntimeError, match="synthetic upstream failure"):
            service.sync_suspend_daily(DAY)
        assert records(db) == before
        assert quality(db).status == "PASS"


def test_trusted_empty_response_still_reconciles_and_records_pass(suspend_db):
    factory, _ = suspend_db
    with factory() as db:
        service = IngestionService(db, Provider(frame()))
        service.sync_suspend_daily(DAY)
        service.provider = Provider(pd.DataFrame())
        assert service.sync_suspend_daily(DAY) == 0
        assert records(db) == []
        assert quality(db).status == "PASS"
        assert dirty_count(db) == 2


def test_description_null_or_length_does_not_change_trade_status_sr_semantics(suspend_db):
    factory, _ = suspend_db
    with factory() as db:
        db.add(TradeCalendar(cal_date=DAY, is_open=True, exchange="SSE"))
        for code in ("T001.SZ", "T002.SZ"):
            db.add(StockBasic(ts_code=code, list_date=DAY - timedelta(days=400)))
            db.add(StockDaily(trade_date=DAY, ts_code=code, close=10))
        db.commit()
        source = pd.concat([frame(timing=None), frame(code="T002.SZ", kind="R", timing="文" * 500)],
                           ignore_index=True)
        assert IngestionService(db, Provider(source)).sync_suspend_daily(DAY) == 2
        assert TradeStatusService(db).recalc(DAY, DAY) == 2
        stopped = db.get(StockTradeStatusDaily, (DAY, "T001.SZ"))
        resumed = db.get(StockTradeStatusDaily, (DAY, "T002.SZ"))
        assert stopped.is_suspended is True and stopped.tradable is False
        assert resumed.is_suspended is False and resumed.tradable is True
        assert quality(db).status == "PASS"
