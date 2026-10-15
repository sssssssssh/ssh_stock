"""Preserve live calculation provenance without certifying legacy orphan references.

Revision ID: 0054_retention_lineage
Revises: 0053_m17_decision_paper_foundation
"""

import sqlalchemy as sa
from alembic import op

revision = "0054_retention_lineage"
down_revision = "0053_m17_decision_paper_foundation"
branch_labels = None
depends_on = None

# Frozen migration manifest; do not import the evolving application registry here.
REFERENCES = (
    ("data_dirty_range", "source_job_id"), ("data_quality_daily", "job_id"),
    ("market_daily", "calc_run_id"), ("sector_factor_daily", "calc_run_id"),
    ("stock_factor_daily", "calc_run_id"), ("stock_opportunity_daily", "calc_run_id"),
    ("stock_state_daily", "calc_run_id"), ("stock_trade_status_daily", "calc_run_id"),
    ("strategy_signal", "calc_run_id"), ("theme_factor_daily", "calc_run_id"),
)
INDEXES = (*REFERENCES, ("paper_day_run", "job_id"))


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
    bind.execute(sa.text("SET LOCAL statement_timeout = '30s'"))
    # Empty/test databases build transactionally. Online operators prebuild the same
    # indexes CONCURRENTLY; invalid or mismatched indexes must never be skipped.
    for table, column in (*INDEXES, ("job_run", "status")):
        name = f"ix_{table}_{column}" if table != "job_run" else "idx_job_run_retention"
        columns = [column] if table != "job_run" else ["status", "finished_at", "id"]
        existing = bind.execute(sa.text("""
            SELECT i.indisvalid, i.indisready, i.indisunique,
                   i.indrelid = to_regclass(:table_name) AS right_table,
                   i.indpred IS NULL AND i.indexprs IS NULL AS plain,
                   am.amname, i.indnkeyatts, i.indnatts,
                   ARRAY(SELECT a.attname FROM unnest(i.indkey)
                         WITH ORDINALITY AS k(attnum, position)
                         JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                         ORDER BY k.position) AS column_names
            FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_am am ON am.oid = c.relam WHERE i.indexrelid = to_regclass(:name)
        """), {"name": name, "table_name": table}).first()
        if existing is not None:
            if not (existing.indisvalid and existing.indisready and not existing.indisunique
                    and existing.right_table and existing.plain and existing.amname == "btree"
                    and existing.indnkeyatts == existing.indnatts == len(columns)
                    and list(existing.column_names) == columns):
                raise RuntimeError("RETENTION_INDEX_REQUIRES_OPERATOR_REPAIR")
        else:
            op.create_index(name, table, columns)
    for table, column in REFERENCES:
        op.create_foreign_key(
            f"fk_{table}_{column}_job_run", table, "job_run", [column], ["id"],
            ondelete="RESTRICT", postgresql_not_valid=True,
        )


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
    for table, column in reversed(REFERENCES):
        op.drop_constraint(f"fk_{table}_{column}_job_run", table, type_="foreignkey")
    for table, column in reversed(INDEXES):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
    op.drop_index("idx_job_run_retention", table_name="job_run")
