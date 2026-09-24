from datetime import date
from types import SimpleNamespace

from app.services.theme.membership import resolve_theme_memberships


class _Result:
    def __init__(self, *, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars or []

    def all(self):
        return self._rows

    def scalars(self):
        return _Result(rows=self._scalars)


def test_theme_membership_resolver_prefers_intervals_and_blocks_ended_pairs() -> None:
    active_interval = SimpleNamespace(
        theme_code="885001.TI",
        ts_code="000001.SZ",
        valid_from=date(2026, 9, 10),
        valid_to=None,
        source="THS",
    )
    ended_interval = SimpleNamespace(
        theme_code="885003.TI",
        ts_code="000003.SZ",
        valid_from=date(2026, 9, 9),
        valid_to=date(2026, 9, 9),
        source="THS",
    )
    quality = SimpleNamespace(
        trade_date=date(2026, 9, 5), status="WARNING", coverage_rate=0.96
    )
    snapshots = [
        SimpleNamespace(
            snapshot_date=date(2026, 9, 5),
            theme_code="885002.TI",
            ts_code="000002.SZ",
            stock_name="B",
            source="THS",
        ),
        SimpleNamespace(
            snapshot_date=date(2026, 9, 5),
            theme_code="885003.TI",
            ts_code="000003.SZ",
            stock_name="C",
            source="THS",
        ),
    ]

    class Db:
        def __init__(self):
            self.results = [
                _Result(scalars=[active_interval, ended_interval]),
                _Result(rows=[quality]),
                _Result(scalars=snapshots),
            ]

        def execute(self, statement):
            return self.results.pop(0)

    before_interval = date(2026, 9, 8)
    during_interval = date(2026, 9, 12)
    resolution = resolve_theme_memberships(Db(), [before_interval, during_interval])
    frame = resolution.members
    valid_dates = resolution.available_dates
    context = resolution.context_by_date

    assert valid_dates == {before_interval, during_interval}
    assert context[before_interval] == {
        "available": True,
        "coverage": 0.96,
        "mode": "SNAPSHOT",
        "source_snapshot_date": date(2026, 9, 5),
    }
    assert context[during_interval] == {
        "available": True,
        "coverage": 0.96,
        "mode": "INTERVAL_SNAPSHOT",
        "source_snapshot_date": date(2026, 9, 5),
    }
    assert set(frame.loc[frame["trade_date"] == before_interval, "ts_code"]) == {
        "000002.SZ",
        "000003.SZ",
    }
    assert set(frame.loc[frame["trade_date"] == during_interval, "ts_code"]) == {
        "000001.SZ",
        "000002.SZ",
    }
    assert set(frame["membership_source"]) == {"INTERVAL", "SNAPSHOT"}
