"""V1.4 tests require a separately provisioned, marked physical PG17 instance.

No business settings are imported until the explicit target and server marker
have been verified. A loopback address alone is NOT proof of isolation.
"""

import os
import uuid
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def verified_test_url():
    raw = os.environ.get("TEST_DATABASE_URL", "")
    marker = os.environ.get("V14_TEST_INSTANCE", "")
    try:
        url = make_url(raw)
        uuid.UUID(marker)
    except Exception:
        raise RuntimeError("V14_EXPLICIT_MARKED_PG17_REQUIRED") from None
    if (url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost"}
            or not (url.database or "").endswith("_test")):
        raise RuntimeError("V14_EXPLICIT_MARKED_PG17_REQUIRED")
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as db:
            if (int(db.scalar(text("SHOW server_version_num"))) // 10000 != 17
                    or db.scalar(text(
                        "SELECT current_setting('v14.test_instance',true)")) != marker):
                raise RuntimeError("V14_PHYSICAL_INSTANCE_MARKER_MISMATCH")
            # Require the operator's separately recorded system identifier too:
            # a copied marker or an SSH tunnel must not silently select a server.
            actual = str(db.scalar(text("SELECT system_identifier FROM pg_control_system()")))
            if actual != os.environ.get("V14_TEST_SYSTEM_IDENTIFIER"):
                raise RuntimeError("V14_PHYSICAL_INSTANCE_ID_MISMATCH")
    finally:
        engine.dispose()
    return url


@contextmanager
def isolated_v14_database(monkeypatch):
    # Verify *before* CREATE, migration, settings imports, and again before DROP.
    url = verified_test_url()
    # pytest owns restoration: no process-wide environment leak into unrelated
    # configuration tests later in a full-suite run.
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("TUSHARE_TOKEN", "synthetic-v14")
    monkeypatch.setenv("LLM_ENABLED", "false")
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import sessionmaker

    name = "v14_" + uuid.uuid4().hex + "_test"
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    engine = None
    created = False
    try:
        with admin.connect() as db:
            db.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        engine = create_engine(url.set(database=name), hide_parameters=True)
        with engine.begin() as db:
            config = Config("alembic.ini")
            config.attributes["connection"] = db
            command.upgrade(config, "head")
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        monkeypatch.setattr("app.core.agent_db.SessionLocal", factory)
        yield factory, engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            verified_test_url()
            with admin.connect() as db:
                db.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
