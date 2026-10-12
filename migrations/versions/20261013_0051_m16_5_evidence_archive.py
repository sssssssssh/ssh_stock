"""Append M16.5 frozen tool evidence archives without backfilling history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql.naming import conv

revision: str = "0051_m16_5_evidence_archive"
down_revision: str | None = "0050_m16_4_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns():
    return [
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def _constraints(name):
    return [
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["chat_id", "owner_user_id"],
            ["agent_chat_session.id", "agent_chat_session.owner_user_id"],
            name=f"fk_{name}_chat_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id", "chat_id"],
            ["agent_chat_turn.id", "agent_chat_turn.session_id"],
            name=f"fk_{name}_turn_chat",
            ondelete="RESTRICT",
        ),
    ]


def _text(name, length=64, nullable=False):
    return sa.Column(name, sa.String(length), nullable=nullable)


def _json(name):
    return sa.Column(name, pg.JSONB(), nullable=False)


def _check(expression, name):
    return sa.CheckConstraint(expression, name=conv(name))


TABLES = [
    ("agent_tool_result_archive", "agent_tool_archive"),
    ("agent_evidence_archive_binding", "agent_evidence_binding"),
    ("agent_turn_archive_manifest", "agent_archive_manifest"),
]


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_agent_chat_session_archive_owner", "agent_chat_session", ["id", "owner_user_id"]
    )
    op.create_unique_constraint(
        "uq_agent_chat_turn_archive_session", "agent_chat_turn", ["id", "session_id"]
    )
    op.create_table(
        "agent_tool_result_archive",
        *_columns(),
        _text("tool_call_id", 128),
        _text("tool_name"),
        _text("tool_version", 32),
        _text("archive_schema_version"),
        _text("projector_version"),
        _json("arguments_json"),
        _json("input_schema_json"),
        _text("arguments_hash"),
        _text("registry_schema_hash"),
        _json("payload_json"),
        _text("payload_hash"),
        sa.Column("payload_size_bytes", sa.Integer(), nullable=False),
        _text("status", 16),
        _text("cache_origin_call_id", 128, nullable=True),
        *_constraints("agent_tool_archive"),
        sa.UniqueConstraint("turn_id", "tool_call_id", name=conv("uq_agent_tool_archive_call")),
        sa.UniqueConstraint(
            "id", "owner_user_id", "turn_id", name=conv("uq_agent_tool_archive_owner")
        ),
        sa.ForeignKeyConstraint(
            ["turn_id", "tool_call_id"],
            ["agent_chat_tool_call.turn_id", "agent_chat_tool_call.tool_call_id"],
            name="fk_agent_tool_archive_audit",
            ondelete="RESTRICT",
        ),
        _check("status = 'READY'", "ck_agent_tool_archive_status"),
        _check(
            "payload_size_bytes BETWEEN 1 AND 65536 AND octet_length(payload_json::text) <= 65536",
            "ck_agent_tool_archive_size",
        ),
        _check(
            "arguments_hash ~ '^[0-9a-f]{64}$' AND registry_schema_hash ~ '^[0-9a-f]{64}$' "
            "AND payload_hash ~ '^[0-9a-f]{64}$'",
            "ck_agent_tool_archive_hashes",
        ),
    )
    op.create_table(
        "agent_evidence_archive_binding",
        *_columns(),
        sa.Column("tool_result_archive_id", pg.UUID(as_uuid=True), nullable=False),
        _text("evidence_id", 128),
        _json("ref_json"),
        _text("ref_hash"),
        _json("source_projection_json"),
        _text("source_projection_hash"),
        _text("projection_version"),
        _text("record_path", 160),
        *_constraints("agent_evidence_binding"),
        sa.UniqueConstraint("turn_id", "evidence_id", name=conv("uq_agent_evidence_binding_ref")),
        sa.ForeignKeyConstraint(
            ["tool_result_archive_id", "owner_user_id", "turn_id"],
            [
                "agent_tool_result_archive.id",
                "agent_tool_result_archive.owner_user_id",
                "agent_tool_result_archive.turn_id",
            ],
            name="fk_agent_evidence_binding_tool_owner",
            ondelete="RESTRICT",
        ),
        _check(
            "ref_hash ~ '^[0-9a-f]{64}$' AND source_projection_hash ~ '^[0-9a-f]{64}$'",
            "ck_agent_evidence_binding_hashes",
        ),
        _check(
            "octet_length(source_projection_json::text) <= 655360", "ck_agent_evidence_binding_size"
        ),
    )
    op.create_index(
        "idx_agent_evidence_binding_tool",
        "agent_evidence_archive_binding",
        ["tool_result_archive_id"],
    )
    op.create_table(
        "agent_turn_archive_manifest",
        *_columns(),
        sa.Column("assistant_message_id", pg.UUID(as_uuid=True), nullable=False),
        _text("manifest_version"),
        _text("archive_status", 16),
        _json("manifest_json"),
        _text("manifest_hash"),
        _text("claim_digest"),
        _text("compiled_message_digest"),
        *_constraints("agent_archive_manifest"),
        sa.UniqueConstraint("turn_id", name=conv("uq_agent_archive_manifest_turn")),
        sa.ForeignKeyConstraint(
            ["assistant_message_id", "chat_id"],
            ["agent_chat_message.id", "agent_chat_message.session_id"],
            name="fk_agent_archive_manifest_assistant",
            ondelete="RESTRICT",
        ),
        _check(
            "archive_status IN ('COMPLETE', 'PARTIAL', 'UNAVAILABLE')",
            "ck_agent_archive_manifest_status",
        ),
        _check(
            "manifest_hash ~ '^[0-9a-f]{64}$' AND claim_digest ~ '^[0-9a-f]{64}$' "
            "AND compiled_message_digest ~ '^[0-9a-f]{64}$'",
            "ck_agent_archive_manifest_hashes",
        ),
        _check("octet_length(manifest_json::text) <= 655360", "ck_agent_archive_manifest_size"),
    )
    op.execute("""CREATE FUNCTION prevent_agent_archive_rewrite()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'agent evidence archives are immutable'; END; $$;""")
    for table, name in TABLES:
        op.create_index(f"idx_{name}_owner_turn", table, ["owner_user_id", "turn_id"])
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_agent_archive_rewrite()"
        )


def downgrade() -> None:
    for table, _ in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("refusing to downgrade M16.5 while any archive data exists")
    for table, _ in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION prevent_agent_archive_rewrite()")
    op.drop_constraint("uq_agent_chat_turn_archive_session", "agent_chat_turn", type_="unique")
    op.drop_constraint("uq_agent_chat_session_archive_owner", "agent_chat_session", type_="unique")
