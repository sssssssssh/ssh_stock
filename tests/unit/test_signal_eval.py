import inspect
from datetime import date, timedelta

import app.api.v1.research as research_api
import app.cli as cli_module
import pytest
from app.models.market_data import SignalForwardEval
from app.services.research import (
    SignalEvaluationService,
    evaluate_forward_returns,
    evaluate_forward_returns_v3,
)


def test_evaluate_forward_returns_calculates_closed_horizons() -> None:
    base = date(2026, 1, 1)
    rows = [
        {"trade_date": base + timedelta(days=offset), "adj_close": 100.0 + offset}
        for offset in range(0, 22)
    ]

    result = evaluate_forward_returns(base, rows)

    assert result is not None
    assert result["ret5"] == pytest.approx(0.05)
    assert result["ret10"] == pytest.approx(0.10)
    assert result["ret20"] == pytest.approx(0.20)
    assert result["ret60"] is None
    assert result["mfe20"] == pytest.approx(0.20)
    assert result["mae20"] == pytest.approx(0.01)
    assert result["evaluated_until_date"] == base + timedelta(days=21)


def test_evaluate_forward_returns_requires_exact_signal_date_close() -> None:
    base = date(2026, 1, 1)
    rows = [{"trade_date": base + timedelta(days=1), "adj_close": 101.0}]

    assert evaluate_forward_returns(base, rows) is None


def test_eval_v3_uses_entry_relative_market_horizons_and_adjusted_high_low() -> None:
    base = date(2026, 1, 1)
    dates = [base + timedelta(days=offset) for offset in range(0, 62)]
    rows = [
        {
            "trade_date": current,
            "adj_open": 100 + offset,
            "adj_high": 102 + offset,
            "adj_low": 98 + offset,
            "adj_close": 100 + offset,
            "raw_open": 10 + offset,
            "up_limit": 20 + offset,
            "tradable": True,
            "is_suspended": False,
            "is_limit_up_close": False,
            "is_limit_down_close": False,
        }
        for offset, current in enumerate(dates)
    ]

    result = evaluate_forward_returns_v3(base, dates, rows, entry_basis="NEXT_OPEN")

    assert result is not None
    assert result["entry_trade_date"] == dates[1]
    assert result["entry_price"] == 101
    assert result["ret5"] == pytest.approx(106 / 101 - 1)
    assert result["ret10"] == pytest.approx(111 / 101 - 1)
    assert result["ret20"] == pytest.approx(121 / 101 - 1)
    assert result["ret60"] == pytest.approx(161 / 101 - 1)
    assert result["mfe20"] == pytest.approx(123 / 101 - 1)
    assert result["mae20"] == pytest.approx(100 / 101 - 1)
    assert result["horizon_basis"] == "MARKET_TRADING_DAY"
    assert result["eval_version"] == "eval_v3"
    assert result["evaluated_until_date"] == dates[-1]


def test_eval_v3_does_not_shift_missing_stock_horizon() -> None:
    base = date(2026, 1, 1)
    dates = [base + timedelta(days=offset) for offset in range(0, 12)]
    rows = [
        {
            "trade_date": current,
            "adj_open": 100,
            "adj_high": 101,
            "adj_low": 99,
            "adj_close": 100 + offset,
            "raw_open": 10,
            "up_limit": 11,
            "tradable": True,
            "is_suspended": False,
            "is_limit_up_close": False,
            "is_limit_down_close": False,
        }
        for offset, current in enumerate(dates)
        if offset != 5
    ]

    result = evaluate_forward_returns_v3(base, dates, rows, entry_basis="SIGNAL_CLOSE")

    assert result is not None
    assert result["ret5"] is None
    assert result["ret10"] == pytest.approx(0.10)


def test_eval_v3_never_fabricates_suspended_or_limit_up_entry_price() -> None:
    base = date(2026, 1, 1)
    dates = [base, base + timedelta(days=1)]
    suspended = {
        "trade_date": dates[1],
        "adj_open": 101,
        "raw_open": 11,
        "up_limit": 11,
        "tradable": False,
        "is_suspended": True,
    }

    result = evaluate_forward_returns_v3(
        base,
        dates,
        [suspended],
        entry_basis="NEXT_OPEN",
    )

    assert result is not None
    assert result["entry_executable"] is False
    assert result["entry_price"] is None
    assert result["non_executable_reason"] == "SUSPENDED"

    limit_up = {
        **suspended,
        "tradable": True,
        "is_suspended": False,
        "raw_open": 11,
        "up_limit": 11,
    }
    result = evaluate_forward_returns_v3(
        base,
        dates,
        [limit_up],
        entry_basis="NEXT_OPEN",
    )
    assert result is not None
    assert result["entry_executable"] is False
    assert result["non_executable_reason"] == "LIMIT_UP"


