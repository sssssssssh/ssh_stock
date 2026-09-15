from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.providers.base import MarketDataProvider


@dataclass(frozen=True)
class ProviderSmokeResult:
    api_name: str
    rows: int


def run_provider_smoke_test(
    provider: MarketDataProvider,
    target_date: date,
    *,
    index_codes: list[str],
) -> list[ProviderSmokeResult]:
    calendar = provider.get_trade_calendar(target_date - timedelta(days=14), target_date)
    _require_columns("trade_cal", calendar, {"cal_date", "is_open"})
    open_date = _latest_open_date(calendar)

    calls = [
        ("stock_basic", provider.get_stock_basic(), {"ts_code", "list_status", "list_date"}),
        ("daily", provider.get_daily(open_date), {"trade_date", "ts_code", "close"}),
        ("adj_factor", provider.get_adj_factor(open_date), {"trade_date", "ts_code", "adj_factor"}),
        (
            "daily_basic",
            provider.get_daily_basic(open_date),
            {"trade_date", "ts_code", "close", "total_mv", "circ_mv"},
        ),
        (
            "index_daily",
            provider.get_index_daily(open_date, index_codes),
            {"trade_date", "ts_code", "close", "pre_close"},
        ),
        (
            "index_classify",
            provider.get_sector_classification(),
            {"index_code", "level"},
        ),
        (
            "index_member_all",
            provider.get_sector_members(),
            {"l1_code", "in_date"},
        ),
        ("stock_st", provider.get_stock_st(open_date), {"trade_date", "ts_code"}),
        (
            "suspend_d",
            provider.get_suspend_daily(open_date),
            {"ts_code", "trade_date", "suspend_type"},
        ),
        (
            "stk_limit",
            provider.get_stock_limit(open_date),
            {"trade_date", "ts_code", "up_limit", "down_limit"},
        ),
    ]
    results = [ProviderSmokeResult("trade_cal", len(calendar.index))]
    for api_name, frame, required in calls:
        _require_columns(api_name, frame, required)
        results.append(ProviderSmokeResult(api_name, len(frame.index)))
    return results


def _require_columns(api_name: str, frame: pd.DataFrame, required: set[str]) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{api_name} did not return a DataFrame")
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{api_name} missing required fields: {missing}")


def _latest_open_date(calendar: pd.DataFrame) -> date:
    open_rows = calendar[calendar["is_open"].astype(str).isin({"1", "True", "true"})]
    if open_rows.empty:
        raise ValueError("trade_cal returned no open date in smoke-test window")
    value = open_rows["cal_date"].max()
    return pd.Timestamp(value).date()
