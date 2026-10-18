"""Additive data queue lifecycle; historical timestamps/identities stay unchanged."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0057_data_queue"
down_revision = "0056_suspend_timing_text"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    for name in ("execution_started_at", "cancel_requested_at", "last_progress_at"):
        op.add_column("job_run", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("job_run", sa.Column("request_fingerprint", sa.String(128), nullable=True))
    op.add_column("job_run", sa.Column("execution_token", postgresql.UUID(), nullable=True))
    for name in ("parent_job_id", "depends_on_job_id"):
        op.add_column("job_run", sa.Column(name, postgresql.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_job_run_{name}_job_run", "job_run", "job_run", [name], ["id"], ondelete="RESTRICT"
        )
        op.create_index(
            "idx_job_parent" if name == "parent_job_id" else "idx_job_dependency", "job_run", [name]
        )
    op.create_check_constraint("job_no_self_dependency", "job_run", "depends_on_job_id <> id")
    op.create_check_constraint("job_no_self_parent", "job_run", "parent_job_id <> id")
    op.create_index("idx_job_data_queue", "job_run", ["status", "started_at", "id"])
    op.create_index(
        "uq_job_active_fingerprint",
        "job_run",
        ["request_fingerprint"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('QUEUED','RUNNING') AND request_fingerprint IS NOT NULL"
        ),
    )
    op.execute("""
        CREATE FUNCTION protect_data_queue_links() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target uuid;
        BEGIN
          IF TG_OP = 'UPDATE' THEN
            IF NEW.parent_job_id IS DISTINCT FROM OLD.parent_job_id OR
               NEW.depends_on_job_id IS DISTINCT FROM OLD.depends_on_job_id THEN
              RAISE EXCEPTION 'JOB_QUEUE_LINKS_IMMUTABLE' USING ERRCODE = '23514';
            END IF;
          ELSE
            FOREACH target IN ARRAY ARRAY[NEW.parent_job_id, NEW.depends_on_job_id] LOOP
              IF target IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM job_run j WHERE j.id = target AND j.parent_job_id IS NULL
                  AND j.job_type IN ('daily','sync_basic','backfill','recalculate',
                                     'validate_data','catchup')
              ) THEN
                RAISE EXCEPTION 'JOB_QUEUE_LINK_TARGET_INVALID' USING ERRCODE = '23514';
              END IF;
            END LOOP;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER protect_data_queue_links BEFORE INSERT OR UPDATE OF
          parent_job_id, depends_on_job_id ON job_run
          FOR EACH ROW EXECUTE FUNCTION protect_data_queue_links();
    """)


def downgrade():
    # Never erase a live new-format queue merely to start an old Worker.
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM job_run WHERE request_fingerprint IS NOT NULL "
            "AND status IN ('QUEUED','RUNNING'))"
        )
    ):
        raise RuntimeError("active data queue exists; freeze and reconcile before downgrade")
    op.execute("DROP TRIGGER protect_data_queue_links ON job_run")
    op.execute("DROP FUNCTION protect_data_queue_links()")
    op.drop_index("uq_job_active_fingerprint", "job_run")
    op.drop_index("idx_job_data_queue", "job_run")
    for name in ("parent_job_id", "depends_on_job_id"):
        op.drop_index(
            "idx_job_parent" if name == "parent_job_id" else "idx_job_dependency", "job_run"
        )
        op.drop_constraint(f"fk_job_run_{name}_job_run", "job_run", type_="foreignkey")
    for name in ("job_no_self_dependency", "job_no_self_parent"):
        op.drop_constraint(name, "job_run", type_="check")
    for name in (
        "execution_started_at",
        "cancel_requested_at",
        "last_progress_at",
        "request_fingerprint",
        "execution_token",
        "parent_job_id",
        "depends_on_job_id",
    ):
        op.drop_column("job_run", name)
