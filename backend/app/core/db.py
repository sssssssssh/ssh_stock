import re
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


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

