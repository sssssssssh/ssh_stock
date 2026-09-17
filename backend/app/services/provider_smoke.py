from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from app.providers.base import MarketDataProvider


@dataclass(frozen=True)
class ProviderSmokeResult:
    api_name: str
    rows: int
    status: str = "PASS"
    detail: str | None = None


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

    concepts = provider.get_ths_concepts()
    _require_columns("ths_index", concepts, {"ts_code", "name", "type"})
    if concepts.empty:
        raise ValueError("ths_index returned no concepts")
    results.append(ProviderSmokeResult("ths_index", len(concepts.index)))

    theme_daily = provider.get_ths_daily(open_date)
    _require_columns("ths_daily", theme_daily, {"ts_code", "trade_date", "close", "turnover_rate"})
    results.append(ProviderSmokeResult("ths_daily", len(theme_daily.index)))

    theme_code = str(concepts.iloc[0]["ts_code"])
    members = provider.get_ths_concept_members([theme_code])
    _require_columns("ths_member", members, {"ts_code", "con_code", "con_name"})
    results.append(ProviderSmokeResult("ths_member", len(members.index)))

    optional = [
        (
            "moneyflow_cnt_ths",
            provider.get_ths_concept_moneyflow,
            {"ts_code", "trade_date", "net_amount"},
        ),
        (
            "limit_cpt_list",
            provider.get_limit_concept_list,
            {"ts_code", "trade_date", "up_nums", "cons_nums"},
        ),
    ]
    statuses: dict[str, str] = {}
    for api_name, fetch, required in optional:
        try:
            frame = fetch(open_date)
            _require_columns(api_name, frame, required)
            status = "PASS"
            results.append(ProviderSmokeResult(api_name, len(frame.index), status))
        except Exception as exc:
            status = _optional_status(exc)
            results.append(ProviderSmokeResult(api_name, 0, status, str(exc)))
        statuses[api_name] = status
    results.append(ProviderSmokeResult("theme_capability", 0, _theme_capability(statuses)))
    return results


def _optional_status(exc: Exception) -> str:
    message = str(exc).lower()
    if any(marker in message for marker in ("permission", "无权限", "积分不足")):
        return "PERMISSION_UNAVAILABLE"
    return "ERROR"


def _theme_capability(statuses: dict[str, str]) -> str:
    moneyflow = statuses.get("moneyflow_cnt_ths") == "PASS"
    limits = statuses.get("limit_cpt_list") == "PASS"
    if moneyflow and limits:
        return "FULL"
    if moneyflow:
        return "NO_LIMIT_DATA"
    if limits:
        return "NO_MONEYFLOW"
    return "BASIC_ONLY"


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