def test_eval_v3_marks_limit_down_horizon_exit_non_executable() -> None:
    base = date(2026, 1, 1)
    dates = [base + timedelta(days=offset) for offset in range(0, 22)]
    rows = [
        {
            "trade_date": current,
            "adj_open": 100,
            "adj_high": 101,
            "adj_low": 99,
            "adj_close": 100,
            "raw_open": 10,
            "up_limit": 11,
            "tradable": True,
            "is_suspended": False,
            "is_limit_up_close": False,
            "is_limit_down_close": offset == 20,
        }
        for offset, current in enumerate(dates)
    ]

    result = evaluate_forward_returns_v3(base, dates, rows, entry_basis="SIGNAL_CLOSE")

    assert result is not None
    assert result["ret20"] is None
    assert result["exit_executable"] is False
    assert result["non_executable_reason"] == "HORIZON20_LIMIT_DOWN"


def test_eval_v3_marks_suspended_horizon_exit_non_executable() -> None:
    base = date(2026, 1, 1)
    dates = [base + timedelta(days=offset) for offset in range(0, 22)]
    rows = [
        {
            "trade_date": current,
            "adj_open": 100,
            "adj_high": 101,
            "adj_low": 99,
            "adj_close": 100,
            "raw_open": 10,
            "up_limit": 11,
            "tradable": offset != 20,
            "is_suspended": offset == 20,
            "is_limit_up_close": False,
            "is_limit_down_close": False,
        }
        for offset, current in enumerate(dates)
    ]

    result = evaluate_forward_returns_v3(base, dates, rows, entry_basis="SIGNAL_CLOSE")

    assert result is not None
    assert result["ret20"] is None
    assert result["exit_executable"] is False
    assert result["non_executable_reason"] == "HORIZON20_SUSPENDED"


@pytest.mark.parametrize(
    ("entry_basis", "entry_index", "price_field"),
    [
        ("SIGNAL_CLOSE", 0, "adj_close"),
        ("NEXT_OPEN", 1, "adj_open"),
        ("NEXT_CLOSE", 1, "adj_close"),
    ],
)
def test_eval_v3_entry_basis_uses_entry_day_zero(
    entry_basis: str,
    entry_index: int,
    price_field: str,
) -> None:
    base = date(2026, 1, 1)
    dates = [base + timedelta(days=offset) for offset in range(0, 8)]
    rows = [
        {
            "trade_date": current,
            "adj_open": 100 + offset,
            "adj_high": 102 + offset,
            "adj_low": 98 + offset,
            "adj_close": 200 + offset,
            "raw_open": 10 + offset,
            "up_limit": 20 + offset,
            "tradable": True,
            "is_suspended": False,
            "is_limit_up_close": False,
            "is_limit_down_close": False,
        }
        for offset, current in enumerate(dates)
    ]

    result = evaluate_forward_returns_v3(base, dates, rows, entry_basis=entry_basis)

    assert result is not None
    assert result["entry_trade_date"] == dates[entry_index]
    assert result["entry_price"] == rows[entry_index][price_field]
    assert result["ret5"] == pytest.approx(
        rows[entry_index + 5]["adj_close"] / rows[entry_index][price_field] - 1
    )


def test_eval_v3_is_default_and_current_algorithm_cannot_write_eval_v2() -> None:
    service_default = inspect.signature(SignalEvaluationService.evaluate).parameters[
        "eval_version"
    ].default
    api_default = inspect.signature(research_api.signal_stats).parameters[
        "eval_version"
    ].default
    cli_default = inspect.signature(cli_module.evaluate_signals).parameters[
        "eval_version"
    ].default.default

    assert service_default == "eval_v3"
    assert api_default == "eval_v3"
    assert cli_default == "eval_v3"
    with pytest.raises(ValueError, match="unsupported eval_version: eval_v2"):
        SignalEvaluationService(object()).evaluate(eval_version="eval_v2")

    unique_columns = next(
        constraint
        for constraint in SignalForwardEval.__table__.constraints
        if constraint.name == "uq_signal_forward_eval_version_basis"
    ).columns.keys()
    assert unique_columns == ["signal_id", "eval_version", "entry_basis"]
