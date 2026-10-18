import re
from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _data_task_transaction_timeouts(session, transaction, connection):
    if session.info.get("data_task_timeouts") and connection.dialect.name == "postgresql":
        config = get_settings().app_config.get("app", {}).get("scheduler", {})
        connection.execute(text("SELECT set_config('statement_timeout', :statement, true), "
                                "set_config('lock_timeout', :lock, true)"), {
            "statement": str(int(config.get("data_statement_timeout_ms", 300000))),
            "lock": str(int(config.get("data_lock_timeout_ms", 5000))),
        })
        identity = session.info.get("data_execution_job_id")
        if identity:
            connection.execute(text("SELECT set_config('application_name', :name, true)"),
                               {"name": f"space-data/{identity}"})


def database_error_summary(error: SQLAlchemyError) -> str:
    """Keep diagnostic classes/SQLSTATE without connection strings, SQL or parameters."""
    kind = type(error).__name__
    original = getattr(error, "orig", None)
    if original is not None:
        kind += f"/{type(original).__name__}"
    code = getattr(original, "sqlstate", None)
    suffix = (
        f" (SQLSTATE {code})"
        if isinstance(code, str) and re.fullmatch(r"[0-9A-Z]{5}", code) else ""
    )
    return f"database operation failed: {kind}{suffix}"


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

