"""Typed and canonical frozen Job references, without materializing the UUID universe."""

from sqlalchemy import func, or_, select, text

from app.models import Base
from app.models.job import JobRun
from app.services.retention_frozen import FROZEN_ISSUES, FROZEN_SCHEMA, frozen_job_reference

JOB_REFERENCES = (
    ("job_run", "parent_job_id"),
    ("job_run", "depends_on_job_id"),
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

INDEX_SPECS = tuple(
    (f"ix_{table}_{column}", table, (column,))
    for table, column in JOB_REFERENCES if table not in {"portfolio_backtest_run", "job_run"}
) + (("idx_job_run_retention", "job_run", ("status", "finished_at", "id")),)
# The online prebuild targets legacy 0053 -> 0054. The new nullable columns do
# not exist there; their indexes are owned by the 0057 maintenance migration.

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
    if not db.scalar(FROZEN_SCHEMA):
        raise RetentionBlocked("RETENTION_FROZEN_PROTECTION_UNAVAILABLE")


def referenced_job():
    typed = []
    for table, column in JOB_REFERENCES:
        source = Base.metadata.tables[table]
        if table == "job_run":
            source = source.alias(f"referencing_{column}")
        typed.append(select(source.c[column]).where(source.c[column] == JobRun.id).exists())
    return or_(*typed, frozen_job_reference())


def reference_inventory(db, *, max_rows=10000):
    if not 1 <= max_rows <= 100000:
        raise ValueError("RETENTION_INVENTORY_INVALID_LIMIT")
    db.execute(text("SET TRANSACTION READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '3s'"))
    db.execute(text("SET LOCAL lock_timeout = '1s'"))
    rows = [dict(row._mapping) for row in db.execute(SCHEMA_REFERENCES)]
    for row in rows:
        key = (row["table_name"], row["column_name"])
        if key not in JOB_REFERENCES:
            row["supported"] = False
            continue
        table = Base.metadata.tables[key[0]]
        if key[0] == "job_run":
            table = table.alias("referencing_job")
        column = table.c[key[1]]
        bounded = select(column).where(column.is_not(None)).limit(max_rows + 1).subquery()
        count = db.scalar(select(func.count()).select_from(bounded))
        missing = select(column).where(
            column.is_not(None), ~select(JobRun.id).where(JobRun.id == column).exists(),
        ).limit(max_rows + 1).subquery()
        lost = db.scalar(select(func.count()).select_from(missing))
        row.update(supported=True, reference_rows_observed=count,
                   reference_rows_truncated=count > max_rows,
                   missing_rows_observed=lost, missing_rows_truncated=lost > max_rows)
    fks = db.execute(text("""
        SELECT c.conrelid::regclass::text AS source_table, c.conname,
               c.convalidated, pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c WHERE c.contype = 'f' AND c.confrelid = 'job_run'::regclass
        ORDER BY source_table, c.conname
    """)).mappings().all()
    frozen_issues = db.execute(FROZEN_ISSUES, {"limit": max_rows + 1}).all()
    frozen = {"table": "decision_observation", "path": "data.candidates[].calc_run_id",
              "missing_observed": sum(row.issue == "MISSING" for row in frozen_issues),
              "invalid_observed": sum(row.issue == "INVALID" for row in frozen_issues),
              "truncated": len(frozen_issues) > max_rows,
              "protection_ready": db.scalar(FROZEN_SCHEMA)}
    indexes = db.execute(text("""
        SELECT p.tablename, p.indexname, p.indexdef, i.indisvalid, i.indisready
        FROM pg_indexes p JOIN pg_namespace n ON n.nspname = p.schemaname
        JOIN pg_class c ON c.relnamespace = n.oid AND c.relname = p.indexname
        JOIN pg_index i ON i.indexrelid = c.oid
        WHERE p.schemaname = current_schema() AND p.tablename = ANY(:tables)
        ORDER BY p.tablename, p.indexname
    """), {"tables": sorted({table for table, _ in JOB_REFERENCES}
                             | {"job_run", "decision_observation"})}).mappings()
    return {"references": rows, "foreign_keys": [dict(row) for row in fks],
            "frozen_references": frozen, "indexes": [dict(row) for row in indexes]}
