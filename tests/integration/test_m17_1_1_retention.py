import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from threading import Barrier, Event
from time import monotonic, sleep

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.core.retention_config import RetentionPolicy
from app.models import Base
from app.models.job import JobRun, ProviderApiLog, ServiceHeartbeat
from app.models.market_data import Sector, StockFactorDaily, Theme
from app.services.retention import run_retention
from app.services.retention_lineage import JOB_REFERENCES, assert_reference_schema
from sqlalchemy.exc import IntegrityError, OperationalError

from tests.integration.m16_6_support import isolated_contract_database
from tests.integration.test_m13_3_2_consistency import _run

NOW = datetime(2026, 10, 15, tzinfo=UTC)
DAY = date(2026, 1, 2)
ENABLED = RetentionPolicy(job_deletion_enabled=True)


@pytest.fixture
def retention_db(monkeypatch):
    with isolated_contract_database(monkeypatch) as database:
        yield database


def old_job(db, *, age=181, status="SUCCESS", kind="recalculate"):
    identity = uuid.uuid4()
    # This fixture also seeds the historical 0053 schema. Do not send newer
    # nullable ORM columns to a database deliberately downgraded by the test.
    db.execute(sa.insert(JobRun.__table__).values(id=identity, job_type=kind, status=status,
               started_at=NOW - timedelta(days=age, minutes=1),
               finished_at=NOW - timedelta(days=age), job_metadata={}))
    db.commit()
    return identity


def legacy_job_snapshot(db):
    fields = ("id", "job_type", "target_trade_date", "started_at", "heartbeat_at", "worker_id",
              "finished_at", "status", "step", "row_count", "error_message", "cancel_requested",
              "job_metadata")
    return db.execute(sa.select(*(JobRun.__table__.c[name] for name in fields))).all()


def reference(db, name, field, job_id, *, day=DAY, code="T001.SZ"):
    table = Base.metadata.tables[name]
    if name == "job_run":
        db.add(JobRun(job_type="backfill", status="QUEUED", **{field: job_id}))
        db.flush()
        return
    if name == "portfolio_backtest_run":
        run = _run(day)
        run.job_id = job_id
        db.add(run)
        db.flush()
        return
    values = {
        "trade_date": day, "ts_code": code, "algo_version": "test-version", "state": "S4",
        "signal_type": "TREND_ENTER", "dataset": "stock_daily", "status": "RESOLVED",
        "dirty_start_date": day, "dirty_end_date": day, "calc_version": "test-version",
        "config_hash": "a" * 64, "source_strategy_config_hash": "b" * 64,
        "calculated_at": NOW - timedelta(days=180), "is_active": True,
        "is_suspended": False, "is_st": False, "st_status_unknown": False,
        "tradable": True, "strategy_eligible": True, "opportunity_stage": "TREND",
    }
    if name == "sector_factor_daily":
        sector = Sector(source="SW", source_code="TEST", name="synthetic", level="L1")
        db.add(sector)
        db.flush()
        values["sector_id"] = sector.sector_id
    if name == "theme_factor_daily":
        db.add(Theme(theme_code="TEST", source="THS", name="synthetic", theme_type="N"))
        db.flush()
        values["theme_code"] = "TEST"
    values = {key: value for key, value in values.items() if key in table.c}
    values[field] = job_id
    db.execute(sa.insert(table).values(values))


def migrate(engine, target, *, downgrade=False):
    config = Config("alembic.ini")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if downgrade else command.upgrade)(config, target)


@pytest.mark.parametrize("status,age,deleted", [
    ("SUCCESS", 179, False), ("SUCCESS", 180, False), ("SUCCESS", 181, True),
    ("PARTIAL", 181, True), ("CANCELLED", 181, True),
    ("FAILED", 364, False), ("FAILED", 365, False), ("FAILED", 366, True),
    ("RUNNING", 400, False), ("QUEUED", 400, False),
])
def test_original_strict_age_and_status_contract(retention_db, status, age, deleted):
    factory, _ = retention_db
    with factory() as db:
        job_id = old_job(db, age=age, status=status)
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert not result["blocked"]
        assert (db.get(JobRun, job_id) is None) == deleted
        assert result["successful_jobs"] + result["failed_jobs"] == int(deleted)
        assert result["deleted_failed_jobs"] == int(deleted and status == "FAILED")


