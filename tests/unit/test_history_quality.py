from datetime import date

from app.services.quality import history_quality
from app.services.quality.history_quality import HistoricalDataQualityService
from app.services.quality.raw_completeness import RawCompletenessResult, RawDatasetCompleteness


class _FakeHistoricalQualityService(HistoricalDataQualityService):
    def __init__(self) -> None:
        super().__init__(db=object(), strategy={})
        self.trade_dates = [date(2026, 1, 2)]

    def _open_trade_dates(self, start: date, end: date) -> list[date]:
        return [day for day in self.trade_dates if start <= day <= end]


def _dataset(status: str) -> RawDatasetCompleteness:
    return RawDatasetCompleteness(
        dataset="test",
        status=status,
        expected_rows=1,
        actual_rows=1 if status != "ERROR" else 0,
        coverage_rate=1.0 if status != "ERROR" else 0.0,
        missing_codes=[] if status != "ERROR" else ["000001.SZ"],
        extra_codes=[],
    )


def _raw_result(
    *,
    stock_daily: str = "PASS",
    adj_factor: str = "PASS",
    daily_basic: str = "PASS",
    index_daily: str = "PASS",
) -> RawCompletenessResult:
    return RawCompletenessResult(
        trade_date=date(2026, 1, 2),
        stock_daily=_dataset(stock_daily),
        adj_factor=_dataset(adj_factor),
        daily_basic=_dataset(daily_basic),
        index_daily=_dataset(index_daily),
    )


def test_historical_quality_validate_counts_raw_error(monkeypatch) -> None:
    monkeypatch.setattr(history_quality, "ensure_stock_basic_ready", lambda db: None)
    monkeypatch.setattr(
        history_quality,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_result(adj_factor="ERROR"),
    )
    monkeypatch.setattr(history_quality, "record_cross_table_quality", lambda *args, **kwargs: None)

    summary = _FakeHistoricalQualityService().validate(date(2026, 1, 1), date(2026, 1, 31))

    assert summary.total_days == 1
    assert summary.pass_days == 0
    assert summary.warning_days == 0
    assert summary.error_days == 1


def test_historical_quality_validate_counts_raw_warning(monkeypatch) -> None:
    monkeypatch.setattr(history_quality, "ensure_stock_basic_ready", lambda db: None)
    monkeypatch.setattr(
        history_quality,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_result(adj_factor="WARNING"),
    )
    monkeypatch.setattr(history_quality, "record_cross_table_quality", lambda *args, **kwargs: None)

    summary = _FakeHistoricalQualityService().validate(date(2026, 1, 1), date(2026, 1, 31))

    assert summary.total_days == 1
    assert summary.pass_days == 0
    assert summary.warning_days == 1
    assert summary.error_days == 0


def test_historical_quality_progress_includes_raw_dataset_status(monkeypatch) -> None:
    progress = []
    monkeypatch.setattr(history_quality, "ensure_stock_basic_ready", lambda db: None)
    monkeypatch.setattr(
        history_quality,
        "check_raw_completeness",
        lambda *args, **kwargs: _raw_result(index_daily="ERROR"),
    )
    monkeypatch.setattr(history_quality, "record_cross_table_quality", lambda *args, **kwargs: None)

    summary = _FakeHistoricalQualityService().validate(
        date(2026, 1, 1),
        date(2026, 1, 31),
        progress_callback=lambda summary, trade_date, result: progress.append(
            (summary, trade_date, result)
        ),
    )

    assert summary.error_days == 1
    assert progress[0][2].as_metadata()["current_day_datasets"]["index_daily"] == "ERROR"
    assert progress[0][2].overall_status == "ERROR"
