import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import DataDirtyRange, StockDaily


def changed_trade_dates(
    db: Session,
    model: type,
    rows: list[dict[str, Any]],
    *,
    conflict_columns: list[str],
    compare_columns: list[str],
    trade_date_column: str = "trade_date",
    preserve_existing_on_null_columns: list[str] | None = None,
) -> set[date]:
    if not rows:
        return set()

    preserve_columns = set(preserve_existing_on_null_columns or [])
    pk_to_row = {tuple(row.get(col) for col in conflict_columns): row for row in rows}
    if not pk_to_row:
        return set()

    table = model.__table__
    selected = [table.c[col] for col in conflict_columns + compare_columns]
    stmt = select(*selected)
    for column in conflict_columns:
        values = {row.get(column) for row in rows if row.get(column) is not None}
        stmt = stmt.where(table.c[column].in_(values))

    dirty_dates: set[date] = set()
    for existing in db.execute(stmt).mappings().all():
        key = tuple(existing[col] for col in conflict_columns)
        incoming = pk_to_row.get(key)
        if incoming is None:
            continue
        for column in compare_columns:
            new_value = incoming.get(column)
            old_value = existing[column]
            if new_value is None and old_value is not None and column in preserve_columns:
                continue
            if _changed(old_value, new_value):
                value = incoming.get(trade_date_column) or existing.get(trade_date_column)
                if value is not None:
                    dirty_dates.add(value)
                break
    return dirty_dates


def record_dirty_range(
    db: Session,
    *,
    dataset: str,
    dirty_dates: set[date],
    reason: str,
    source_job_id: uuid.UUID | None = None,
) -> DataDirtyRange | None:
    if not dirty_dates:
        return None
    row = DataDirtyRange(
        dataset=dataset,
        dirty_start_date=min(dirty_dates),
        dirty_end_date=max(dirty_dates),
        reason=reason,
        source_job_id=source_job_id,
        status="OPEN",
    )
    db.add(row)
    return row


def open_dirty_ranges(db: Session) -> list[DataDirtyRange]:
    return list(
        db.execute(
            select(DataDirtyRange)
            .where(DataDirtyRange.status == "OPEN")
            .order_by(DataDirtyRange.dirty_start_date)
        )
        .scalars()
        .all()
    )


def repairable_dirty_ranges(
    db: Session,
    *,
    max_retry_count: int = 3,
) -> list[DataDirtyRange]:
    return list(
        db.execute(
            select(DataDirtyRange)
            .where(
                DataDirtyRange.status.in_(("OPEN", "FAILED")),
                DataDirtyRange.retry_count < max_retry_count,
            )
            .order_by(DataDirtyRange.dirty_start_date)
        )
        .scalars()
        .all()
    )


def unresolved_dirty_ranges(db: Session) -> list[DataDirtyRange]:
    return list(
        db.execute(
            select(DataDirtyRange)
            .where(DataDirtyRange.status.in_(("OPEN", "FAILED")))
            .order_by(DataDirtyRange.dirty_start_date)
        )
        .scalars()
        .all()
    )


def latest_raw_trade_date(db: Session) -> date | None:
    return db.execute(select(func.max(StockDaily.trade_date))).scalar_one_or_none()


def mark_dirty_ranges_processing(db: Session, ranges: list[DataDirtyRange]) -> None:
    for row in ranges:
        row.status = "PROCESSING"
        db.add(row)
    db.commit()


def mark_dirty_ranges_resolved(db: Session, ranges: list[DataDirtyRange]) -> None:
    resolved_at = datetime.now(UTC)
    for row in ranges:
        row.status = "RESOLVED"
        row.resolved_at = resolved_at
        row.last_error = None
        db.add(row)
    db.commit()


def mark_dirty_ranges_failed(
    db: Session,
    ranges: list[DataDirtyRange],
    error_message: str | None = None,
) -> None:
    failed_at = datetime.now(UTC)
    for row in ranges:
        row.status = "FAILED"
        row.retry_count = int(row.retry_count or 0) + 1
        row.last_error = error_message[:4096] if error_message else None
        row.last_failed_at = failed_at
        db.add(row)
    db.commit()


def _changed(old_value: Any, new_value: Any) -> bool:
    if old_value is None and new_value is None:
        return False
    if old_value is None or new_value is None:
        return True
    try:
        return abs(float(old_value) - float(new_value)) > 1e-12
    except (TypeError, ValueError):
        return old_value != new_value
