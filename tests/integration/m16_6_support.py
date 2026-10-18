import os
import uuid
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@contextmanager
def isolated_contract_database(monkeypatch, *, revision="head"):
    """Create and destroy only a uniquely named synthetic integration-test database."""
    database_name = "m166_test_" + uuid.uuid4().hex
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url and os.environ.get("CI") != "true":
        raise RuntimeError("M16.6 integration requires explicit TEST_DATABASE_URL or isolated CI")
    base_url = make_url(test_url or get_settings().database_url)
    admin = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    engine = None
    try:
        with admin.connect() as connection:
            assert connection.scalar(sa.text("SHOW server_version_num"))[:2] == "17"
            connection.execute(sa.text(f'CREATE DATABASE "{database_name}"'))
        engine = sa.create_engine(base_url.set(database=database_name))
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        monkeypatch.setattr("app.core.agent_db.SessionLocal", factory)
        yield factory, engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin.dispose()
