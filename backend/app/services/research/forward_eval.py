from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from app.services.research.signal_eval import _executable_entry, _executable_exit, _positive

HORIZONS = (5, 10, 20, 60)


def evaluate_stock_forward(
    event_date: date,
    market_dates: Sequence[date],
    stock_rows: Mapping[date, dict[str, Any]],
    benchmark_rows: Mapping[date, dict[str, Any]],
    *,
    horizons: Sequence[int] = HORIZONS,
) -> dict[str, Any]:
    dates = list(market_dates)
    result = _empty_forward(horizons, dates)
    if event_date not in dates or dates.index(event_date) + 1 >= len(dates):
        return result
    entry_index = dates.index(event_date) + 1
    entry_date = dates[entry_index]
    entry_row = stock_rows.get(entry_date)
    if entry_row is not None and entry_row.get("raw_present") is False:
        entry_price, entry_reason = None, "NO_STOCK_ROW"
    elif entry_row is not None and entry_row.get("status_present") is False:
        entry_price, entry_reason = None, "TRADE_STATUS_MISSING"
    else:
        entry_price, entry_reason = _executable_entry(entry_row, "adj_open", use_open_limit=True)
    result.update(
        entry_trade_date=entry_date,
        entry_price=entry_price,
        entry_executable=entry_reason is None,
        entry_reason=entry_reason,
    )
    for horizon in horizons:
        index = entry_index + horizon
        if index >= len(dates):
            continue
        exit_date = dates[index]
        result[f"mature{horizon}"] = True
        result[f"exit_trade_date{horizon}"] = exit_date
        exit_row = stock_rows.get(exit_date)
        if exit_row is not None and exit_row.get("raw_present") is False:
            exit_price, exit_reason = None, "NO_STOCK_ROW"
        elif exit_row is not None and exit_row.get("status_present") is False:
            exit_price, exit_reason = None, "TRADE_STATUS_MISSING"
        else:
            exit_price, exit_reason = _executable_exit(exit_row)
        result[f"exit_executable{horizon}"] = exit_reason is None
        result[f"exit_reason{horizon}"] = exit_reason
        if entry_price is not None and exit_price is not None:
            result[f"ret{horizon}"] = exit_price / entry_price - 1
        benchmark_entry = benchmark_rows.get(entry_date, {}).get("open")
        benchmark_exit = benchmark_rows.get(exit_date, {}).get("close")
        if _positive(benchmark_entry) and _positive(benchmark_exit):
            result[f"benchmark_ret{horizon}"] = float(benchmark_exit) / float(benchmark_entry) - 1
        if result[f"ret{horizon}"] is not None and result[f"benchmark_ret{horizon}"] is not None:
            result[f"excess_ret{horizon}"] = (
                result[f"ret{horizon}"] - result[f"benchmark_ret{horizon}"]
            )
    if result.get("mature20") and entry_price is not None:
        window = [stock_rows.get(day, {}) for day in dates[entry_index + 1 : entry_index + 21]]
        if len(window) == 20 and all(_positive(row.get("adj_high")) for row in window):
            result["mfe20"] = max(float(row["adj_high"]) for row in window) / entry_price - 1
        if len(window) == 20 and all(_positive(row.get("adj_low")) for row in window):
            result["mae20"] = min(float(row["adj_low"]) for row in window) / entry_price - 1
    return result


def evaluate_theme_forward(
    event_date: date,
    market_dates: Sequence[date],
    theme_rows: Mapping[date, dict[str, Any]],
    benchmark_rows: Mapping[date, dict[str, Any]],
    *,
    horizons: Sequence[int] = HORIZONS,
) -> dict[str, Any]:
    dates = list(market_dates)
    result = _empty_forward(horizons, dates)
    if event_date not in dates or dates.index(event_date) + 1 >= len(dates):
        return result
    entry_index = dates.index(event_date) + 1
    entry_date = dates[entry_index]
    entry_row = theme_rows.get(entry_date)
    entry_price = entry_row.get("close") if entry_row else None
    entry_reason = None if _positive(entry_price) else "ENTRY_PRICE_MISSING"
    result.update(
        entry_trade_date=entry_date,
        entry_price=float(entry_price) if entry_reason is None else None,
        entry_executable=entry_reason is None,
        entry_reason=entry_reason,
    )
    for horizon in horizons:
        index = entry_index + horizon
        if index >= len(dates):
            continue
        exit_date = dates[index]
        result[f"mature{horizon}"] = True
        result[f"exit_trade_date{horizon}"] = exit_date
        exit_row = theme_rows.get(exit_date)
        exit_price = exit_row.get("close") if exit_row else None
        exit_reason = None if _positive(exit_price) else "EXIT_PRICE_MISSING"
        result[f"exit_executable{horizon}"] = exit_reason is None
        result[f"exit_reason{horizon}"] = exit_reason
        if result["entry_price"] is not None and exit_reason is None:
            result[f"ret{horizon}"] = float(exit_price) / result["entry_price"] - 1
        benchmark_entry = benchmark_rows.get(entry_date, {}).get("close")
        benchmark_exit = benchmark_rows.get(exit_date, {}).get("close")
        if _positive(benchmark_entry) and _positive(benchmark_exit):
            result[f"benchmark_ret{horizon}"] = float(benchmark_exit) / float(benchmark_entry) - 1
        if result[f"ret{horizon}"] is not None and result[f"benchmark_ret{horizon}"] is not None:
            result[f"excess_ret{horizon}"] = (
                result[f"ret{horizon}"] - result[f"benchmark_ret{horizon}"]
            )
    if result.get("mature20") and result["entry_price"] is not None:
        window = [theme_rows.get(day, {}) for day in dates[entry_index + 1 : entry_index + 21]]
        if len(window) == 20 and all(_positive(row.get("high")) for row in window):
            result["mfe20"] = max(float(row["high"]) for row in window) / result["entry_price"] - 1
        if len(window) == 20 and all(_positive(row.get("low")) for row in window):
            result["mae20"] = min(float(row["low"]) for row in window) / result["entry_price"] - 1
    return result


def _empty_forward(horizons: Sequence[int], dates: Sequence[date]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entry_trade_date": None,
        "entry_price": None,
        "entry_executable": None,
        "entry_reason": None,
        "evaluated_until_date": dates[-1] if dates else None,
        "mfe20": None,
        "mae20": None,
    }
    for horizon in horizons:
        result.update(
            {
                f"mature{horizon}": False,
                f"exit_trade_date{horizon}": None,
                f"exit_executable{horizon}": None,
                f"exit_reason{horizon}": None,
                f"ret{horizon}": None,
                f"benchmark_ret{horizon}": None,
                f"excess_ret{horizon}": None,
            }
        )
    return result
