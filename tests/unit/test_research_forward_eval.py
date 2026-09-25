from datetime import date, timedelta

import pytest
from app.core.config import _validate_research_config, get_settings
from app.services.calc_metadata import config_hash
from app.services.research.forward_eval import evaluate_stock_forward, evaluate_theme_forward


def _days(count: int) -> list[date]:
    return [date(2026, 1, 1) + timedelta(days=index) for index in range(count)]


def test_research_hash_is_independent_of_production_hashes() -> None:
    settings = get_settings()
    modified = dict(settings.research_config)
    modified["score_bucket_size"] = 5
    assert config_hash(modified) != config_hash(settings.research_config)
    assert config_hash(settings.strategy) == config_hash(settings.strategy.copy())
    assert config_hash(settings.opportunity_config) == config_hash(
        settings.opportunity_config.copy()
    )


@pytest.mark.parametrize(
    "change",
    [
        {"horizons": [5, 5]},
        {"horizons": [5, 251]},
        {"horizons": [5, 10, 20]},
        {"transition_horizons": [5, 20]},
        {"left_thresholds": [-1, 50]},
        {"theme_topn": [20, 5]},
        {"score_bucket_size": 51},
        {"refresh_lookback_trade_days": 60},
    ],
)
def test_invalid_research_config_is_rejected(change) -> None:
    config = dict(get_settings().research_config)
    config.update(change)
    with pytest.raises(ValueError, match="research"):
        _validate_research_config(config)


def test_stock_forward_uses_next_open_market_horizons_and_excess() -> None:
    days = _days(22)
    stock = {
        day: {
            "adj_open": 100,
            "adj_close": 110 if index == 6 else 100,
            "adj_high": 115,
            "adj_low": 95,
            "raw_open": 100,
            "up_limit": 120,
            "tradable": True,
            "is_suspended": False,
        }
        for index, day in enumerate(days)
    }
    benchmark = {
        day: {"open": 100, "close": 104 if index == 6 else 100} for index, day in enumerate(days)
    }
    result = evaluate_stock_forward(days[0], days, stock, benchmark)
    assert result["entry_trade_date"] == days[1]
    assert result["exit_trade_date5"] == days[6]
    assert result["ret5"] == pytest.approx(0.1)
    assert result["excess_ret5"] == pytest.approx(0.06)
    assert result["mature20"] is True
    assert result["mfe20"] == pytest.approx(0.15)
    assert result["mae20"] == pytest.approx(-0.05)
    assert result["mature60"] is False
    assert result["ret60"] is None


@pytest.mark.parametrize(
    ("entry_change", "exit_change", "entry_reason", "exit_reason"),
    [
        ({"is_suspended": True}, {}, "SUSPENDED", None),
        ({"raw_open": 120}, {}, "LIMIT_UP", None),
        ({"adj_open": None}, {}, "ENTRY_PRICE_MISSING", None),
        ({}, {"is_suspended": True}, None, "SUSPENDED"),
        ({}, {"is_limit_down_close": True}, None, "LIMIT_DOWN"),
        ({}, {"adj_close": None}, None, "EXIT_PRICE_MISSING"),
    ],
)
def test_stock_execution_is_separate_from_maturity(
    entry_change, exit_change, entry_reason, exit_reason
) -> None:
    days = _days(7)
    base = {
        "adj_open": 100,
        "adj_close": 110,
        "raw_open": 100,
        "up_limit": 120,
        "is_suspended": False,
        "tradable": True,
    }
    stock = {days[1]: {**base, **entry_change}, days[6]: {**base, **exit_change}}
    result = evaluate_stock_forward(days[0], days, stock, {})
    assert result["mature5"] is True
    assert result["entry_reason"] == entry_reason
    assert result["exit_reason5"] == exit_reason
    assert result["ret5"] is None


def test_theme_forward_uses_next_close_without_lookahead() -> None:
    days = _days(9)
    theme = {
        day: {"close": 100 if index < 6 else 110, "high": 120, "low": 90}
        for index, day in enumerate(days)
    }
    theme[days[0]]["close"] = 10
    benchmark = {day: {"close": 100 if index < 6 else 104} for index, day in enumerate(days)}
    result = evaluate_theme_forward(days[0], days, theme, benchmark)
    assert result["entry_trade_date"] == days[1]
    assert result["entry_price"] == 100
    assert result["ret5"] == pytest.approx(0.1)
    assert result["excess_ret5"] == pytest.approx(0.06)
    assert result["mature10"] is False
    assert result["ret10"] is None


