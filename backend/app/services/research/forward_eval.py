from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from app.services.research.signal_eval import _executable_entry, _executable_exit, _positive

HORIZONS = (5, 10, 20, 60)


def _validated_stock_exit(row: dict[str, Any] | None) -> tuple[float | None, str | None]:
    if row is None or row.get("raw_present") is False:
        return None, "NO_STOCK_ROW"
    if row.get("status_present") is False:
        return None, "TRADE_STATUS_MISSING"
    return _executable_exit(row)


def _mark_price(
    stock_rows: Mapping[date, dict[str, Any]],
    dates: Sequence[date],
    entry_index: int,
    target_index: int,
) -> tuple[date | None, float | None]:
    for index in range(target_index, entry_index - 1, -1):
        price = stock_rows.get(dates[index], {}).get("adj_close")
        if _positive(price):
            return dates[index], float(price)
    return None, None


def _net_return(entry_price: float, exit_price: float, costs: Mapping[str, Any] | None) -> float:
    if not costs or not costs.get("enabled", False):
        return exit_price / entry_price - 1
    commission = float(costs.get("commission_rate", 0))
    stamp_tax = float(costs.get("stamp_tax_sell_rate", 0))
    slippage = float(costs.get("slippage_bps", 0)) / 10_000
    effective_entry = entry_price * (1 + commission + slippage)
    effective_exit = exit_price * (1 - commission - stamp_tax - slippage)
    return effective_exit / effective_entry - 1


def evaluate_stock_forward(
    event_date: date,
    market_dates: Sequence[date],
    stock_rows: Mapping[date, dict[str, Any]],
    benchmark_rows: Mapping[date, dict[str, Any]],
    *,
    horizons: Sequence[int] = HORIZONS,
    executable_exit_search_days: int = 5,
    trading_cost: Mapping[str, Any] | None = None,
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
        exit_price, exit_reason = _validated_stock_exit(exit_row)
        result[f"exit_executable{horizon}"] = exit_reason is None
        result[f"exit_reason{horizon}"] = exit_reason
        mark_date, mark_price = _mark_price(stock_rows, dates, entry_index, index)
        if entry_price is not None and mark_price is not None:
            result[f"mark_trade_date{horizon}"] = mark_date
            result[f"mark_ret{horizon}"] = mark_price / entry_price - 1
        if entry_price is not None and exit_price is not None:
            result[f"ret{horizon}"] = exit_price / entry_price - 1
            result[f"net_ret{horizon}"] = _net_return(entry_price, exit_price, trading_cost)
        if entry_price is not None:
            for delay in range(0, executable_exit_search_days + 1):
                delayed_index = index + delay
                if delayed_index >= len(dates):
                    break
                delayed_date = dates[delayed_index]
                delayed_row = stock_rows.get(delayed_date)
                delayed_price, delayed_reason = _validated_stock_exit(delayed_row)
                if delayed_reason is not None or delayed_price is None:
                    continue
                result[f"delayed_exit_trade_date{horizon}"] = delayed_date
                result[f"delayed_exit_price{horizon}"] = delayed_price
                result[f"delayed_exit_delay_days{horizon}"] = delay
                result[f"delayed_exit_ret{horizon}"] = delayed_price / entry_price - 1
                result[f"net_delayed_exit_ret{horizon}"] = _net_return(
                    entry_price, delayed_price, trading_cost
                )
                break
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
    executable_exit_search_days: int = 5,
    trading_cost: Mapping[str, Any] | None = None,
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
        if result["entry_price"] is not None and _positive(exit_price):
            result[f"mark_trade_date{horizon}"] = exit_date
            result[f"mark_ret{horizon}"] = float(exit_price) / result["entry_price"] - 1
        if result["entry_price"] is not None and exit_reason is None:
            result[f"ret{horizon}"] = float(exit_price) / result["entry_price"] - 1
            result[f"net_ret{horizon}"] = _net_return(
                result["entry_price"], float(exit_price), trading_cost
            )
        if result["entry_price"] is not None:
            for delay in range(0, executable_exit_search_days + 1):
                delayed_index = index + delay
                if delayed_index >= len(dates):
                    break
                delayed_date = dates[delayed_index]
                delayed_price = theme_rows.get(delayed_date, {}).get("close")
                if not _positive(delayed_price):
                    continue
                price = float(delayed_price)
                result[f"delayed_exit_trade_date{horizon}"] = delayed_date
                result[f"delayed_exit_price{horizon}"] = price
                result[f"delayed_exit_delay_days{horizon}"] = delay
                result[f"delayed_exit_ret{horizon}"] = price / result["entry_price"] - 1
                result[f"net_delayed_exit_ret{horizon}"] = _net_return(
                    result["entry_price"], price, trading_cost
                )
                break
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
                f"mark_ret{horizon}": None,
                f"mark_trade_date{horizon}": None,
                f"delayed_exit_trade_date{horizon}": None,
                f"delayed_exit_price{horizon}": None,
                f"delayed_exit_delay_days{horizon}": None,
                f"delayed_exit_ret{horizon}": None,
                f"net_ret{horizon}": None,
                f"net_delayed_exit_ret{horizon}": None,
                f"benchmark_ret{horizon}": None,
                f"excess_ret{horizon}": None,
            }
        )
    return result
