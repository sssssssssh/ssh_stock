from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from app.repositories.upsert import upsert_rows


def replace_slice_rows(
    db: Session,
    model: type,
    rows: Sequence[dict[str, Any]],
    *,
    scope_filters: Sequence[Any],
    key_columns: Sequence[str],
    update_columns: Sequence[str] | None = None,
) -> int:
    """Make one calculated scope authoritative without replacing surviving rows."""
    if not key_columns:
        raise ValueError("key_columns must not be empty")
    columns = [getattr(model, name) for name in key_columns]
    existing_keys = {
        tuple(row)
        for row in db.execute(select(*columns).where(*scope_filters)).all()
    }
    current_keys = {
        tuple(row[column] for column in key_columns)
        for row in rows
    }
    stale_keys = existing_keys - current_keys
    _delete_stale_keys(
        db,
        model,
        columns=columns,
        scope_filters=scope_filters,
        stale_keys=stale_keys,
    )
    return upsert_rows(
        db,
        model,
        rows,
        key_columns,
        update_columns=update_columns,
    )


def replace_slice_rows_with_stats(
    db: Session,
    model: type,
    row_batches: Iterable[Sequence[dict[str, Any]]],
    *,
    scope_filters: Sequence[Any],
    key_columns: Sequence[str],
) -> dict[str, int]:
    """Reconcile one scope while streaming upserts in bounded batches."""
    if not key_columns:
        raise ValueError("key_columns must not be empty")
    columns = [getattr(model, name) for name in key_columns]
    existing_keys = {
        tuple(row) for row in db.execute(select(*columns).where(*scope_filters)).all()
    }
    current_keys: set[tuple[Any, ...]] = set()
    upserted = 0
    for rows in row_batches:
        current_keys.update(tuple(row[column] for column in key_columns) for row in rows)
        upserted += upsert_rows(db, model, rows, key_columns)
    stale_keys = existing_keys - current_keys
    _delete_stale_keys(
        db, model, columns=columns, scope_filters=scope_filters, stale_keys=stale_keys
    )
    return {"upserted": upserted, "deleted": len(stale_keys)}


def _delete_stale_keys(
    db: Session,
    model: type,
    *,
    columns: Sequence[Any],
    scope_filters: Sequence[Any],
    stale_keys: set[tuple[Any, ...]],
) -> None:
    if not stale_keys:
        return
    ordered_keys = sorted(stale_keys, key=lambda key: tuple(str(value) for value in key))
    chunk_size = max(1, 30_000 // len(columns))
    for start in range(0, len(ordered_keys), chunk_size):
        keys = ordered_keys[start : start + chunk_size]
        if len(columns) == 1:
            key_filter = columns[0].in_([key[0] for key in keys])
        else:
            key_filter = tuple_(*columns).in_(keys)
        db.execute(delete(model).where(*scope_filters, key_filter))