@pytest.mark.parametrize("name,field", [r for r in JOB_REFERENCES if r[0] != "paper_day_run"])
def test_each_persistent_reference_protects_old_job(retention_db, name, field):
    factory, _ = retention_db
    with factory() as db:
        job_id = old_job(db)
        reference(db, name, field, job_id)
        db.commit()
        before = db.execute(sa.select(Base.metadata.tables[name])).all()
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert not result["blocked"]
        assert result["eligible_success_jobs"] == result["protected_referenced_jobs"] == 1
        assert result["successful_jobs"] == result["failed_jobs"] == 0
        assert db.get(JobRun, job_id) is not None
        assert db.execute(sa.select(Base.metadata.tables[name])).all() == before


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED", "PARTIAL", "CANCELLED"])
def test_multiple_tables_days_and_statuses_protect_one_distinct_job(retention_db, status):
    factory, _ = retention_db
    with factory() as db:
        job_id = old_job(db, age=400, status=status)
        reference(db, "stock_factor_daily", "calc_run_id", job_id)
        reference(db, "stock_factor_daily", "calc_run_id", job_id, day=DAY + timedelta(days=1))
        reference(db, "market_daily", "calc_run_id", job_id)
        db.commit()
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert result["protected_referenced_jobs"] == 1 and not result["blocked"]
        assert db.get(JobRun, job_id).status == status


@pytest.mark.parametrize("kind", ["PAPER_DAILY", "PAPER_REVIEW", "PAPER_OBSERVATION"])
def test_paper_types_remain_excluded_even_without_fk_references(retention_db, kind):
    factory, _ = retention_db
    with factory() as db:
        job_id = old_job(db, age=800, kind=kind)
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert result["candidate_scan_rows"] == 0 and not result["blocked"]
        assert db.get(JobRun, job_id) is not None


def test_dry_run_default_disabled_and_idempotent_real_cleanup(retention_db):
    factory, _ = retention_db
    with factory() as db:
        job_id = old_job(db)
        for kwargs in ({"dry_run": True, "policy": ENABLED}, {"policy": RetentionPolicy()}):
            result = run_retention(db, now=NOW, **kwargs)
            assert result["eligible_success_jobs"] == 1 and result["successful_jobs"] == 0
            assert db.get(JobRun, job_id) is not None and not result["blocked"]
        assert run_retention(db, now=NOW, policy=ENABLED)["successful_jobs"] == 1
        assert run_retention(db, now=NOW, policy=ENABLED)["successful_jobs"] == 0


def test_schema_unknown_reference_and_missing_index_fail_closed(retention_db):
    factory, engine = retention_db
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE future_derived (calc_run_id uuid)"))
    with factory() as db:
        job_id = old_job(db)
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert result["error_code"] == "RETENTION_REFERENCE_SCHEMA_MISMATCH"
        assert db.get(JobRun, job_id) is not None
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE future_derived"))
        connection.execute(sa.text("DROP INDEX ix_stock_factor_daily_calc_run_id"))
    with factory() as db:
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert result["error_code"] == "RETENTION_REFERENCE_PROTECTION_UNAVAILABLE"
        assert db.get(JobRun, job_id) is not None


def test_legacy_orphan_survives_migration_and_is_diagnosed_not_fabricated(retention_db):
    factory, engine = retention_db
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    lost = uuid.uuid4()
    with factory() as db:
        reference(db, "stock_factor_daily", "calc_run_id", lost)
        db.commit()
        before = db.execute(sa.select(StockFactorDaily)).scalar_one().calc_run_id
    migrate(engine, "head")
    with factory() as db:
        assert_reference_schema(db)
        result = run_retention(db, now=NOW, dry_run=True, include_diagnostics=True)
        assert not result["blocked"] and result["missing_provenance_references"] == 1
        assert result["missing_reference_samples"] == [{
            "table": "stock_factor_daily", "column": "calc_run_id", "job_id": str(lost),
            "trade_date": str(DAY),
        }]
        assert db.get(JobRun, lost) is None
        assert db.scalar(sa.select(StockFactorDaily.calc_run_id)) == before
        with pytest.raises(IntegrityError):
            reference(db, "stock_factor_daily", "calc_run_id", lost, code="NEW.SZ")
        db.rollback()


