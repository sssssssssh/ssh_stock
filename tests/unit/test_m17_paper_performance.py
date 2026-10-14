from decimal import Decimal

from app.domain.decision.performance import frozen_performance


def row(day, nav, benchmark="1"):
    return {
        "trade_date": day,
        "nav": nav,
        "cash": "1000",
        "market_value": "0",
        "benchmark_nav": benchmark,
        "trading_cost": "5",
        "data": {"turnover": "0.1"},
    }


def test_continuous_decimal_nav_and_drawdown():
    rows = [row("2026-10-14", "1.1"), row("2026-10-15", "0.99")]
    result = frozen_performance(
        rows, expected_dates=[r["trade_date"] for r in rows], initial_cash=Decimal("1000")
    )
    assert result["continuous"]
    assert result["cumulative_return"] == Decimal("-0.01")
    assert result["maximum_drawdown"] == Decimal("-0.10")
    assert result["series"][1]["daily_return"] == Decimal("-0.10")
    assert result["cumulative_cost"] == "10" and result["cumulative_turnover"] == "0.2"


def test_gap_inserts_null_not_interpolated_value():
    rows = [row("2026-10-14", "1"), row("2026-10-16", "1.1")]
    result = frozen_performance(
        rows,
        expected_dates=["2026-10-14", "2026-10-15", "2026-10-16"],
        initial_cash=Decimal("1000"),
    )
    assert not result["continuous"] and result["maximum_drawdown"] is None
    assert result["cumulative_return"] is None
    assert result["series"][1]["nav"] is None and not result["series"][1]["valid"]
    assert all(r["daily_return"] is None for r in result["series"])


def test_review_required_and_missing_benchmark_do_not_fake_comparisons():
    rows = [row("2026-10-14", "1.1", None)]
    result = frozen_performance(
        rows,
        expected_dates=["2026-10-14"],
        initial_cash=Decimal("1000"),
        invalid_dates={"2026-10-14"},
    )
    assert not result["continuous"] and not result["series"][0]["valid"]
    assert result["benchmark_status"] == "BENCHMARK_UNAVAILABLE"
    assert result["series"][0]["benchmark_nav"] is None
