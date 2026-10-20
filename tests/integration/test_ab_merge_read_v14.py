from datetime import timedelta

import pandas as pd
import pytest
from app.models.data_publication import DataPublicationRow
from app.models.market_data import StockTradeStatusDaily as Model
from app.repositories.ab_merge_read import (
    ABMergeReadRepository,
    ReadWindow,
    trade_status_statement,
    verify_public_read_evidence,
)
from app.repositories.calculation_frame import read_calculation_frame
from app.repositories.job_run import update_job
from app.services.data_publication import workspace
from app.services.job_guard import data_queue_identity
from sqlalchemy import select, text, update

from scripts.ab_read_benchmark_v14 import frozen_q0, q0_statement
from scripts.v14_test_database import isolated_v14_database
from tests.integration import test_data_publication as support

DAY = support.DAY


@pytest.fixture
def database(monkeypatch):
    with isolated_v14_database(monkeypatch) as value:
        yield value


def params():
    return dict(lo=DAY-timedelta(days=1), hi=DAY+timedelta(days=1),
                version="trade_status_v1", hash=data_queue_identity()["analysis"])


def sorted_frame(frame):
    if frame.empty:
        return frame
    return frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


@pytest.mark.parametrize("mode", ["a_only", "overwrite", "delete", "wrong_version", "wrong_hash",
                                 "rebuild", "new", "empty", "null", "other_root"])
def test_frozen_q0_all_columns_and_factor_types(database, monkeypatch, mode):
    factory, engine = database
    if mode != "empty":
        support.seed_published(factory)
    frozen, _ = frozen_q0()
    monkeypatch.setattr(support, "PublicationWorkspace", frozen)
    # same pinned view from the exact frozen SHA, not an independently guessed SQL oracle
    with support.candidate(factory, engine) as (db, job):
        ws = workspace(db)
        if mode not in {"a_only", "empty"}:
            row = support.sample_row(Model, job.id, 20)
            if mode == "new":
                row["ts_code"] = "NEW.SZ"
            if mode == "null":
                row.update(is_st=None, up_limit=None, down_limit=None, status_reason=None)
            if mode == "wrong_version":
                row["calc_version"] = "wrong"
            if mode == "wrong_hash":
                row["config_hash"] = "wrong"
            ws.upsert(Model, [row], ("trade_date", "ts_code"))
            if mode in {"delete", "rebuild"}:
                ws.delete_keys(Model, [(DAY, row["ts_code"])])
                if mode == "rebuild":
                    ws.upsert(Model, [{**row, "is_st": True}], ("trade_date", "ts_code"))
            if mode == "other_root":
                # Stage into an unrelated PREPARING ledger; not a valid current B.
                from uuid import uuid4

                from app.models.data_publication import DataPublication
                from app.models.job import JobRun

                other = JobRun(job_type="backfill", status="SUCCESS", job_metadata={})
                db.add(other)
                db.flush()
                db.add(DataPublication(job_id=other.id, execution_token=uuid4(), state="PREPARING",
                                       identity={}, row_counts={}))
                db.flush()
                db.execute(update(DataPublicationRow).where(
                    DataPublicationRow.publication_id == job.id).values(publication_id=other.id))
        db.commit()
        before = db.execute(select(DataPublicationRow).where(
            DataPublicationRow.publication_id == job.id)).scalars().all()
        old = read_calculation_frame(db, q0_statement().bindparams(**params()), name="test.golden")
        actual = ABMergeReadRepository(db).read_trade_status(
            window=ReadWindow(params()["lo"], params()["hi"]),
            calc_version=params()["version"], config_hash=params()["hash"], window_days=None)
        pd.testing.assert_frame_equal(sorted_frame(old), actual)
        columns = tuple(Model.__table__.c.keys())
        full_old = read_calculation_frame(db, text(
            "SELECT * FROM stock_trade_status_daily WHERE trade_date BETWEEN :lo AND :hi "
            "AND calc_version=:version AND config_hash=:hash").bindparams(**params()),
            name="test.full_golden")
        statement = trade_status_statement(candidate=True, columns=columns)
        full_new = read_calculation_frame(db, statement
            .bindparams(**params(), root=job.id), name="test.full_new")
        pd.testing.assert_frame_equal(sorted_frame(full_old), full_new)
        if mode in {"delete", "wrong_version", "wrong_hash", "empty"}:
            assert actual.empty  # no ghost A
        assert len(before) == len(list(db.scalars(select(DataPublicationRow).where(
            DataPublicationRow.publication_id == job.id))))
        update_job(db, job, status="FAILED", step="synthetic read test complete")


