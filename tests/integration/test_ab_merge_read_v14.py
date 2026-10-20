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
        pd.testing.assert_frame_equal(sorted_frame(old), actual, check_exact=True)
        columns = tuple(Model.__table__.c.keys())
        full_old = read_calculation_frame(db, text(
            "SELECT * FROM stock_trade_status_daily WHERE trade_date BETWEEN :lo AND :hi "
            "AND calc_version=:version AND config_hash=:hash").bindparams(**params()),
            name="test.full_golden")
        statement = trade_status_statement(candidate=True, columns=columns)
        full_new = read_calculation_frame(db, statement
            .bindparams(**params(), root=job.id), name="test.full_new")
        pd.testing.assert_frame_equal(sorted_frame(full_old), full_new, check_exact=True)
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
        pd.testing.assert_frame_equal(sorted_frame(old), actual, check_exact=True)
        assert len(actual) == (end-start).days
        assert len([item for item in events if item["event"] == "window"]) > 1
        assert db.in_transaction()
        update_job(db, job, status="FAILED")


@pytest.mark.parametrize("fault,expected", [
    ("cancel", "CANCELLED"), ("timeout", "FAILED"), ("disconnect", "RUNNING"),
])
def test_real_worker_window_failure_keeps_public_a_and_execution_safety(
    database, monkeypatch, fault, expected,
):
    from app.api.v1.jobs import cancel_job
    from app.models.data_publication import DataPublication
    from app.models.job import JobRun
    from app.services.job_guard import create_queued_ingestion_job
    from app.services.job_worker import claim_next_job, execute_claimed_job

    factory, engine = database
    support.seed_published(factory)
    monkeypatch.setattr("app.services.job_worker.SessionLocal", factory)
    with factory() as db:
        before = db.scalar(text("SELECT jsonb_agg(to_jsonb(a)) FROM stock_trade_status_daily a"))
        job = create_queued_ingestion_job(db, "recalculate", DAY, step="queued", metadata={
            "start": str(DAY), "end": str(DAY), "evaluate_signals": False})
        assert claim_next_job(db, "v14-fault-test") == job.id
        db.refresh(job)
        key, worker, token = job.id, job.worker_id, job.execution_token

    def pipeline(db, job, *args, **kwargs):
        # One committed B exists, but must remain invisible on all failures.
        row = support.sample_row(Model, job.id)
        row["is_st"] = True
        workspace(db).upsert(Model, [row], ("trade_date", "ts_code"))
        db.commit()
        pid = db.scalar(text("SELECT pg_backend_pid()"))

        def inject(metric):
            if metric["event"] != "window":
                return
            if fault == "cancel":
                with factory() as cancellation:
                    cancel_job(job.id, cancellation)
                from app.services.job_execution import checkpoint

                checkpoint()
            elif fault == "timeout":
                db.execute(text("SET LOCAL statement_timeout='10ms'"))
                db.execute(text("SELECT pg_sleep(0.1)"))
            else:
                with engine.begin() as controller:
                    assert controller.scalar(text("SELECT pg_terminate_backend(:pid)"),
                                             {"pid": pid})
                db.execute(text("SELECT 1"))

        ABMergeReadRepository(db, observer=inject).read_trade_status(
            window=ReadWindow(DAY, DAY), calc_version="trade_status_v1",
            config_hash=params()["hash"])
        raise AssertionError("partial read must never reach success")

    monkeypatch.setattr("app.services.job_worker.run_recalculation", pipeline)
    with factory() as db:
        execute_claimed_job(db, key, expected_worker=worker, expected_token=token)
    with factory() as db:
        job = db.get(JobRun, key)
        assert job.status == expected
        state = db.get(DataPublication, key).state
        assert state == ("PREPARING" if fault == "disconnect" else "ABORTED")
        after = db.scalar(text("SELECT jsonb_agg(to_jsonb(a)) FROM stock_trade_status_daily a"))
        assert after == before
        if fault == "disconnect":
            assert job.job_metadata["execution_unconfirmed"]
            assert claim_next_job(db, "other") is None
        if fault == "timeout":
            assert "57014" in job.error_message


