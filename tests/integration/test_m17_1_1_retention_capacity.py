import json
import os
from pathlib import Path
from time import perf_counter

import sqlalchemy as sa
from app.core.retention_config import RetentionPolicy
from app.models.job import JobRun, ProviderApiLog
from app.models.market_data import StockFactorDaily
from app.services.retention import eligible_jobs, run_retention
from app.services.retention_indexes import prepare_retention_indexes
from app.services.retention_lineage import referenced_job

from tests.integration.test_m17_1_1_retention import ENABLED, NOW, migrate, old_job
from tests.integration.test_m17_1_1_retention import retention_db as retention_db


def emit(data):
    if destination := os.environ.get("M17_1_1_MEASUREMENT_PATH"):
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(data, default=str, sort_keys=True) + "\n")


def explain(db, query):
    sql = str(query.compile(dialect=db.get_bind().dialect,
                            compile_kwargs={"literal_binds": True}))
    return db.scalar(sa.text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql))[0]


def nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


def test_million_row_provenance_explain_and_actual_cleanup_are_bounded(retention_db):
    factory, engine = retention_db
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    with factory() as db:
        ids = [old_job(db) for _ in range(10)]
        db.execute(sa.text("""
            INSERT INTO stock_factor_daily (trade_date, ts_code, eligible, calc_run_id)
            SELECT DATE '2020-01-01' + ((n - 1) / 1000)::int,
                   'T' || lpad((n % 1000)::text, 6, '0') || '.SZ', false, :job
            FROM generate_series(1, 1000000) AS n
        """), {"job": ids[0]})
        db.commit()
        db.execute(sa.text("ANALYZE stock_factor_daily"))
        before = explain(db, sa.select(StockFactorDaily.calc_run_id).where(
            StockFactorDaily.calc_run_id == ids[1],
        ).limit(1))
        db.commit()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        prepared = prepare_retention_indexes(connection, apply=True)
        assert all(row["state"] in ("READY", "CREATED") for row in prepared)
    migrate(engine, "head")
    with factory() as db:
        after = explain(db, sa.select(StockFactorDaily.calc_run_id).where(
            StockFactorDaily.calc_run_id == ids[1],
        ).limit(1))
        actual = explain(db, sa.select(JobRun.id).where(*eligible_jobs(NOW), ~referenced_job()))
        assert any(node.get("Index Name") == "ix_stock_factor_daily_calc_run_id"
                   for node in nodes(after["Plan"]))
        assert db.scalar(sa.select(sa.func.count()).select_from(StockFactorDaily)) == 1000000
        db.commit()
        statements = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sa.event.listen(engine, "before_cursor_execute", capture)
        started = perf_counter()
        try:
            result = run_retention(db, now=NOW, policy=ENABLED)
        finally:
            elapsed = perf_counter() - started
            sa.event.remove(engine, "before_cursor_execute", capture)
        assert not result["blocked"], result
        assert result["candidate_scan_rows"] == 10 and result["protected_referenced_jobs"] == 1
        assert result["successful_jobs"] == 9 and result["missing_provenance_references"] == 0
        assert result["sql_count"] == len(statements) <= 60
        assert elapsed < 15
        assert not any("record_json" in sql or "job_metadata" in sql for sql in statements)
        assert db.get(JobRun, ids[0]) is not None
        assert db.scalar(sa.select(sa.func.count()).select_from(StockFactorDaily)) == 1000000
        emit({"kind": "million_row_retention", "derived_rows": 1000000,
              "elapsed_seconds": elapsed, "result": result, "before_index_plan": before,
              "after_index_plan": after, "actual_antijoin_plan": actual})


def test_candidate_budget_rejects_all_deletes_with_explicit_unknown_totals(retention_db):
    factory, _ = retention_db
    with factory() as db:
        ids = [old_job(db), old_job(db)]
        result = run_retention(db, now=NOW, policy=ENABLED.model_copy(update={
            "max_candidate_rows": 1,
        }))
        assert result["error_code"] == "RETENTION_CANDIDATE_BUDGET_EXCEEDED"
        assert result["candidate_scan_rows"] == 2
        assert result["eligible_success_jobs"] is None
        assert result["protected_referenced_jobs"] is None
        assert result["successful_jobs"] == 0 and result["error_count"] == 1
        assert all(db.get(JobRun, identity) is not None for identity in ids)


def test_actual_slow_delete_timeout_rolls_back_earlier_job_deletion(retention_db):
    factory, engine = retention_db
    with factory() as db:
        identity = old_job(db)
        db.add(ProviderApiLog(provider="synthetic", api_name="daily", status="SUCCESS",
                              created_at=NOW.replace(year=2020)))
        db.commit()
    with engine.begin() as connection:
        connection.execute(sa.text("""CREATE FUNCTION retention_slow_delete() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(0.2); RETURN OLD; END $$"""))
        connection.execute(sa.text("""CREATE TRIGGER retention_slow_delete BEFORE DELETE
            ON provider_api_log FOR EACH ROW EXECUTE FUNCTION retention_slow_delete()"""))
    with factory() as db:
        result = run_retention(db, now=NOW, policy=RetentionPolicy(
            job_deletion_enabled=True, statement_timeout_ms=30,
        ))
        assert result["blocked"] and result["error_code"] == "RETENTION_RETRY_REQUIRED"
        assert result["successful_jobs"] == result["provider_api_log"] == 0
        assert db.get(JobRun, identity) is not None
        assert db.scalar(sa.select(sa.func.count()).select_from(ProviderApiLog)) == 1


def test_repeatable_read_cleanup_is_rejected_not_silently_used_for_set_null_fk(retention_db):
    factory, _ = retention_db
    with factory() as db:
        identity = old_job(db)
    with factory() as db:
        db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert result["error_code"] == "RETENTION_REQUIRES_READ_COMMITTED"
        assert db.get(JobRun, identity) is not None
