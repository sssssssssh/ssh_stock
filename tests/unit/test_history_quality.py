from datetime import date

from app.services.quality import history_quality
from app.services.quality.history_quality import HistoricalDataQualityService


class _FakeHistoricalQualityService(HistoricalDataQualityService):
    def __init__(self) -> None:
        super().__init__(
            db=object(),
            strategy={
                "data_quality": {
                    "daily": {
                        "warning_coverage_rate": 0.98,
                        "error_coverage_rate": 0.95,
                    }
                }
            },
        )
        self.expected = {f"{idx:06d}.SZ" for idx in range(100)}
        self.actual_by_date = {
            date(2026, 1, 2): set(self.expected),
            date(2026, 1, 5): set(list(self.expected)[:97]),
            date(2026, 1, 6): set(list(self.expected)[:90]),
        }

    def _open_trade_dates(self, start: date, end: date) -> list[date]:
        return [day for day in self.actual_by_date if start <= day <= end]

    def _expected_stock_codes(self, trade_date: date) -> set[str]:
        return self.expected

    def _stock_daily_codes(self, trade_date: date) -> set[str]:
        return self.actual_by_date[trade_date]

    def _stock_daily_duplicate_count(self, trade_date: date) -> int:
        return 0


def test_historical_quality_validate_writes_pass_warning_error(monkeypatch) -> None:
    persisted = []
    cross_checked = []
    monkeypatch.setattr(
        history_quality,
        "persist_coverage_result",
        lambda db, result, **kwargs: persisted.append((result.trade_date, result.status)),
    )
    monkeypatch.setattr(
        history_quality,
        "record_cross_table_quality",
        lambda db, trade_date, **kwargs: cross_checked.append(trade_date),
    )
    monkeypatch.setattr(history_quality, "ensure_stock_basic_ready", lambda db: None)

    summary = _FakeHistoricalQualityService().validate(date(2026, 1, 1), date(2026, 1, 31))

    assert summary.total_days == 3
    assert summary.pass_days == 1
    assert summary.warning_days == 1
    assert summary.error_days == 1
    assert persisted == [
        (date(2026, 1, 2), "PASS"),
        (date(2026, 1, 5), "WARNING"),
        (date(2026, 1, 6), "ERROR"),
    ]
    assert cross_checked == [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]
