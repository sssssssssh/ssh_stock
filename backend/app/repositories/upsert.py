from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def upsert_rows(
    db: Session,
    model: type,
    rows: Iterable[dict[str, Any]],
    conflict_columns: Sequence[str],
    update_columns: Sequence[str] | None = None,
    preserve_existing_on_null_columns: Sequence[str] | None = None,
    merge_json_columns: Sequence[str] | None = None,
    max_parameters: int = 60000,
    _published_raw_quality: bool = False,
) -> int:
    payload = list(rows)
    if not payload:
        return 0

    from app.services.data_publication import published_table, route_upsert, workspace

    if not _published_raw_quality:
        routed = route_upsert(db, model, payload, conflict_columns,
            update_columns=update_columns,
            preserve_existing_on_null_columns=preserve_existing_on_null_columns,
            merge_json_columns=merge_json_columns)
        if routed is not None:
            return routed

    table = (published_table(model) if _published_raw_quality and workspace(db)
             else model.__table__)
    if update_columns is None:
        primary_keys = {col.name for col in table.primary_key.columns}
        excluded = set(conflict_columns) | primary_keys
        update_columns = [col.name for col in table.columns if col.name not in excluded]

    chunk_size = _chunk_size(payload, max_parameters)
    preserve_columns = set(preserve_existing_on_null_columns or [])
    json_merge_columns = set(merge_json_columns or [])
    for start in range(0, len(payload), chunk_size):
        batch = payload[start : start + chunk_size]
        stmt = insert(table).values(batch)
        if update_columns:
            update_map = {}
            for col in update_columns:
                excluded_value = getattr(stmt.excluded, col)
                if col in preserve_columns:
                    update_map[col] = case(
                        (excluded_value.is_(None), table.c[col]),
                        else_=excluded_value,
                    )
                elif col in json_merge_columns:
                    update_map[col] = case(
                        (table.c[col].is_(None), excluded_value),
                        else_=table.c[col].op("||")(excluded_value),
                    )
                else:
                    update_map[col] = excluded_value
            stmt = stmt.on_conflict_do_update(
                index_elements=list(conflict_columns), set_=update_map
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(conflict_columns))
        db.execute(stmt)
    return len(payload)


def _chunk_size(payload: Sequence[dict[str, Any]], max_parameters: int) -> int:
    column_count = len(set().union(*(row.keys() for row in payload)))
    if column_count <= 0:
        return len(payload)
    return max(1, max_parameters // column_count)
