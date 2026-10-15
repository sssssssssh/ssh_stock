"""Explicit online prebuild, separate from transactional Alembic/FK installation."""

from sqlalchemy import text

from app.services.retention_lineage import INDEX_SPECS, RetentionBlocked

INDEX_STATE = text("""
    SELECT i.indisvalid, i.indisready, i.indisunique,
           i.indrelid = to_regclass(:table_name) AS right_table,
           i.indpred IS NULL AND i.indexprs IS NULL AS plain,
           am.amname, i.indnkeyatts, i.indnatts,
           ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, position)
                 JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                 ORDER BY k.position) AS column_names
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_am am ON am.oid = c.relam WHERE i.indexrelid = to_regclass(:name)
""")


def index_ready(row, columns):
    return (
        row.indisvalid and row.indisready and not row.indisunique and row.right_table
        and row.plain and row.amname == "btree"
        and row.indnkeyatts == row.indnatts == len(columns)
        and tuple(row.column_names) == tuple(columns)
    )


def prepare_retention_indexes(connection, *, apply=False, timeout_ms=600000):
    if not 1 <= timeout_ms <= 1800000:
        raise ValueError("RETENTION_INDEX_INVALID_TIMEOUT")
    if connection.get_isolation_level() != "READ COMMITTED":
        # SQLAlchemy reports the underlying PG isolation level even in AUTOCOMMIT.
        raise RetentionBlocked("RETENTION_INDEX_INVALID_ISOLATION")
    if connection.get_execution_options().get("isolation_level") != "AUTOCOMMIT":
        raise RetentionBlocked("RETENTION_INDEX_REQUIRES_AUTOCOMMIT")
    connection.execute(text("SELECT set_config('lock_timeout', '1000', false)"))
    connection.execute(text("SELECT set_config('statement_timeout', :value, false)"),
                       {"value": str(timeout_ms)})
    results = []
    for name, table, columns in INDEX_SPECS:
        existing = connection.execute(INDEX_STATE, {"name": name, "table_name": table}).first()
        if existing is not None:
            if not index_ready(existing, columns):
                raise RetentionBlocked("RETENTION_INDEX_REQUIRES_OPERATOR_REPAIR")
            results.append({"index": name, "state": "READY"})
            continue
        if apply:
            # Identifiers exclusively originate in the versioned application manifest.
            connection.execute(text(
                f'CREATE INDEX CONCURRENTLY "{name}" ON "{table}" '
                f'({", ".join(columns)})'
            ))
        results.append({"index": name, "state": "CREATED" if apply else "MISSING"})
    return results
