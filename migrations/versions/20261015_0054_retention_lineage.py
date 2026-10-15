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
            SELECT i.indisvalid, i.indisready,
                   pg_get_indexdef(i.indexrelid) AS definition
            FROM pg_index i WHERE i.indexrelid = to_regclass(:name)
        """), {"name": name}).first()
        if existing is not None:
            definition = f"({', '.join(columns)})"
            if not existing.indisvalid or not existing.indisready or (
                definition not in existing.definition
                or f" ON public.{table} USING btree " not in existing.definition
                or " WHERE " in existing.definition
            ):
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
