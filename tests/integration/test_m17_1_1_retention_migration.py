import json

import pytest
import sqlalchemy as sa
from app.models import Base
from app.models.job import JobRun
from app.models.market_data import StockFactorDaily
from app.services.retention import run_retention
from app.services.retention_indexes import prepare_retention_indexes
from app.services.retention_lineage import (
    JOB_REFERENCES,
    RetentionBlocked,
    reference_inventory,
)
from sqlalchemy.exc import DBAPIError

from tests.integration.test_m17_1_1_retention import NOW, migrate, old_job, reference
from tests.integration.test_m17_1_1_retention import retention_db as retention_db
from tests.integration.test_m17_1_1_retention_capacity import emit


def test_actual_inventory_fk_index_and_bounded_reference_counts(retention_db):
    factory, _ = retention_db
    with factory() as db:
        identity = old_job(db)
        reference(db, "stock_factor_daily", "calc_run_id", identity)
        reference(db, "stock_factor_daily", "calc_run_id", identity, code="T002.SZ")
        db.commit()
        data = reference_inventory(db, max_rows=1)
        assert {(row["table_name"], row["column_name"]) for row in data["references"]} == (
            set(JOB_REFERENCES)
        )
        assert all(row["has_fk"] and row["has_index"] for row in data["references"])
        factor = next(row for row in data["references"]
                      if row["table_name"] == "stock_factor_daily")
        assert factor["reference_rows_observed"] == 2 and factor["reference_rows_truncated"]
        assert len(data["foreign_keys"]) == 12
        legacy = {row["source_table"]: row for row in data["foreign_keys"]}
        assert "SET NULL" in legacy["portfolio_backtest_run"]["definition"]
        assert "RESTRICT" in legacy["paper_day_run"]["definition"]
        assert sum(not row["convalidated"] for row in data["foreign_keys"]) == 10
        emit({"kind": "physical_reference_inventory", "server_major": 17, "inventory": data})


def test_failed_concurrent_index_requires_explicit_repair_and_safe_retry(retention_db):
    factory, engine = retention_db
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    with factory() as db:
        identity = old_job(db)
        reference(db, "stock_factor_daily", "calc_run_id", identity)
        db.commit()
        before = db.execute(sa.select(StockFactorDaily.__table__)).all()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        with pytest.raises(DBAPIError):
            # Row-dependent division fails in the concurrent build, leaving a real INVALID index.
            connection.execute(sa.text("""CREATE INDEX CONCURRENTLY
                ix_stock_factor_daily_calc_run_id ON stock_factor_daily (calc_run_id)
                WHERE length(ts_code) / (length(ts_code) - length(ts_code)) > 0"""))
        assert connection.scalar(sa.text("""SELECT NOT indisvalid FROM pg_index
            WHERE indexrelid = 'ix_stock_factor_daily_calc_run_id'::regclass"""))
        with pytest.raises(RetentionBlocked, match="RETENTION_INDEX_REQUIRES_OPERATOR_REPAIR"):
            prepare_retention_indexes(connection, apply=True)
    with pytest.raises(RuntimeError, match="RETENTION_INDEX_REQUIRES_OPERATOR_REPAIR"):
        migrate(engine, "head")
    with factory() as db:
        assert db.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0053_m17_decision_paper_foundation"
        )
        assert db.execute(sa.select(StockFactorDaily.__table__)).all() == before
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        # Explicit operator-equivalent repair only in this disposable database.
        connection.execute(sa.text("DROP INDEX CONCURRENTLY ix_stock_factor_daily_calc_run_id"))
        assert any(row["state"] == "MISSING" for row in prepare_retention_indexes(connection))
        assert any(row["state"] == "CREATED" for row in prepare_retention_indexes(
            connection, apply=True,
        ))
    migrate(engine, "head")
    with factory() as db:
        assert db.execute(sa.select(StockFactorDaily.__table__)).all() == before
        assert db.get(JobRun, identity) is not None
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    with factory() as db:
        assert db.execute(sa.select(StockFactorDaily.__table__)).all() == before
    migrate(engine, "head")


