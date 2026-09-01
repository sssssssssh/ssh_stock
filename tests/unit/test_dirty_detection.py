from datetime import date
from types import SimpleNamespace

from app.models.market_data import StockDaily
from app.services.dirty import changed_trade_dates


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
