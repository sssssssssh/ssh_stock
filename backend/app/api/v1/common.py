from datetime import date
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def envelope(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": 0, "message": "ok", "data": data, "meta": meta or {}}


def clamp_limit(limit: int, default: int = 50, maximum: int = 200) -> int:
    return max(1, min(limit or default, maximum))


def clamp_offset(offset: int) -> int:
    return max(0, offset or 0)


def iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def latest_date(db: Session, column: Any, *criteria: Any) -> date | None:
    stmt = select(func.max(column))
    if criteria:
        stmt = stmt.where(*criteria)
    return db.execute(stmt).scalar_one_or_none()


def scalar_count(db: Session, stmt: Select[tuple[Any]]) -> int:
    return int(db.execute(stmt).scalar_one() or 0)