@pytest.mark.parametrize("corruption", ["date", "entity", "payload_date", "missing_identity",
                                        "tombstone_date"])
def test_bad_redundant_keys_and_missing_identity_fail_closed(database, corruption):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        ws = workspace(db)
        row = support.sample_row(Model, job.id)
        ws.upsert(Model, [row], ("trade_date", "ts_code"))
        if corruption == "tombstone_date":
            ws.delete_keys(Model, [(DAY, row["ts_code"])])
        changes = {"trade_date": DAY+timedelta(days=100)}
        if corruption == "entity":
            changes = {"entity_key": "WRONG.SZ"}
        if corruption in {"payload_date", "missing_identity"}:
            candidate = db.scalar(select(DataPublicationRow).where(
                DataPublicationRow.publication_id == job.id))
            payload = dict(candidate.row_data)
            if corruption == "payload_date":
                payload["trade_date"] = "2020-01-01"
            else:
                del payload["config_hash"]
            changes = {"row_data": payload}
        db.execute(update(DataPublicationRow).where(
            DataPublicationRow.publication_id == job.id).values(**changes))
        db.commit()
        with pytest.raises(ValueError, match="AB_READ_CANDIDATE_INVALID"):
            ABMergeReadRepository(db).read_trade_status(window=ReadWindow(DAY, DAY),
                calc_version="trade_status_v1", config_hash=params()["hash"])
        db.rollback()
        update_job(db, job, status="FAILED")


def test_public_only_does_not_create_workspace(database):
    factory, _ = database
    support.seed_published(factory)
    with factory() as db:
        frame = ABMergeReadRepository(db).read_trade_status(window=ReadWindow(DAY, DAY),
            calc_version="trade_status_v1", config_hash=params()["hash"])
        assert len(frame) == 1
        assert workspace(db) is None


def test_public_input_changed_between_checkpoint_commits_is_rejected(database):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        reader = ABMergeReadRepository(db)
        reader.read_trade_status(window=ReadWindow(DAY, DAY),
            calc_version="trade_status_v1", config_hash=params()["hash"])
        db.commit()
        with factory.begin() as outsider:
            outsider.execute(update(Model).values(is_st=True))
        # New window need not overlap the old one to detect a changed source.
        with pytest.raises(ValueError, match="AB_READ_PUBLISHED_INPUT_CHANGED"):
            reader.read_trade_status(window=ReadWindow(
                DAY+timedelta(days=1), DAY+timedelta(days=2)),
                calc_version="trade_status_v1", config_hash=params()["hash"])
        db.rollback()
        with pytest.raises(ValueError, match="AB_READ_PUBLISHED_INPUT_CHANGED"):
            verify_public_read_evidence(db, workspace(db))
        update_job(db, job, status="FAILED")


@pytest.mark.parametrize("window_days", [1, 3, 5, 10, 20])
def test_windows_preserve_full_keys_null_dtype_and_closed_day_rows(database, window_days):
    from datetime import date

    from app.models.market_data import TradeCalendar

    factory, engine = database
    support.seed_published(factory)
    start, end = date(2024, 12, 20), date(2025, 2, 8)
    with factory() as db:
        day = start
        while day <= end:
            db.add(TradeCalendar(cal_date=day, is_open=day.weekday()<5 and day != date(2025, 1, 1)))
            # Deliberately include closed-day stored values: do not silently drop.
            row = support.sample_row(Model, None, day=day)
            row["is_st"] = None if day < date(2025, 1, 5) else False
            db.add(Model(**row))
            day += timedelta(days=1)
        db.commit()
    with support.candidate(factory, engine) as (db, job):
        row = support.sample_row(Model, job.id, day=date(2025, 1, 1))
        workspace(db).upsert(Model, [row], ("trade_date", "ts_code"))
        workspace(db).delete_keys(Model, [(date(2025, 1, 2), row["ts_code"])])
        db.commit()
        bind = {**params(), "lo": start, "hi": end}
        old = read_calculation_frame(db, q0_statement().bindparams(**bind), name="test.golden")
        events = []
        actual = ABMergeReadRepository(db, observer=events.append).read_trade_status(
            window=ReadWindow(start, end), calc_version=bind["version"], config_hash=bind["hash"],
            window_days=window_days)
        pd.testing.assert_frame_equal(sorted_frame(old), actual)
        assert len(actual) == (end-start).days
        assert len([item for item in events if item["event"] == "window"]) > 1
        assert db.in_transaction()
        update_job(db, job, status="FAILED")