@pytest.mark.parametrize("name,field", [
    ("stock_factor_daily", "calc_run_id"), ("portfolio_backtest_run", "job_id"),
])
def test_writer_first_parent_key_share_prevents_delete_and_orphan(retention_db, name, field):
    factory, _ = retention_db
    with factory() as db:
        job_id = old_job(db)
    with factory() as writer:
        reference(writer, name, field, job_id)
        with ThreadPoolExecutor(max_workers=1) as pool:
            def cleanup():
                with factory() as cleaner:
                    return run_retention(cleaner, now=NOW, policy=ENABLED)
            result = pool.submit(cleanup).result(timeout=20)
        assert not result["blocked"] and result["successful_jobs"] == 0
        writer.commit()
    with factory() as db:
        assert db.get(JobRun, job_id) is not None
        assert db.scalar(sa.select(Base.metadata.tables[name].c[field])) == job_id


@pytest.mark.parametrize("name,field", [
    ("stock_factor_daily", "calc_run_id"), ("portfolio_backtest_run", "job_id"),
    ("decision_observation", "data.candidates[].calc_run_id"),
])
def test_cleaner_first_new_reference_is_rejected_after_parent_commit(retention_db, name, field):
    factory, engine = retention_db
    with factory() as db:
        job_id = old_job(db)
    deleted, release, writing = Event(), Event(), Event()

    def after_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM job_run"):
            deleted.set()
            assert release.wait(10)

    def cleanup():
        with factory() as db:
            return run_retention(db, now=NOW, policy=ENABLED)

    def write():
        assert deleted.wait(10)
        with factory() as db:
            db.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
            writing.set()
            try:
                if name == "decision_observation":
                    from tests.integration.test_m17_1_1_retention_frozen import snapshot

                    snapshot(db, job_id)
                else:
                    reference(db, name, field, job_id)
                db.commit()
                return "UNEXPECTED_WRITE"
            except IntegrityError as exc:
                db.rollback()
                return exc.orig.sqlstate

    sa.event.listen(engine, "after_cursor_execute", after_delete)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cleaner = pool.submit(cleanup)
            writer = pool.submit(write)
            try:
                assert writing.wait(10)
            finally:
                release.set()
            result, state = cleaner.result(timeout=20), writer.result(timeout=20)
    finally:
        sa.event.remove(engine, "after_cursor_execute", after_delete)
    assert not result["blocked"] and result["successful_jobs"] == 1 and state == "23503"
    with factory() as db:
        assert db.get(JobRun, job_id) is None
        assert db.scalar(sa.select(sa.func.count()).select_from(Base.metadata.tables[name])) == 0


def test_two_cleaners_do_not_double_count_or_deadlock(retention_db):
    factory, engine = retention_db
    with factory() as db:
        job_id = old_job(db)
    barrier = Barrier(2, timeout=10)

    def before_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT job_run.id") and "FOR UPDATE" in statement:
            barrier.wait()

    def cleanup():
        with factory() as db:
            return run_retention(db, now=NOW, policy=ENABLED)

    sa.event.listen(engine, "before_cursor_execute", before_delete)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(cleanup) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
    finally:
        sa.event.remove(engine, "before_cursor_execute", before_delete)
    assert all(not result["blocked"] for result in results)
    assert sum(result["successful_jobs"] for result in results) == 1
    with factory() as db:
        assert db.get(JobRun, job_id) is None


