from collections.abc import Generator

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal


def get_agent_db() -> Generator[Session, None, None]:
    """Use an isolated transaction so tool execution can never commit application writes."""
    db = SessionLocal()
    try:
        if db.get_bind().dialect.name == "postgresql":
            timeout = get_settings().agent_config.statement_timeout_ms
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(
                text("SELECT set_config('statement_timeout', :value, true)"),
                {"value": f"{timeout}ms"},
            )
        yield db
    finally:
        db.rollback()
        db.close()
