from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal


@contextmanager
def agent_db_session(
    settings: Settings | None = None,
    *,
    remaining_seconds: float | None = None,
) -> Iterator[Session]:
    """Open one isolated READ ONLY transaction for exactly one Agent tool call."""
    db = SessionLocal()
    try:
        if db.get_bind().dialect.name == "postgresql":
            db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            timeout = _effective_statement_timeout_ms(
                (settings or get_settings()).agent_config.statement_timeout_ms,
                remaining_seconds,
            )
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.info["published_snapshot"] = True
            db.execute(
                text("SELECT set_config('statement_timeout', :value, true)"),
                {"value": f"{timeout}ms"},
            )
        yield db
    finally:
        db.rollback()
        db.close()


def _effective_statement_timeout_ms(
    configured_ms: int,
    remaining_seconds: float | None,
) -> int:
    if remaining_seconds is None:
        return configured_ms
    remaining_ms = int(remaining_seconds * 1000)
    if remaining_ms <= 0:
        raise ValueError("remaining tool budget is below one millisecond")
    return min(configured_ms, remaining_ms)


def get_agent_db() -> Generator[Session, None, None]:
    with agent_db_session() as db:
        yield db