def test_database_failure_rolls_back_jobs_and_all_log_deletes(retention_db):
    factory, engine = retention_db
    with factory() as db:
        job_id = old_job(db)
        log = ProviderApiLog(provider="synthetic", api_name="daily", status="SUCCESS",
                             created_at=NOW - timedelta(days=400))
        heartbeat = ServiceHeartbeat(service_name="worker", instance_id="synthetic-worker",
                                     started_at=NOW - timedelta(days=401),
                                     heartbeat_at=NOW - timedelta(days=400), version="synthetic")
        db.add_all([log, heartbeat])
        db.commit()
        log_id, heartbeat_id = log.id, heartbeat.id
    with engine.begin() as conn:
        conn.execute(sa.text("""CREATE FUNCTION retention_test_failure() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected failure'; END $$"""))
        conn.execute(sa.text("""CREATE TRIGGER retention_test_failure BEFORE DELETE
            ON service_heartbeat FOR EACH ROW EXECUTE FUNCTION retention_test_failure()"""))
    with factory() as db:
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert result["blocked"] and result["error_code"] == "RETENTION_DATABASE_ERROR"
        assert result["successful_jobs"] == result["provider_api_log"] == 0
        assert db.get(JobRun, job_id) is not None and db.get(ProviderApiLog, log_id) is not None
        assert db.get(ServiceHeartbeat, heartbeat_id) is not None


@pytest.mark.parametrize("kind", ["backtest", "frozen"])
def test_reference_committed_after_lock_query_snapshot_cannot_be_set_null(retention_db, kind):
    factory, engine = retention_db
    with factory() as db:
        job_id = old_job(db)
    gate_key = uuid.uuid4().int % (2**62)
    injected = Event()

    def pause_lock_query(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT job_run.id") and "FOR UPDATE" in statement:
            # Only a test barrier: the statement snapshot exists before LockRows can run.
            statement = statement.replace(
                "FROM job_run \n",
                "FROM job_run CROSS JOIN (SELECT pg_advisory_xact_lock("
                f"{gate_key})) AS retention_test_barrier \n", 1,
            )
            injected.set()
        return statement, parameters

    def cleanup():
        with factory() as db:
            return run_retention(db, now=NOW, policy=ENABLED)

    sa.event.listen(engine, "before_cursor_execute", pause_lock_query, retval=True)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as gate:
            gate.execute(sa.text("SELECT pg_advisory_lock(:key)"), {"key": gate_key})
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(cleanup)
                try:
                    assert injected.wait(10)
                    deadline = monotonic() + 5
                    while not gate.scalar(sa.text("""SELECT EXISTS (
                        SELECT 1 FROM pg_stat_activity WHERE wait_event = 'advisory'
                        AND query LIKE '%retention_test_barrier%')""")):
                        assert monotonic() < deadline
                        sleep(0.01)
                    with factory() as writer:
                        writer.execute(sa.text("SET LOCAL lock_timeout = '1s'"))
                        if kind == "backtest":
                            reference(writer, "portfolio_backtest_run", "job_id", job_id)
                        else:
                            from tests.integration.test_m17_1_1_retention_frozen import snapshot

                            snapshot(writer, job_id)
                        writer.commit()
                finally:
                    gate.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": gate_key})
                result = future.result(timeout=20)
    finally:
        sa.event.remove(engine, "before_cursor_execute", pause_lock_query)
    assert not result["blocked"] and result["successful_jobs"] == 0
    assert result["protected_referenced_jobs"] == 1
    with factory() as db:
        assert db.get(JobRun, job_id) is not None
        if kind == "backtest":
            column = Base.metadata.tables["portfolio_backtest_run"].c.job_id
            assert db.scalar(sa.select(column)) == job_id
        else:
            table = Base.metadata.tables["decision_observation"]
            assert db.scalar(sa.select(sa.func.count()).select_from(table)) == 1


def test_lost_commit_response_does_not_misreport_a_real_commit_as_zero_deletions(
    retention_db, monkeypatch,
):
    factory, _ = retention_db
    with factory() as db:
        identity = old_job(db)
        original_commit = db.commit

        def lose_response():
            original_commit()
            raise OperationalError("synthetic lost commit response", {}, OSError(),
                                   connection_invalidated=True)

        monkeypatch.setattr(db, "commit", lose_response)
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert result["blocked"] and result["commit_outcome_unknown"]
        assert result["error_code"] == "RETENTION_COMMIT_OUTCOME_UNKNOWN"
        assert result["successful_jobs"] is None and result["deleted_success_jobs"] is None
    with factory() as db:
        # The server really committed; only the response was fault-injected.
        assert db.get(JobRun, identity) is None
