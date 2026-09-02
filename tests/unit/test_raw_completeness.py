from datetime import date

import app.services.quality.raw_completeness as raw_module
from app.services.quality.raw_completeness import check_raw_completeness


def test_raw_completeness_requires_dataset_coverage(monkeypatch) -> None:
    expected_stocks = {"000001.SZ", "000002.SZ", "000003.SZ"}
    stock_daily = {"000001.SZ", "000002.SZ", "000003.SZ"}
    adj_factor = {"000001.SZ"}
    daily_basic = {"000001.SZ", "000002.SZ", "000003.SZ"}
    index_daily = {"000300.SH", "000001.SH", "000852.SH"}

    monkeypatch.setattr(raw_module, "expected_stock_codes", lambda db, trade_date: expected_stocks)
    monkeypatch.setattr(
        raw_module,
        "_codes_for_date",
        lambda db, model, column, trade_date: {
            "stock_daily": stock_daily,
            "stock_adj_factor": adj_factor,
            "stock_daily_basic": daily_basic,
            "index_daily": index_daily,
        }[model.__tablename__],
    )

    result = check_raw_completeness(
        object(),
        date(2026, 8, 31),
        strategy={
            "benchmark": {"market_indices": ["000300.SH", "000001.SH", "000852.SH"]},
            "raw_quality": {
                "adj_factor": {"warning_coverage_rate": 0.98, "error_coverage_rate": 0.95}
            },
        },
    )

    assert result.stock_daily_status == "PASS"
    assert result.adj_factor_status == "ERROR"
    assert result.daily_basic_status == "PASS"
    assert result.index_daily_status == "PASS"
    assert result.is_complete is False


def test_raw_completeness_requires_all_configured_indices(monkeypatch) -> None:
    expected_stocks = {"000001.SZ", "000002.SZ"}
    all_stocks = {"000001.SZ", "000002.SZ"}

    monkeypatch.setattr(raw_module, "expected_stock_codes", lambda db, trade_date: expected_stocks)
    monkeypatch.setattr(
        raw_module,
        "_codes_for_date",
        lambda db, model, column, trade_date: (
            {"000300.SH", "000001.SH"} if model.__tablename__ == "index_daily" else all_stocks
        ),
    )

    result = check_raw_completeness(
        object(),
        date(2026, 8, 31),
        strategy={"benchmark": {"market_indices": ["000300.SH", "000001.SH", "000852.SH"]}},
    )

    assert result.index_daily_status == "ERROR"
    assert result.index_daily.missing_codes == ["000852.SH"]
    assert result.is_complete is False
