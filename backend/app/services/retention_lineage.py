"""Typed, exhaustive JobRun references; never materialize the referenced UUID universe."""

from sqlalchemy import or_, select, text

from app.models import Base
from app.models.job import JobRun

JOB_REFERENCES = (
    ("data_dirty_range", "source_job_id"),
    ("data_quality_daily", "job_id"),
    ("market_daily", "calc_run_id"),
    ("paper_day_run", "job_id"),
    ("portfolio_backtest_run", "job_id"),
    ("sector_factor_daily", "calc_run_id"),
    ("stock_factor_daily", "calc_run_id"),
    ("stock_opportunity_daily", "calc_run_id"),
    ("stock_state_daily", "calc_run_id"),
    ("stock_trade_status_daily", "calc_run_id"),
    ("strategy_signal", "calc_run_id"),
    ("theme_factor_daily", "calc_run_id"),
)

SCHEMA_REFERENCES = text("""
SELECT c.relname AS table_name, a.attname AS column_name,
       EXISTS (SELECT 1 FROM pg_constraint f WHERE f.contype = 'f'
          AND f.conrelid = c.oid AND f.confrelid = 'job_run'::regclass
          AND f.conkey = ARRAY[a.attnum] AND f.confkey = ARRAY[
              (SELECT attnum FROM pg_attribute WHERE attrelid = 'job_run'::regclass
               AND attname = 'id')]
          AND f.confdeltype IN ('r', 'a', 'n')) AS has_fk,
       EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid
          AND i.indisvalid AND i.indisready AND i.indkey[0] = a.attnum
          AND i.indpred IS NULL AND i.indexprs IS NULL) AS has_index
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p')
  AND a.attnum > 0 AND NOT a.attisdropped AND a.atttypid = 'uuid'::regtype
  AND (a.attname IN ('calc_run_id', 'source_job_id', 'job_id') OR EXISTS (
       SELECT 1 FROM pg_constraint f WHERE f.contype = 'f'
       AND f.conrelid = c.oid AND f.confrelid = 'job_run'::regclass
       AND a.attnum = ANY(f.conkey)))
ORDER BY c.relname, a.attname
""")


class RetentionBlocked(RuntimeError):
    pass


def discovered_orm_references(metadata=None):
    metadata = metadata if metadata is not None else Base.metadata
    return {
        (table.name, column.name)
        for table in metadata.tables.values() for column in table.c
        if column.name in ("calc_run_id", "source_job_id", "job_id")
        or any(fk.target_fullname == "job_run.id" for fk in column.foreign_keys)
    }


def assert_reference_schema(db):
    if discovered_orm_references() != set(JOB_REFERENCES):
        raise RetentionBlocked("RETENTION_REFERENCE_MANIFEST_MISMATCH")
    rows = db.execute(SCHEMA_REFERENCES).all()
    if {(r.table_name, r.column_name) for r in rows} != set(JOB_REFERENCES):
        raise RetentionBlocked("RETENTION_REFERENCE_SCHEMA_MISMATCH")
    if any(not r.has_fk or not r.has_index for r in rows):
        raise RetentionBlocked("RETENTION_REFERENCE_PROTECTION_UNAVAILABLE")


def referenced_job():
    return or_(*(
        select(Base.metadata.tables[table].c[column]).where(
            Base.metadata.tables[table].c[column] == JobRun.id,
        ).exists()
        for table, column in JOB_REFERENCES
    ))
