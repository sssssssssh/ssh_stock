from datetime import date
from unittest.mock import Mock

from app.models.market_data import StockDaily
from app.repositories.upsert import _chunk_size, upsert_rows
from sqlalchemy.dialects import postgresql


def test_chunk_size_respects_parameter_limit() -> None:
    payload = [{"a": idx, "b": idx, "c": idx} for idx in range(10)]

    assert _chunk_size(payload, max_parameters=7) == 2


def test_chunk_size_is_at_least_one_row() -> None:
    payload = [{"a": 1, "b": 2, "c": 3}]

    assert _chunk_size(payload, max_parameters=1) == 1


def test_upsert_can_preserve_existing_value_on_null() -> None:
    db = Mock()

    upsert_rows(
        db,
        StockDaily,
        [
            {
                "trade_date": date(2026, 8, 31),
                "ts_code": "000001.SZ",
                "close": None,
            }
        ],
        ["trade_date", "ts_code"],
        update_columns=["close"],
        preserve_existing_on_null_columns=["close"],
    )

    stmt = db.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "CASE WHEN (excluded.close IS NULL)" in sql
    assert "THEN stock_daily.close" in sql
