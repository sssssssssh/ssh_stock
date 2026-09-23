from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from app.core.config import get_settings


@pytest.fixture
def transition_migration(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("path_separator", "os")
    script = ScriptDirectory.from_config(config)
    migration = script.get_revision("0020_transition_calc_lineage").module
    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as conn:
        transaction = conn.begin()
        columns = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_trade_date", sa.Date(), nullable=False),
            sa.Column("ts_code", sa.String(16), nullable=False),
            sa.Column("event_key", sa.String(32), nullable=False),
            sa.Column("algo_version", sa.String(32), nullable=False),
            sa.Column("trend_calc_version", sa.String(32), nullable=False),
            sa.Column("strategy_config_hash", sa.String(64), nullable=False),
            sa.Column("opportunity_config_hash", sa.String(64), nullable=False),
            sa.Column("research_version", sa.String(32), nullable=False),
            sa.Column("research_config_hash", sa.String(64), nullable=False),
            sa.UniqueConstraint(*migration.OLD_KEY, name=migration.CONSTRAINT),
        ]
        table = sa.Table(migration.TABLE, sa.MetaData(), *columns, prefixes=["TEMPORARY"])
        try:
            table.create(conn)
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(conn))
            )
            yield conn, migration, table
        finally:
            transaction.rollback()
    engine.dispose()


def _row(row_id: int, *, calc_version: str | None = None) -> dict:
    row = {
        "id": row_id,
        "event_trade_date": date(2026, 1, 5),
        "ts_code": "A.SZ",
        "event_key": "LEFT_75",
        "algo_version": "v1.1",
        "trend_calc_version": "trend_v1",
        "strategy_config_hash": "strategy",
        "opportunity_config_hash": "opportunity",
        "research_version": "research_v1",
        "research_config_hash": "research",
    }
    if calc_version is not None:
        row["opportunity_calc_version"] = calc_version
    return row


def test_0020_upgrade_and_downgrade_without_collision(transition_migration) -> None:
    conn, migration, table = transition_migration
    conn.execute(table.insert().values(_row(1)))
    migration.upgrade()
    assert conn.scalar(sa.text(
        "SELECT opportunity_calc_version FROM research_transition_eval WHERE id = 1"
    )) == "legacy-unverified"
    migration.downgrade()
    assert conn.scalar(sa.text("SELECT count(*) FROM research_transition_eval")) == 1


def test_0020_downgrade_rejects_collision_then_succeeds_after_cleanup(
    transition_migration,
) -> None:
    conn, migration, table = transition_migration
    conn.execute(table.insert().values(_row(1)))
    migration.upgrade()
    table.append_column(sa.Column("opportunity_calc_version", sa.String(32)))
    conn.execute(table.insert().values(_row(2, calc_version="opportunity_v1")))
    conn.execute(table.insert().values(_row(3, calc_version="opportunity_v2")))

    with pytest.raises(RuntimeError, match="Cannot downgrade 0020"):
        migration.downgrade()
    assert conn.scalar(sa.text("SELECT count(*) FROM research_transition_eval")) == 3

    conn.execute(table.delete().where(table.c.id.in_((2, 3))))
    migration.downgrade()
    assert conn.scalar(sa.text("SELECT count(*) FROM research_transition_eval")) == 1
