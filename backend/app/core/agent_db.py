from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal


@contextmanager
def agent_db_session(settings: Settings | None = None) -> Iterator[Session]:
    """Open one isolated READ ONLY transaction for exactly one Agent tool call."""
    db = SessionLocal()
    try:
        if db.get_bind().dialect.name == "postgresql":
            timeout = (settings or get_settings()).agent_config.statement_timeout_ms
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(
                text("SELECT set_config('statement_timeout', :value, true)"),
                {"value": f"{timeout}ms"},
            )
        yield db
    finally:
        db.rollback()
        db.close()


def get_agent_db() -> Generator[Session, None, None]:
    with agent_db_session() as db:
        yield db
