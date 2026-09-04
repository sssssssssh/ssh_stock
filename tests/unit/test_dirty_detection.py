from datetime import date
from types import SimpleNamespace

from app.models.market_data import StockDaily
from app.services.dirty import changed_trade_dates, mark_dirty_ranges_failed


class _FakeResult:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def all(self) -> list[dict]:
        return self._rows


def test_changed_trade_dates_ignores_protected_null_overwrite() -> None:
    db = SimpleNamespace(
        execute=lambda stmt: _FakeResult(
            [{"trade_date": date(2026, 8, 31), "ts_code": "000001.SZ", "close": 10.5}]
        )
    )

    dirty = changed_trade_dates(
        db,
        StockDaily,
        [{"trade_date": date(2026, 8, 31), "ts_code": "000001.SZ", "close": None}],
        conflict_columns=["trade_date", "ts_code"],
        compare_columns=["close"],
        preserve_existing_on_null_columns=["close"],
    )

    assert dirty == set()


def test_changed_trade_dates_tracks_real_value_change() -> None:
    db = SimpleNamespace(
        execute=lambda stmt: _FakeResult(
            [{"trade_date": date(2026, 8, 31), "ts_code": "000001.SZ", "close": 10.5}]
        )
    )

    dirty = changed_trade_dates(
        db,
        StockDaily,
        [{"trade_date": date(2026, 8, 31), "ts_code": "000001.SZ", "close": 10.8}],
        conflict_columns=["trade_date", "ts_code"],
        compare_columns=["close"],
        preserve_existing_on_null_columns=["close"],
    )

    assert dirty == {date(2026, 8, 31)}


def test_mark_dirty_ranges_failed_marks_failed() -> None:
    dirty_range = SimpleNamespace(
        status="PROCESSING",
        retry_count=1,
        last_error=None,
        last_failed_at=None,
    )
    added = []
    db = SimpleNamespace(add=added.append, commit=lambda: None)

    mark_dirty_ranges_failed(db, [dirty_range], "factor failed")

    assert dirty_range.status == "FAILED"
    assert dirty_range.retry_count == 2
    assert dirty_range.last_error == "factor failed"
    assert dirty_range.last_failed_at is not None
    assert added == [dirty_range]
