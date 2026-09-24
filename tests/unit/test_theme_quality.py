from datetime import date
from types import SimpleNamespace

import app.api.v1.themes as themes_api
from app.services.quality.theme_quality import historical_theme_members


class _Result:
    def __init__(self, *, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars or []

    def all(self):
        return self._rows

    def scalars(self):
        return _Result(rows=self._scalars)


def test_theme_api_uses_factor_member_snapshot_before_fallback(monkeypatch) -> None:
    expected = date(2026, 9, 24)
    monkeypatch.setattr(
        themes_api,
        "theme_factor_member_snapshot",
        lambda *args, **kwargs: expected,
    )
    monkeypatch.setattr(
        themes_api,
        "latest_usable_theme_member_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("factor snapshot must not fall back to an older PASS snapshot")
        ),
    )

    assert (
        themes_api._member_snapshot_for_factor(
            object(), date(2026, 9, 24), "hash", "885001.TI"
        )
        == expected
    )


def test_historical_theme_members_prefers_interval_then_real_snapshot() -> None:
    interval = SimpleNamespace(
        theme_code="885001.TI",
        ts_code="000001.SZ",
        valid_from=date(2026, 9, 10),
        valid_to=None,
        source="THS",
    )
    quality = SimpleNamespace(
        trade_date=date(2026, 9, 5), status="WARNING", coverage_rate=0.96
    )
    snapshot = SimpleNamespace(
        snapshot_date=date(2026, 9, 5),
        theme_code="885002.TI",
        ts_code="000002.SZ",
        stock_name="B",
        source="THS",
    )

    class Db:
        def __init__(self):
            self.results = [
                _Result(scalars=[interval]),
                _Result(rows=[quality]),
                _Result(scalars=[snapshot]),
            ]

        def execute(self, statement):
            return self.results.pop(0)

    before_interval = date(2026, 9, 8)
    during_interval = date(2026, 9, 12)
    frame, valid_dates, context = historical_theme_members(
        Db(), [before_interval, during_interval]
    )

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
    assert set(frame.loc[frame["snapshot_date"] == before_interval, "ts_code"]) == {
        "000002.SZ"
    }
    assert set(frame.loc[frame["snapshot_date"] == during_interval, "ts_code"]) == {
        "000001.SZ",
        "000002.SZ",
    }
