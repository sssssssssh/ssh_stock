"""Add empty publication storage without rewriting existing derived/history rows."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0058_data_publication"
down_revision = "0057_data_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.create_table(
        "data_schedule_intent",
        sa.Column("identity_key", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("identity", pg.JSONB(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("job_id", pg.UUID(), sa.ForeignKey("job_run.id", ondelete="RESTRICT")),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("queue_count", sa.Integer()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_schedule_intent_due",
        "data_schedule_intent",
        ["state", "next_attempt_at", "target_date"],
    )
    op.create_index("idx_schedule_intent_job", "data_schedule_intent", ["job_id"])
    op.create_table(
        "data_publication",
        sa.Column(
            "job_id", pg.UUID(), sa.ForeignKey("job_run.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column("execution_token", pg.UUID(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("identity", pg.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("publish_started_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("row_counts", pg.JSONB(), nullable=False),
        sa.CheckConstraint(
            "state IN ('PREPARING','PUBLISHED','ABORTED')", name="publication_state"
        ),
    )
    op.create_table(
        "data_publication_source",
        sa.Column(
            "publication_id",
            pg.UUID(),
            sa.ForeignKey("data_publication.job_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "source_job_id",
            pg.UUID(),
            sa.ForeignKey("job_run.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True)),
        sa.Column("validation", pg.JSONB()),
    )
    op.create_index("idx_publication_source_job", "data_publication_source", ["source_job_id"])
    op.create_table(
        "data_publication_row",
        sa.Column(
            "publication_id",
            pg.UUID(),
            sa.ForeignKey("data_publication.job_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("table_name", sa.String(64), primary_key=True),
        sa.Column("row_key", pg.JSONB(), primary_key=True),
        sa.Column("row_data", pg.JSONB()),
        sa.Column("base_row", pg.JSONB()),
        sa.Column("source_id", pg.UUID(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("trade_date", sa.Date()),
        sa.Column("entity_key", sa.String(64)),
        sa.CheckConstraint(
            "(is_deleted AND row_data IS NULL) OR (NOT is_deleted AND row_data IS NOT NULL)",
            name="candidate_row_data",
        ),
    )
    op.create_index(
        "idx_publication_row_date",
        "data_publication_row",
        ["publication_id", "table_name", "trade_date"],
    )
    op.create_index(
        "idx_publication_row_entity",
        "data_publication_row",
        ["publication_id", "table_name", "entity_key", "trade_date"],
    )
    op.create_table(
        "data_publication_preimage",
        sa.Column(
            "publication_id",
            pg.UUID(),
            sa.ForeignKey("data_publication.job_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("table_name", sa.String(64), primary_key=True),
        sa.Column("row_key", pg.JSONB(), primary_key=True),
        sa.Column("row_data", pg.JSONB(), nullable=False),
    )
    op.create_table(
        "data_publication_scope",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column(
            "publication_id",
            pg.UUID(),
            sa.ForeignKey("data_publication.job_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(64), nullable=False),
        sa.Column("source_id", pg.UUID(), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
    )
    op.create_index(
        "idx_publication_scope", "data_publication_scope", ["publication_id", "table_name"]
    )
    # Published candidates and preimages are audit evidence, not a GC surface.
    op.execute("""
    CREATE FUNCTION protect_data_publication_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE root uuid; current_state text;
    BEGIN
      IF TG_TABLE_NAME = 'data_publication' THEN
        IF OLD.state <> 'PREPARING' THEN
          RAISE EXCEPTION 'PUBLICATION_IMMUTABLE' USING ERRCODE = '23514';
        END IF;
      ELSE
        root := CASE WHEN TG_OP = 'DELETE' THEN OLD.publication_id ELSE NEW.publication_id END;
        SELECT state INTO current_state FROM data_publication WHERE job_id = root FOR KEY SHARE;
        IF current_state IS DISTINCT FROM 'PREPARING' THEN
          RAISE EXCEPTION 'PUBLICATION_EVIDENCE_IMMUTABLE' USING ERRCODE = '23514';
        END IF;
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END $$;
    CREATE TRIGGER protect_publication BEFORE UPDATE OR DELETE ON data_publication
      FOR EACH ROW EXECUTE FUNCTION protect_data_publication_evidence();
    """)
    for table in (
        "data_publication_row",
        "data_publication_source",
        "data_publication_preimage",
        "data_publication_scope",
    ):
        op.execute(
            f"CREATE TRIGGER protect_publication_evidence BEFORE INSERT OR UPDATE OR "
            f"DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION protect_data_publication_evidence()"
        )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM data_publication)")):
        raise RuntimeError("publication evidence exists; destructive downgrade refused")
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM data_schedule_intent)")):
        raise RuntimeError("schedule evidence exists; destructive downgrade refused")
    for table in (
        "data_publication_scope",
        "data_publication_preimage",
        "data_publication_row",
        "data_publication_source",
        "data_publication",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION protect_data_publication_evidence()")
    op.drop_table("data_schedule_intent")
