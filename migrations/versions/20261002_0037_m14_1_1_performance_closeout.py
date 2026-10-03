"""Close M14.1 performance concurrency and persistence integrity gaps.

Revision ID: 0037_m14_1_1_closeout
Revises: 0036_m14_1_performance
"""

import sqlalchemy as sa
from alembic import op

revision = "0037_m14_1_1_closeout"
down_revision = "0036_m14_1_performance"
branch_labels = None
depends_on = None

_DAILY_REPORT_FK = (
    "fk_portfolio_performance_daily_performance_id_portfolio_performance_report"
)
_DAILY_REPORT_RUN_FK = "fk_portfolio_performance_daily_report_run"
_REPORT_ID_RUN_UNIQUE = "uq_portfolio_performance_report_id_run"


def _count(connection, query: str) -> int:
    return int(connection.scalar(sa.text(query)) or 0)


def upgrade() -> None:
    connection = op.get_bind()
    cross_run_count = _count(
        connection,
        """
        SELECT count(*)
        FROM portfolio_performance_daily daily
        JOIN portfolio_performance_report report
          ON report.id = daily.performance_id
        WHERE daily.run_id <> report.run_id
        """,
    )
    if cross_run_count:
        raise RuntimeError(
            "cannot enforce performance report/daily same-run ownership: "
            f"found {cross_run_count} cross-run daily row(s)"
        )

    op.alter_column(
        "portfolio_performance_report",
        "annualized_return",
        existing_type=sa.Numeric(precision=20, scale=10),
        type_=sa.Numeric(precision=60, scale=18),
        existing_nullable=False,
        postgresql_using="annualized_return::numeric(60,18)",
    )
    op.create_unique_constraint(
        op.f(_REPORT_ID_RUN_UNIQUE),
        "portfolio_performance_report",
        ["id", "run_id"],
    )
    op.drop_constraint(
        op.f(_DAILY_REPORT_FK),
        "portfolio_performance_daily",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f(_DAILY_REPORT_RUN_FK),
        "portfolio_performance_daily",
        "portfolio_performance_report",
        ["performance_id", "run_id"],
        ["id", "run_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    connection = op.get_bind()
    unsafe_count = _count(
        connection,
        """
        SELECT count(*)
        FROM portfolio_performance_report
        WHERE annualized_return >= 10000000000
           OR annualized_return <= -10000000000
           OR annualized_return <> round(annualized_return, 10)
        """,
    )
    if unsafe_count:
        raise RuntimeError(
            "cannot safely narrow performance annualized_return to NUMERIC(20,10): "
            f"found {unsafe_count} out-of-range or over-scale row(s)"
        )

    op.drop_constraint(
        op.f(_DAILY_REPORT_RUN_FK),
        "portfolio_performance_daily",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f(_DAILY_REPORT_FK),
        "portfolio_performance_daily",
        "portfolio_performance_report",
        ["performance_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        op.f(_REPORT_ID_RUN_UNIQUE),
        "portfolio_performance_report",
        type_="unique",
    )
    op.alter_column(
        "portfolio_performance_report",
        "annualized_return",
        existing_type=sa.Numeric(precision=60, scale=18),
        type_=sa.Numeric(precision=20, scale=10),
        existing_nullable=False,
        postgresql_using="annualized_return::numeric(20,10)",
    )
