import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.core.config import get_settings


@pytest.fixture
def agent_chat_migration(monkeypatch):
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261011_0046_m16_2_agent_chat.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0046", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(sa.text("SET LOCAL search_path TO pg_temp"))
        connection.execute(
            sa.text("CREATE TEMPORARY TABLE app_user (id uuid PRIMARY KEY)")
        )
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        try:
            yield connection, migration
        finally:
            transaction.rollback()
    engine.dispose()


def test_0046_postgresql_upgrade_downgrade_upgrade_when_empty(
    agent_chat_migration,
) -> None:
    connection, migration = agent_chat_migration
    migration.upgrade()
    assert connection.scalar(sa.text("SELECT to_regclass('agent_chat_session')"))
    assert connection.scalar(
        sa.text(
            "SELECT count(*) FROM pg_indexes "
            "WHERE schemaname LIKE 'pg_temp_%' "
            "AND indexname='uq_agent_chat_turn_running_session'"
        )
    ) == 1
    assert connection.scalar(
        sa.text(
            "SELECT count(*) FROM pg_constraint "
            "WHERE connamespace=pg_my_temp_schema() "
            "AND conname='ck_agent_chat_message_content_length'"
        )
    ) == 1
    assert connection.scalar(
        sa.text(
            "SELECT count(*) FROM pg_constraint "
            "WHERE connamespace=pg_my_temp_schema() "
            "AND conname LIKE 'ck_agent_chat_%_ck_agent_chat_%'"
        )
    ) == 0

    migration.downgrade()
    assert connection.scalar(sa.text("SELECT to_regclass('agent_chat_session')")) is None

    migration.upgrade()
    assert connection.scalar(sa.text("SELECT to_regclass('agent_chat_session')"))


def test_0046_refuses_destructive_downgrade_when_chat_history_exists(
    agent_chat_migration,
) -> None:
    connection, migration = agent_chat_migration
    migration.upgrade()
    owner_id = uuid.uuid4()
    connection.execute(
        sa.text("INSERT INTO app_user (id) VALUES (:id)"), {"id": owner_id}
    )
    connection.execute(
        sa.text(
            "INSERT INTO agent_chat_session "
            "(id, owner_user_id, title) VALUES (:id, :owner_id, 'history')"
        ),
        {"id": uuid.uuid4(), "owner_id": owner_id},
    )
    with pytest.raises(RuntimeError, match="cannot downgrade M16.2"):
        migration.downgrade()
    assert connection.scalar(sa.text("SELECT count(*) FROM agent_chat_session")) == 1


def test_0047_normalizes_pre_release_constraint_names(agent_chat_migration) -> None:
    connection, migration = agent_chat_migration
    migration.upgrade()
    closeout_path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261011_0047_m16_2_constraint_name_closeout.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0047", closeout_path)
    assert spec is not None and spec.loader is not None
    closeout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(closeout)
    closeout.op = Operations(MigrationContext.configure(connection))

    for table, legacy_name, canonical_name in closeout._RENAMES:
        connection.execute(
            sa.text(
                f'ALTER TABLE "{table}" RENAME CONSTRAINT '
                f'"{canonical_name}" TO "{legacy_name}"'
            )
        )
    closeout.upgrade()
    closeout.downgrade()

    canonical_names = {item[2] for item in closeout._RENAMES}
    actual_names = set(
        connection.scalars(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace=pg_my_temp_schema() AND contype='c'"
            )
        )
    )
    assert canonical_names <= actual_names
    assert not ({item[1] for item in closeout._RENAMES} & actual_names)
