"""Verify that a fresh temporary PostgreSQL database upgrades to Alembic head."""

import os
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

EXPECTED_M13_TABLES = {
    "portfolio_backtest_run",
    "portfolio_order",
    "portfolio_fill",
    "portfolio_position_daily",
    "portfolio_nav_daily",
}


def main() -> None:
    source_url = make_url(os.environ["DATABASE_URL"])
    admin_url = source_url.set(database="postgres")
    database_name = f"ssh_stock_migration_check_{uuid.uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    temporary_engine = None
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        temporary_url = source_url.set(database=database_name)
        os.environ["DATABASE_URL"] = temporary_url.render_as_string(hide_password=False)
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        temporary_engine = create_engine(temporary_url)
        with temporary_engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            tables = set(inspect(connection).get_table_names())
        if revision != "0029_m13_1_portfolio_foundation":
            raise RuntimeError(f"unexpected migration head: {revision}")
        missing = EXPECTED_M13_TABLES - tables
        if missing:
            raise RuntimeError(f"fresh migration is missing tables: {sorted(missing)}")
        print(f"fresh migration verified: {revision}; M13 tables={len(EXPECTED_M13_TABLES)}")
    finally:
        if temporary_engine is not None:
            temporary_engine.dispose()
        os.environ["DATABASE_URL"] = source_url.render_as_string(hide_password=False)
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
        admin_engine.dispose()


if __name__ == "__main__":
    main()
