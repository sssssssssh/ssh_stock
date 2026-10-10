import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.core.config import get_settings


@pytest.fixture
def validation_identity_migration(monkeypatch):
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261010_0045_m15_3_2_validation_identity.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0045", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine(get_settings().database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(
            sa.text(
                """
                CREATE TEMPORARY TABLE portfolio_walk_forward_validation_report (
                    id uuid PRIMARY KEY,
                    study_id uuid NOT NULL,
                    walk_forward_version varchar(32) NOT NULL,
                    walk_forward_config_hash varchar(64) NOT NULL,
                    validation_policy_snapshot jsonb NOT NULL,
                    validation_policy_hash varchar(64) NOT NULL,
                    source_hash varchar(64) NOT NULL,
                    CONSTRAINT uq_walk_forward_validation_identity UNIQUE
                        (study_id, walk_forward_version,
                         walk_forward_config_hash, source_hash),
                    CONSTRAINT ck_walk_forward_validation_policy_identity CHECK
                        (validation_policy_hash = walk_forward_config_hash)
                )
                """
            )
        )
        monkeypatch.setattr(
            migration, "op", Operations(MigrationContext.configure(connection))
        )
        try:
            yield connection, migration
        finally:
            transaction.rollback()
    engine.dispose()


def _insert_legacy(connection, *, config_hash: str = "a" * 64) -> uuid.UUID:
    report_id = uuid.uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO portfolio_walk_forward_validation_report
                (id, study_id, walk_forward_version, walk_forward_config_hash,
                 validation_policy_snapshot, validation_policy_hash, source_hash)
            VALUES
                (:id, :study_id, 'walk_forward_v1', :config_hash,
                 '{"version":"walk_forward_validation_policy_v0"}'::jsonb,
                 :config_hash, :source_hash)
            """
        ),
        {
            "id": report_id,
            "study_id": uuid.UUID("10000000-0000-0000-0000-000000000001"),
            "config_hash": config_hash,
            "source_hash": "s" * 64,
        },
    )
    return report_id


def test_0045_preserves_legacy_identity_and_allows_current_policy_identity(
    validation_identity_migration,
) -> None:
    connection, migration = validation_identity_migration
    legacy_id = _insert_legacy(connection)

    migration.upgrade()

    assert connection.scalar(
        sa.text(
            "SELECT policy_identity_version "
            "FROM portfolio_walk_forward_validation_report WHERE id=:id"
        ),
        {"id": legacy_id},
    ) == "legacy_v0"
    connection.execute(
        sa.text(
            """
            INSERT INTO portfolio_walk_forward_validation_report
                (id, study_id, walk_forward_version, walk_forward_config_hash,
                 policy_identity_version, validation_policy_snapshot,
                 validation_policy_hash, source_hash)
            VALUES
                (:id, :study_id, 'walk_forward_v1', :config_hash, 'policy_v1',
                 '{"version":"walk_forward_validation_policy_v1"}'::jsonb,
                 :policy_hash, :source_hash)
            """
        ),
        {
            "id": uuid.uuid4(),
            "study_id": uuid.UUID("10000000-0000-0000-0000-000000000001"),
            "config_hash": "c" * 64,
            "policy_hash": "p" * 64,
            "source_hash": "s" * 64,
        },
    )
    assert connection.scalar(
        sa.text("SELECT count(*) FROM portfolio_walk_forward_validation_report")
    ) == 2


def test_0045_dirty_identity_upgrade_fails_and_savepoint_rolls_back(
    validation_identity_migration,
) -> None:
    connection, migration = validation_identity_migration
    _insert_legacy(connection)
    connection.execute(
        sa.text(
            "ALTER TABLE portfolio_walk_forward_validation_report "
            "DROP CONSTRAINT ck_walk_forward_validation_policy_identity"
        )
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO portfolio_walk_forward_validation_report
                (id, study_id, walk_forward_version, walk_forward_config_hash,
                 validation_policy_snapshot, validation_policy_hash, source_hash)
            VALUES
                (:id, :study_id, 'walk_forward_v1', :config_hash,
                 '{}'::jsonb, :policy_hash, :source_hash)
            """
        ),
        {
            "id": uuid.uuid4(),
            "study_id": uuid.UUID("10000000-0000-0000-0000-000000000001"),
            "config_hash": "b" * 64,
            "policy_hash": "a" * 64,
            "source_hash": "s" * 64,
        },
    )
    savepoint = connection.begin_nested()
    with pytest.raises(RuntimeError, match="validation identity conflict"):
        migration.upgrade()
    savepoint.rollback()

    assert connection.scalar(
        sa.text(
            """
            SELECT count(*)
              FROM information_schema.columns
             WHERE table_schema LIKE 'pg_temp_%'
               AND table_name = 'portfolio_walk_forward_validation_report'
               AND column_name = 'policy_identity_version'
            """
        )
    ) == 0


def test_0045_downgrade_allows_legacy_and_rejects_current_artifacts(
    validation_identity_migration,
) -> None:
    connection, migration = validation_identity_migration
    _insert_legacy(connection)
    migration.upgrade()
    migration.downgrade()
    assert connection.scalar(
        sa.text(
            """
            SELECT count(*)
              FROM information_schema.columns
             WHERE table_schema LIKE 'pg_temp_%'
               AND table_name = 'portfolio_walk_forward_validation_report'
               AND column_name = 'policy_identity_version'
            """
        )
    ) == 0

    migration.upgrade()
    connection.execute(
        sa.text(
            """
            INSERT INTO portfolio_walk_forward_validation_report
                (id, study_id, walk_forward_version, walk_forward_config_hash,
                 validation_policy_snapshot, validation_policy_hash, source_hash)
            VALUES
                (:id, :study_id, 'walk_forward_v1', :config_hash,
                 '{"version":"walk_forward_validation_policy_v1"}'::jsonb,
                 :policy_hash, :source_hash)
            """
        ),
        {
            "id": uuid.uuid4(),
            "study_id": uuid.uuid4(),
            "config_hash": "c" * 64,
            "policy_hash": "p" * 64,
            "source_hash": "t" * 64,
        },
    )
    with pytest.raises(RuntimeError, match="cannot downgrade M15.3.2"):
        migration.downgrade()