def test_real_engine_and_atomic_publication_equal_legacy_full_path(monkeypatch):
    import json

    from app.core.config import get_settings
    from app.models.data_publication import DataPublication

    outputs = []
    for enabled in (False, True):
        with monkeypatch.context() as patch:
            patch.setattr(get_settings(), "ab_merge_read_enabled", enabled)
            with isolated_v14_database(patch) as database:
                factory, _ = database
                support.test_real_recalculation_and_quality_publish_without_synthetic_certificate(
                    database, patch, "absent", None)
                with factory() as db:
                    roots = set(db.scalars(select(DataPublication.job_id)))
                    tables = {}
                    for model in support.MODELS:
                        rows = []
                        for record in db.execute(select(model.__table__)).mappings():
                            row = dict(record)
                            for field in ("calculated_at", "created_at", "checked_at"):
                                row.pop(field, None)  # independent run clock, not business columns
                            for field in ("calc_run_id", "job_id"):
                                if row.get(field) is not None:
                                    row[field] = "ROOT" if row[field] in roots else "SEED"
                            rows.append(json.dumps(row, default=str, sort_keys=True))
                        tables[model.__tablename__] = sorted(rows)
                    outputs.append(tables)
    assert outputs[0] == outputs[1]


def test_read_lock_allows_rr_public_reader_but_prevents_mid_window_old_writer(database):
    from sqlalchemy.exc import DBAPIError

    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        row = support.sample_row(Model, job.id)
        row["is_st"] = True
        workspace(db).upsert(Model, [row], ("trade_date", "ts_code"))
        db.commit()
        ABMergeReadRepository(db).read_trade_status(window=ReadWindow(DAY, DAY),
            calc_version="trade_status_v1", config_hash=params()["hash"])
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as reader:
            reader.execute(text("SET TRANSACTION READ ONLY"))
            assert reader.scalar(text("SELECT is_st FROM public.stock_trade_status_daily")) is None
        with factory() as writer:
            writer.execute(text("SET LOCAL lock_timeout='20ms'"))
            with pytest.raises(DBAPIError) as error:
                writer.execute(update(Model).values(is_st=True))
            assert error.value.orig.sqlstate == "55P03"
            writer.rollback()
        db.rollback()
        update_job(db, job, status="FAILED")


def test_actual_named_cursor_fetches_5000_and_closes(database):
    from sqlalchemy import insert

    factory, engine = database
    support.seed_published(factory)
    with factory() as db:
        db.execute(insert(Model), [{**support.sample_row(Model, None), "ts_code": f"S{i:06}.SZ"}
                                   for i in range(10001)])
        db.commit()
    with support.candidate(factory, engine) as (db, job):
        events = []

        def observed(metric):
            events.append(metric)
            if metric["event"] == "fetch":
                assert db.scalar(text("""SELECT count(*) FROM pg_cursors WHERE
                    statement LIKE '%stock_trade_status_daily%' AND NOT is_holdable""")) == 1

        frame = ABMergeReadRepository(db, observer=observed).read_trade_status(
            window=ReadWindow(DAY, DAY), calc_version="trade_status_v1",
            config_hash=params()["hash"])
        assert len(frame) == 10002
        assert [m["rows"] for m in events if m["event"] == "fetch"] == [5000, 5000, 2]
        assert events[-1]["first_5000_seconds"] is not None
        assert 0 <= events[-1]["first_row_seconds"] <= events[-1]["first_5000_seconds"]
        assert db.scalar(text("SELECT count(*) FROM pg_cursors")) == 0
        update_job(db, job, status="FAILED")


def test_wrong_execution_token_cannot_read_candidate(database):
    from dataclasses import replace
    from uuid import uuid4

    from app.services.job_execution import JobOwnershipLost, current_execution

    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        token = current_execution.set(replace(current_execution.get(), token=uuid4()))
        try:
            with pytest.raises(JobOwnershipLost):
                ABMergeReadRepository(db).read_trade_status(window=ReadWindow(DAY, DAY),
                    calc_version="trade_status_v1", config_hash=params()["hash"])
        finally:
            current_execution.reset(token)
        update_job(db, job, status="FAILED")


def test_final_publication_checks_read_only_warmup_a_not_just_candidate_base(database):
    from types import SimpleNamespace

    from app.services.data_publication import record_validation

    factory, engine = database
    source = support.seed_published(factory)
    warmup = DAY-timedelta(days=1)
    with factory() as db:
        db.add(Model(**support.sample_row(Model, source, day=warmup)))
        db.commit()
    with support.candidate(factory, engine) as (db, job):
        ABMergeReadRepository(db).read_trade_status(window=ReadWindow(warmup, DAY),
            calc_version="trade_status_v1", config_hash=params()["hash"], window_days=None)
        db.commit()
        support.stage_all(db, job)
        record_validation(db, job.id, DAY, SimpleNamespace(has_error=False))
        db.commit()
        with factory.begin() as outsider:
            outsider.execute(update(Model).where(
                Model.trade_date == warmup).values(is_st=True))
        with pytest.raises(ValueError, match="AB_READ_PUBLISHED_INPUT_CHANGED"):
            update_job(db, job, status="SUCCESS")
        db.rollback()
        update_job(db, job, status="FAILED")
        assert db.scalar(select(Model.is_st).where(Model.trade_date == warmup)) is True
