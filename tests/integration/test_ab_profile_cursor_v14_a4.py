from datetime import date

import pytest
from app.repositories import ab_merge_read as ab
from app.repositories import calculation_frame as cf
from app.services.data_publication import workspace
from app.services.job_execution import JobCancelled
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from scripts.ab_read_benchmark_v14 import frozen_q0, seed, stage
from scripts.ab_read_profile_v14_a4 import Profile, measure
from scripts.v14_test_database import isolated_v14_database
from tests.integration import test_data_publication as support


@pytest.fixture
def database(monkeypatch):
    with isolated_v14_database(monkeypatch) as value:
        factory, _ = value
        with factory.begin() as db:
            db.execute(text("CREATE EXTENSION pg_stat_statements"))
        yield value


def test_profile_real_cursor_complete_golden_and_driver_restoration(database, monkeypatch):
    factory, engine = database
    with factory() as db:
        seed(db, public_rows=10000, candidate_rows=0, other_rows=0)
    monkeypatch.setattr(support, "PublicationWorkspace", frozen_q0()[0])
    with support.candidate(factory, engine) as (db, job):
        stage(db, job.id, job.id, 5253, offset=9)
        params = dict(lo=date(2024, 1, 1), hi=date(2024, 12, 31),
                      version="trade_status_v1", hash=support.data_queue_identity()["analysis"])
        driver = db.connection().connection.driver_connection
        original_factory, original_checkpoint = driver.server_cursor_factory, cf.checkpoint
        records = [measure(db, engine, variant, params)[0] for variant in ("q0", "q1", "q2")]
        assert len({(r["rows"], r["hash"]) for r in records}) == 1
        assert records[0]["dtypes"] == records[1]["dtypes"] == records[2]["dtypes"]
        assert driver.server_cursor_factory is original_factory
        assert cf.checkpoint is original_checkpoint
        protected = records[1]
        assert all(c["name"] and c["closed"] for c in protected["cursors"])
        # Real psycopg server cursor: SQLAlchemy primes one row, then obtains
        # 4999 to complete the first logical batch; following FETCHes are 5000.
        requests = [f["requested"] for c in protected["cursors"] for f in c["fetches"]]
        assert requests[:3] == [1, 4999, 5000]
        fetched = sum(f["rows"] for c in protected["cursors"] for f in c["fetches"])
        assert fetched == protected["rows"]
        phases = protected["phase_distributions"]
        assert phases["T3_fingerprint_inclusive"]["count"] == 2  # capture + final verify
        assert phases["T8_verify_inclusive"]["count"] == 1
        assert phases["T2_lock_hold"]["count"] == 2
        assert "checkpoint" not in records[0]["phase_distributions"]


def test_profile_preserves_share_lock_dml_effect_and_cross_commit_proof(database):
    factory, engine = database
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        profile = Profile(db, engine)
        with profile.observe():
            ab.ABMergeReadRepository(db).read_trade_status(
                window=ab.ReadWindow(support.DAY, support.DAY), calc_version="trade_status_v1",
                config_hash=support.data_queue_identity()["analysis"], window_days=None)
            with factory() as outsider:
                outsider.execute(text("SET LOCAL lock_timeout='100ms'"))
                with pytest.raises(DBAPIError) as error:
                    outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=true"))
                assert error.value.orig.sqlstate == "55P03"
                outsider.rollback()
            db.commit()
            with factory.begin() as outsider:
                outsider.execute(text("UPDATE public.stock_trade_status_daily SET is_st=true"))
            db.execute(text("LOCK TABLE public.stock_trade_status_daily IN SHARE MODE"))
            with pytest.raises(ValueError, match="AB_READ_PUBLISHED_INPUT_CHANGED"):
                ab.verify_public_read_evidence(db, workspace(db))
            db.rollback()
        evidence = profile.receipt()
        assert evidence["phase_distributions"]["T2_lock_hold"]["count"] == 2
        assert any(e.get("failure_type") == "ValueError" for e in evidence["events"])


def test_profile_cancel_has_no_partial_frame_and_restores_observers(database, monkeypatch):
    factory, engine = database
    support.seed_published(factory)
    original = cf.checkpoint
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        original()
        if calls == 2:
            raise JobCancelled("synthetic-a4-cancel")

    monkeypatch.setattr(cf, "checkpoint", cancelled)
    with support.candidate(factory, engine) as (db, job):
        driver = db.connection().connection.driver_connection
        original_factory = driver.server_cursor_factory
        params = dict(lo=support.DAY, hi=support.DAY, version="trade_status_v1",
                      hash=support.data_queue_identity()["analysis"])
        with pytest.raises(JobCancelled) as error:
            measure(db, engine, "q1", params)
        assert error.value.a4_receipt["failure_type"] == "JobCancelled"
        assert all(c["closed"] for c in error.value.a4_receipt["cursors"])
        assert driver.server_cursor_factory is original_factory
        assert cf.checkpoint is cancelled
