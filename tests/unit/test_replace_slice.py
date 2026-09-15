from datetime import date

import pytest
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    SignalForwardEval,
    StockFactorDaily,
    StockStateDaily,
    StrategySignal,
)
from app.repositories.replace_slice import replace_slice_rows
from sqlalchemy.dialects import postgresql


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Db:
    def __init__(self, existing):
        self.existing = existing
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if statement.is_select:
            return _Result(self.existing)
        return _Result([])


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_signal_replace_slice_removes_stale_and_preserves_surviving_id() -> None:
    target = date(2026, 9, 15)
    db = _Db(
        [
            (target, "000001.SZ", "RIGHT_SIDE_NEW", "v1"),
            (target, "000002.SZ", "RIGHT_SIDE_NEW", "v1"),
        ]
    )

    count = replace_slice_rows(
        db,
        StrategySignal,
        [
            {
                "trade_date": target,
                "ts_code": "000001.SZ",
                "signal_type": "RIGHT_SIDE_NEW",
                "algo_version": "v1",
                "score": 88.0,
            }
        ],
        scope_filters=[
            StrategySignal.trade_date == target,
            StrategySignal.algo_version == "v1",
        ],
        key_columns=["trade_date", "ts_code", "signal_type", "algo_version"],
        update_columns=["score"],
    )

    assert count == 1
    delete_sql = _sql(db.statements[1])
    upsert_sql = _sql(db.statements[2])
    assert "000002.SZ" in delete_sql
    assert "000001.SZ" not in delete_sql
    assert "ON CONFLICT (trade_date, ts_code, signal_type, algo_version)" in upsert_sql
    assert "DO UPDATE SET score = excluded.score" in upsert_sql
    assert "id =" not in upsert_sql


def test_signal_forward_eval_uses_cascade_lifecycle() -> None:
    foreign_key = next(iter(SignalForwardEval.__table__.foreign_keys))

    assert foreign_key.target_fullname == "strategy_signal.id"
    assert foreign_key.ondelete == "CASCADE"


@pytest.mark.parametrize(
    ("model", "existing", "rows", "scope_filters", "key_columns", "stale_marker"),
    [
        (
            SectorFactorDaily,
            [(date(2026, 9, 15), 1), (date(2026, 9, 15), 2)],
            [{"trade_date": date(2026, 9, 15), "sector_id": 1}],
            [SectorFactorDaily.trade_date == date(2026, 9, 15)],
            ["trade_date", "sector_id"],
            "2",
        ),
        (
            StockFactorDaily,
            [(date(2026, 9, 15), "000001.SZ"), (date(2026, 9, 15), "000002.SZ")],
            [{"trade_date": date(2026, 9, 15), "ts_code": "000001.SZ"}],
            [StockFactorDaily.trade_date == date(2026, 9, 15)],
            ["trade_date", "ts_code"],
            "000002.SZ",
        ),
        (
            MarketDaily,
            [(date(2026, 9, 14),), (date(2026, 9, 15),)],
            [{"trade_date": date(2026, 9, 15)}],
            [
                MarketDaily.trade_date >= date(2026, 9, 14),
                MarketDaily.trade_date <= date(2026, 9, 15),
            ],
            ["trade_date"],
            "2026-09-14",
        ),
    ],
)
def test_replace_slice_removes_stale_derived_rows(
    model,
    existing,
    rows,
    scope_filters,
    key_columns,
    stale_marker,
) -> None:
    db = _Db(existing)

    replace_slice_rows(
        db,
        model,
        rows,
        scope_filters=scope_filters,
        key_columns=key_columns,
    )

    assert stale_marker in _sql(db.statements[1])


def test_state_replace_slice_only_deletes_current_algo_version() -> None:
    target = date(2026, 9, 15)
    db = _Db(
        [
            (target, "000001.SZ", "v2"),
            (target, "000002.SZ", "v2"),
        ]
    )

    replace_slice_rows(
        db,
        StockStateDaily,
        [
            {
                "trade_date": target,
                "ts_code": "000001.SZ",
                "algo_version": "v2",
                "state": "S3",
            }
        ],
        scope_filters=[
            StockStateDaily.trade_date == target,
            StockStateDaily.algo_version == "v2",
        ],
        key_columns=["trade_date", "ts_code", "algo_version"],
    )

    delete_sql = _sql(db.statements[1])
    assert "stock_state_daily.algo_version = 'v2'" in delete_sql
    assert "000002.SZ" in delete_sql