def test_missing_reference_budget_is_bounded_and_does_not_clear_or_forge_rows(retention_db):
    import uuid

    from app.core.retention_config import RetentionPolicy

    factory, engine = retention_db
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    lost = uuid.uuid4()
    with factory() as db:
        for number in range(3):
            reference(db, "stock_factor_daily", "calc_run_id", lost, code=f"T{number}.SZ")
        db.commit()
    migrate(engine, "head")
    with factory() as db:
        result = run_retention(db, now=NOW, policy=RetentionPolicy(
            job_deletion_enabled=True, max_missing_references=2,
        ))
        assert result["error_code"] == "RETENTION_MISSING_REFERENCE_BUDGET_EXCEEDED"
        assert result["missing_provenance_references"] is None
        assert db.get(JobRun, lost) is None
        assert db.scalar(sa.select(sa.func.count()).select_from(StockFactorDaily)) == 3


def test_disabled_or_dry_run_never_loads_legacy_job_metadata_or_logs_diagnostics(
    retention_db, capsys,
):
    from loguru import logger

    factory, _ = retention_db
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        with factory() as db:
            identity = old_job(db)
            db.get(JobRun, identity).job_metadata = {
                "private_cookie": "synthetic-must-not-log", "owner_user_id": "not-for-logs",
            }
            db.commit()
            result = run_retention(db, now=NOW, dry_run=True, include_diagnostics=True)
            assert not result["blocked"]
            assert "job_metadata" not in json.dumps(result)
        assert "synthetic-must-not-log" not in "".join(messages)
        assert "not-for-logs" not in "".join(messages)
    finally:
        logger.remove(sink)


def test_new_nullable_fk_does_not_rewrite_unknown_legacy_calculation_fields(retention_db):
    factory, _ = retention_db
    with factory() as db:
        table = Base.metadata.tables["stock_factor_daily"]
        reference(db, "stock_factor_daily", "calc_run_id", None)
        db.commit()
        before = db.execute(sa.select(table)).all()
        result = run_retention(db, now=NOW, dry_run=True)
        assert result["missing_provenance_references"] == 0
        assert db.execute(sa.select(table)).all() == before


def test_old_age_only_delete_reproduces_orphan_then_new_retention_preserves_same_job(retention_db):
    from datetime import timedelta

    from tests.integration.test_m17_1_1_retention import ENABLED

    factory, engine = retention_db
    migrate(engine, "0053_m17_decision_paper_foundation", downgrade=True)
    with factory() as db:
        identity = old_job(db)
        reference(db, "stock_factor_daily", "calc_run_id", identity)
        db.commit()
        original = db.execute(sa.select(JobRun.__table__)).all()
        with db.begin_nested() as savepoint:
            count = db.execute(sa.delete(JobRun).where(
                JobRun.status.in_(("SUCCESS", "PARTIAL", "CANCELLED")),
                JobRun.finished_at < NOW - timedelta(days=180),
                JobRun.job_type.not_in(("PAPER_DAILY", "PAPER_REVIEW", "PAPER_OBSERVATION")),
            )).rowcount
            assert count == 1
            assert db.scalar(sa.select(sa.func.count()).select_from(JobRun)) == 0
            assert db.scalar(sa.select(StockFactorDaily.calc_run_id)) == identity
            savepoint.rollback()
        db.commit()
        assert db.execute(sa.select(JobRun.__table__)).all() == original
    migrate(engine, "head")
    with factory() as db:
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert not result["blocked"] and result["protected_referenced_jobs"] == 1
        assert result["successful_jobs"] == 0
        assert db.execute(sa.select(JobRun.__table__)).all() == original
        emit({"kind": "old_rule_reproduction_then_protection", "old_deleted_jobs": count,
              "old_orphan_rows": 1, "new_result": result})
