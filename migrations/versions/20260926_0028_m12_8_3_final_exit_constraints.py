"""Constrain persisted final-exit statuses to the v7 state space.

Revision ID: 0028_m12_8_3_exit_checks
Revises: 0027_m12_8_2_final_exit
"""

from alembic import op

revision = "0028_m12_8_3_exit_checks"
down_revision = "0027_m12_8_2_final_exit"
branch_labels = None
depends_on = None

HORIZONS = (5, 10, 20, 60)
TABLES = (
    ("opportunity_forward_eval", "ck_opp_eval_exit_status"),
    ("theme_forward_eval", "ck_theme_eval_exit_status"),
)
VALID_STATUSES = "'SUCCESS', 'PENDING', 'UNRESOLVED', 'DATA_INCOMPLETE'"


def upgrade() -> None:
    for table, constraint_prefix in TABLES:
        for horizon in HORIZONS:
            column = f"final_exit_status{horizon}"
            op.create_check_constraint(
                op.f(f"{constraint_prefix}{horizon}"),
                table,
                f"{column} IS NULL OR {column} IN ({VALID_STATUSES})",
            )


def downgrade() -> None:
    for table, constraint_prefix in reversed(TABLES):
        for horizon in reversed(HORIZONS):
            op.drop_constraint(
                op.f(f"{constraint_prefix}{horizon}"), table, type_="check"
            )
