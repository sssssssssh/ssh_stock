"""Separate walk-forward validation policy identity from runtime config.

Revision ID: 0045_m15_3_2_validation_identity
Revises: 0044_m15_3_1_walk_forward_integrity
"""

import sqlalchemy as sa
from alembic import op

revision = "0045_m15_3_2_validation_identity"
down_revision = "0044_m15_3_1_walk_forward_integrity"
branch_labels = None
depends_on = None


REPORT = "portfolio_walk_forward_validation_report"
IDENTITY_UNIQUE = "uq_walk_forward_validation_identity"
IDENTITY_CHECK = "ck_walk_forward_validation_policy_identity"
LEGACY_IDENTITY = "legacy_v0"
CURRENT_IDENTITY = "policy_v1"


def upgrade() -> None:
    # A constant add-column default preserves every 0044 artifact without firing
    # its append-only UPDATE trigger. Only rows inserted after this migration use v1.
    op.add_column(
        REPORT,
        sa.Column(
            "policy_identity_version",
            sa.String(16),
            nullable=False,
            server_default=sa.text(f"'{LEGACY_IDENTITY}'"),
        ),
    )
    connection = op.get_bind()
    conflict = connection.execute(
        sa.text(
            f"""
            SELECT study_id, walk_forward_version, policy_identity_version,
                   validation_policy_hash, source_hash, count(*) AS row_count
              FROM {REPORT}
             GROUP BY study_id, walk_forward_version, policy_identity_version,
                      validation_policy_hash, source_hash
            HAVING count(*) > 1
             ORDER BY study_id, walk_forward_version, validation_policy_hash,
                      source_hash
             LIMIT 1
            """
        )
    ).mappings().first()
    if conflict is not None:
        raise RuntimeError(
            "cannot upgrade M15.3.2: validation identity conflict for "
            f"study_id={conflict['study_id']} source_hash={conflict['source_hash']}"
        )

    _drop_policy_identity_check(connection)
    op.drop_constraint(op.f(IDENTITY_UNIQUE), REPORT, type_="unique")
    op.alter_column(
        REPORT,
        "policy_identity_version",
        server_default=sa.text(f"'{CURRENT_IDENTITY}'"),
    )
    op.create_unique_constraint(
        op.f(IDENTITY_UNIQUE),
        REPORT,
        [
            "study_id",
            "walk_forward_version",
            "policy_identity_version",
            "validation_policy_hash",
            "source_hash",
        ],
    )
    op.create_check_constraint(
        op.f(IDENTITY_CHECK),
        REPORT,
        "(policy_identity_version = 'legacy_v0' AND "
        "validation_policy_hash = walk_forward_config_hash) OR "
        "(policy_identity_version = 'policy_v1' AND "
        "validation_policy_snapshot->>'version' = "
        "'walk_forward_validation_policy_v1')",
    )


def downgrade() -> None:
    connection = op.get_bind()
    incompatible = connection.execute(
        sa.text(
            f"""
            SELECT id
              FROM {REPORT}
             WHERE validation_policy_hash <> walk_forward_config_hash
             ORDER BY id
             LIMIT 1
            """
        )
    ).first()
    if incompatible is not None:
        raise RuntimeError(
            "cannot downgrade M15.3.2 while policy-v1 artifacts depend on "
            "separate validation and runtime configuration identities"
        )
    conflict = connection.execute(
        sa.text(
            f"""
            SELECT study_id, walk_forward_version, walk_forward_config_hash,
                   source_hash, count(*) AS row_count
              FROM {REPORT}
             GROUP BY study_id, walk_forward_version, walk_forward_config_hash,
                      source_hash
            HAVING count(*) > 1
             LIMIT 1
            """
        )
    ).first()
    if conflict is not None:
        raise RuntimeError(
            "cannot downgrade M15.3.2 because the 0044 validation identity "
            "would collide"
        )

    _drop_policy_identity_check(connection)
    op.drop_constraint(op.f(IDENTITY_UNIQUE), REPORT, type_="unique")
    op.create_unique_constraint(
        op.f(IDENTITY_UNIQUE),
        REPORT,
        [
            "study_id",
            "walk_forward_version",
            "walk_forward_config_hash",
            "source_hash",
        ],
    )
    op.create_check_constraint(
        op.f(IDENTITY_CHECK),
        REPORT,
        "validation_policy_hash = walk_forward_config_hash",
    )
    op.drop_column(REPORT, "policy_identity_version")


def _drop_policy_identity_check(connection: sa.Connection) -> None:
    constraint_name = connection.scalar(
        sa.text(
            f"""
            SELECT conname
              FROM pg_constraint
             WHERE conrelid = to_regclass('{REPORT}')
               AND contype = 'c'
               AND pg_get_constraintdef(oid) LIKE '%validation_policy_hash%'
               AND pg_get_constraintdef(oid) LIKE '%walk_forward_config_hash%'
             ORDER BY conname
             LIMIT 1
            """
        )
    )
    if not constraint_name:
        raise RuntimeError(
            "cannot migrate M15.3.2: validation policy identity check is missing"
        )
    quoted_name = str(constraint_name).replace('"', '""')
    connection.execute(
        sa.text(f'ALTER TABLE {REPORT} DROP CONSTRAINT "{quoted_name}"')
    )
