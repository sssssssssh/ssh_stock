"""Add immutable M16.4 research report snapshots and comparisons.

Revision ID: 0050_m16_4_reports
Revises: 0049_m16_2_1_hash_name
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_m16_4_reports"
down_revision: str | None = "0049_m16_2_1_hash_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_research_report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column(
            "report_version",
            sa.String(length=32),
            server_default="m16.4-v1",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("source_answer_status", sa.String(length=32), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "source_contract_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "report_type IN ('market_review', 'opportunity_review', "
            "'strategy_review', 'oos_review')",
            name="ck_agent_research_report_type",
        ),
        sa.CheckConstraint(
            "source_answer_status IN ('COMPLETED', 'PARTIAL_VERIFIED')",
            name="ck_agent_research_report_answer_status",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$' AND snapshot_hash ~ '^[0-9a-f]{64}$'",
            name="ck_agent_research_report_hashes",
        ),
        sa.CheckConstraint(
            "octet_length(snapshot_json::text) <= 262144",
            name="ck_agent_research_report_snapshot_size",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["app_user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id", "source_chat_id"],
            ["agent_chat_message.id", "agent_chat_message.session_id"],
            name="fk_agent_research_report_source_message",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_turn_id"], ["agent_chat_turn.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id", "request_id", name="uq_agent_research_report_request"
        ),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_agent_research_report_owner"),
    )
    op.create_foreign_key(
        "fk_agent_research_report_parent_owner",
        "agent_research_report",
        "agent_research_report",
        ["parent_report_id", "owner_user_id"],
        ["id", "owner_user_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_agent_research_report_owner_created",
        "agent_research_report",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "idx_agent_research_report_owner_source_message",
        "agent_research_report",
        ["owner_user_id", "source_message_id"],
    )

    op.create_table(
        "agent_research_report_comparison",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("left_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("right_report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column(
            "reason_codes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("left_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("right_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("comparison_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('COMPARABLE', 'CONTEXT_REQUIRED', 'INCOMPATIBLE')",
            name="ck_agent_research_report_comparison_state",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$' AND "
            "left_snapshot_hash ~ '^[0-9a-f]{64}$' AND "
            "right_snapshot_hash ~ '^[0-9a-f]{64}$' AND "
            "comparison_hash ~ '^[0-9a-f]{64}$'",
            name="ck_agent_research_report_comparison_hashes",
        ),
        sa.CheckConstraint(
            "left_report_id <> right_report_id",
            name="ck_agent_research_report_comparison_distinct",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["app_user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["left_report_id", "owner_user_id"],
            ["agent_research_report.id", "agent_research_report.owner_user_id"],
            name="fk_agent_research_report_comparison_left_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["right_report_id", "owner_user_id"],
            ["agent_research_report.id", "agent_research_report.owner_user_id"],
            name="fk_agent_research_report_comparison_right_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "request_id",
            name="uq_agent_research_report_comparison_request",
        ),
    )
    op.create_index(
        "idx_agent_research_report_comparison_owner_created",
        "agent_research_report_comparison",
        ["owner_user_id", "created_at"],
    )

    op.execute(
        """
        CREATE FUNCTION prevent_agent_research_report_rewrite()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'archived_at') IS DISTINCT FROM
               (to_jsonb(OLD) - 'archived_at') THEN
                RAISE EXCEPTION 'agent research report snapshots are immutable';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER trg_agent_research_report_immutable
        BEFORE UPDATE ON agent_research_report
        FOR EACH ROW EXECUTE FUNCTION prevent_agent_research_report_rewrite();

        CREATE FUNCTION prevent_agent_research_report_comparison_rewrite()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'agent research report comparisons are immutable';
        END;
        $$;
        CREATE TRIGGER trg_agent_research_report_comparison_immutable
        BEFORE UPDATE ON agent_research_report_comparison
        FOR EACH ROW EXECUTE FUNCTION prevent_agent_research_report_comparison_rewrite();
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    report_count = connection.scalar(sa.text("SELECT count(*) FROM agent_research_report"))
    comparison_count = connection.scalar(
        sa.text("SELECT count(*) FROM agent_research_report_comparison")
    )
    if report_count or comparison_count:
        raise RuntimeError("refusing to downgrade M16.4 while report data exists")
    op.execute(
        "DROP TRIGGER trg_agent_research_report_comparison_immutable "
        "ON agent_research_report_comparison"
    )
    op.execute("DROP FUNCTION prevent_agent_research_report_comparison_rewrite()")
    op.execute("DROP TRIGGER trg_agent_research_report_immutable ON agent_research_report")
    op.execute("DROP FUNCTION prevent_agent_research_report_rewrite()")
    op.drop_index(
        "idx_agent_research_report_comparison_owner_created",
        table_name="agent_research_report_comparison",
    )
    op.drop_table("agent_research_report_comparison")
    op.drop_index(
        "idx_agent_research_report_owner_source_message",
        table_name="agent_research_report",
    )
    op.drop_index(
        "idx_agent_research_report_owner_created", table_name="agent_research_report"
    )
    op.drop_table("agent_research_report")