def test_stock_horizon_matures_later_without_changing_event_identity() -> None:
    days = _days(22)
    stock = {
        day: {
            "adj_open": 100,
            "adj_close": 110,
            "raw_open": 100,
            "up_limit": 120,
            "tradable": True,
            "is_suspended": False,
        }
        for day in days
    }
    early = evaluate_stock_forward(days[0], days[:9], stock, {})
    mature = evaluate_stock_forward(days[0], days, stock, {})
    assert early["mature5"] is True
    assert early["mature20"] is False
    assert early["ret20"] is None
    assert mature["mature20"] is True
    assert mature["ret20"] == pytest.approx(0.1)
    assert mature["benchmark_ret20"] is None
    assert mature["excess_ret20"] is None


def test_stock_missing_entry_and_exit_rows_keep_maturity() -> None:
    days = _days(7)
    missing_entry = evaluate_stock_forward(days[0], days, {}, {})
    assert missing_entry["entry_reason"] == "NO_STOCK_ROW"
    assert missing_entry["mature5"] is True
    assert missing_entry["exit_reason5"] == "NO_STOCK_ROW"
    assert missing_entry["ret5"] is None


@pytest.mark.parametrize(
    ("flag", "reason"),
    [("raw_present", "NO_STOCK_ROW"), ("status_present", "TRADE_STATUS_MISSING")],
)
def test_stock_partial_source_rows_are_not_treated_as_executable(flag, reason) -> None:
    days = _days(7)
    stock = {
        day: {
            "adj_open": 100,
            "adj_close": 110,
            "raw_open": 100,
            "raw_present": True,
            "status_present": True,
            "tradable": True,
            "is_suspended": False,
        }
        for day in days
    }
    stock[days[1]][flag] = False
    result = evaluate_stock_forward(days[0], days, stock, {})
    assert result["mature5"] is True
    assert result["entry_reason"] == reason
    assert result["ret5"] is None


def test_limit_down_keeps_mark_return_and_uses_delayed_executable_exit() -> None:
    days = _days(10)
    stock = {
        day: {
            "adj_open": 100,
            "adj_close": 100,
            "raw_open": 100,
            "up_limit": 120,
            "is_suspended": False,
            "tradable": True,
            "is_limit_down_close": False,
        }
        for day in days
    }
    stock[days[6]]["adj_close"] = 80
    stock[days[6]]["is_limit_down_close"] = True
    stock[days[7]]["adj_close"] = 75
    stock[days[7]]["is_limit_down_close"] = True
    stock[days[8]]["adj_close"] = 78

    result = evaluate_stock_forward(
        days[0], days, stock, {}, horizons=(5,), executable_exit_search_days=5
    )

    assert result["exit_executable5"] is False
    assert result["ret5"] is None
    assert result["mark_ret5"] == pytest.approx(-0.2)
    assert result["delayed_exit_trade_date5"] == days[8]
    assert result["delayed_exit_delay_days5"] == 2
    assert result["delayed_exit_ret5"] == pytest.approx(-0.22)


def test_trading_cost_produces_separate_net_returns() -> None:
    days = _days(7)
    stock = {
        day: {
            "adj_open": 100,
            "adj_close": 110,
            "raw_open": 100,
            "up_limit": 120,
            "is_suspended": False,
            "tradable": True,
        }
        for day in days
    }
    costs = {
        "enabled": True,
        "commission_rate": 0.0003,
        "minimum_commission_cny": 5,
        "stamp_tax_sell_rate": 0.0005,
        "slippage_bps": 5,
    }
    result = evaluate_stock_forward(
        days[0], days, stock, {}, horizons=(5,), trading_cost=costs
    )
    expected = 110 * (1 - 0.0003 - 0.0005 - 0.0005) / (100 * (1 + 0.0003 + 0.0005)) - 1

    assert result["ret5"] == pytest.approx(0.1)
    assert result["net_ret5"] == pytest.approx(expected)
    assert result["net_delayed_exit_ret5"] == pytest.approx(expected)
