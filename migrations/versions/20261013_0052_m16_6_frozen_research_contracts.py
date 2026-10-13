"""Append M16.6 research contracts without changing 0051 archive contents."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.sql.naming import conv

revision: str = "0052_m16_6_frozen_research_contracts"
down_revision: str | None = "0051_m16_5_evidence_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns():
    return [
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def _owner_constraints(name):
    return [
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["chat_id", "owner_user_id"],
            ["agent_chat_session.id", "agent_chat_session.owner_user_id"],
            name=f"fk_{name}_chat_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id", "chat_id"],
            ["agent_chat_turn.id", "agent_chat_turn.session_id"],
            name=f"fk_{name}_turn_chat", ondelete="RESTRICT",
        ),
    ]


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_agent_archive_manifest_owner", "agent_turn_archive_manifest",
        ["id", "owner_user_id", "turn_id"],
    )
    op.create_table(
        "agent_frozen_research_contract",
        *_identity_columns(),
        sa.Column("tool_result_archive_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_kind", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(160), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("verification_scope", sa.String(64), nullable=False),
        sa.Column("contract_json", pg.JSONB(), nullable=False),
        sa.Column("contract_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        *_owner_constraints("agent_frozen_contract"),
        sa.ForeignKeyConstraint(
            ["tool_result_archive_id", "owner_user_id", "turn_id"],
            [
                "agent_tool_result_archive.id", "agent_tool_result_archive.owner_user_id",
                "agent_tool_result_archive.turn_id",
            ],
            name="fk_agent_frozen_contract_tool_owner", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tool_result_archive_id", "contract_kind", "subject_id", "role",
            name=conv("uq_agent_frozen_contract_source"),
        ),
        sa.UniqueConstraint(
            "id", "owner_user_id", "turn_id", name=conv("uq_agent_frozen_contract_owner"),
        ),
        sa.CheckConstraint(
            "contract_kind IN ('M14_EXACT_BUNDLE', 'M15_WINDOW_LINEAGE', 'M15_STUDY_AGGREGATE')",
            name=conv("ck_agent_frozen_contract_kind"),
        ),
        sa.CheckConstraint(
            "role IN ('LIVE', 'TRAIN', 'OOS', 'STUDY')",
            name=conv("ck_agent_frozen_contract_role"),
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 131072 AND octet_length(contract_json::text) <= 131072",
            name=conv("ck_agent_frozen_contract_size"),
        ),
        sa.CheckConstraint(
            "contract_hash ~ '^[0-9a-f]{64}$'", name=conv("ck_agent_frozen_contract_hash"),
        ),
    )
    op.create_index(
        "idx_agent_frozen_contract_owner_turn", "agent_frozen_research_contract",
        ["owner_user_id", "turn_id"],
    )
    op.create_index(
        "idx_agent_frozen_contract_subject", "agent_frozen_research_contract",
        ["owner_user_id", "contract_kind", "subject_id"],
    )
    op.create_table(
        "agent_frozen_contract_manifest",
        *_identity_columns(),
        sa.Column("base_manifest_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("base_manifest_hash", sa.String(64), nullable=False),
        sa.Column("contract_ids_hash", sa.String(64), nullable=False),
        sa.Column("contract_count", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("manifest_json", pg.JSONB(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        *_owner_constraints("agent_contract_manifest"),
        sa.UniqueConstraint("turn_id", name=conv("uq_agent_contract_manifest_turn")),
        sa.ForeignKeyConstraint(
            ["base_manifest_id", "owner_user_id", "turn_id"],
            [
                "agent_turn_archive_manifest.id", "agent_turn_archive_manifest.owner_user_id",
                "agent_turn_archive_manifest.turn_id",
            ],
            name="fk_agent_contract_manifest_base_owner", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "contract_count BETWEEN 1 AND 800", name=conv("ck_agent_contract_manifest_count"),
        ),
        sa.CheckConstraint(
            "octet_length(manifest_json::text) <= 65536",
            name=conv("ck_agent_contract_manifest_size"),
        ),
        sa.CheckConstraint(
            "base_manifest_hash ~ '^[0-9a-f]{64}$' AND "
            "contract_ids_hash ~ '^[0-9a-f]{64}$' AND manifest_hash ~ '^[0-9a-f]{64}$'",
            name=conv("ck_agent_contract_manifest_hashes"),
        ),
    )
    op.create_index(
        "idx_agent_contract_manifest_owner_turn", "agent_frozen_contract_manifest",
        ["owner_user_id", "turn_id"],
    )
    for table in ("agent_frozen_research_contract", "agent_frozen_contract_manifest"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_agent_archive_rewrite()"
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("agent_frozen_research_contract", "agent_frozen_contract_manifest"):
        if connection.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("refusing to downgrade M16.6 while frozen contracts exist")
    op.drop_table("agent_frozen_contract_manifest")
    op.drop_table("agent_frozen_research_contract")
    op.drop_constraint(
        "uq_agent_archive_manifest_owner", "agent_turn_archive_manifest", type_="unique"
    )
