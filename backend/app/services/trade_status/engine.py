from datetime import date

import pandas as pd

from app.services.universe import is_stock_active_on

ST_HISTORY_START = date(2000, 1, 1)


def calculate_trade_status_rows(
    *,
    trade_dates: list[date],
    stock_basic: pd.DataFrame,
    daily: pd.DataFrame,
    stock_st: pd.DataFrame,
    suspend_daily: pd.DataFrame,
    stock_limit: pd.DataFrame,
    exclude_st: bool,
) -> pd.DataFrame:
    basic_records = {
        str(row["ts_code"]): row
        for row in stock_basic.to_dict("records")
        if row.get("ts_code")
    }
    daily_map = _records_by_key(daily, ["trade_date", "ts_code"])
    st_keys = set(_records_by_key(stock_st, ["trade_date", "ts_code"]))
    suspend_keys = {
        (row["trade_date"], str(row["ts_code"]))
        for row in suspend_daily.to_dict("records")
        if row.get("trade_date")
        and row.get("ts_code")
        and str(row.get("suspend_type", "S")).upper() == "S"
    }
    limit_map = _records_by_key(stock_limit, ["trade_date", "ts_code"])
    source_codes_by_date = _source_codes_by_date(daily, stock_st, suspend_daily, stock_limit)

    rows: list[dict[str, object]] = []
    for trade_date in sorted(set(trade_dates)):
        active_codes = {
            ts_code
            for ts_code, basic in basic_records.items()
            if is_stock_active_on(
                _as_date(basic.get("list_date")),
                _as_date(basic.get("delist_date")),
                trade_date,
            )
        }
        all_codes = active_codes | source_codes_by_date.get(trade_date, set())
        for ts_code in sorted(all_codes):
            basic = basic_records.get(ts_code, {})
            is_active = is_stock_active_on(
                _as_date(basic.get("list_date")),
                _as_date(basic.get("delist_date")),
                trade_date,
            ) if basic else False
            is_suspended = (trade_date, ts_code) in suspend_keys
            st_status_unknown = trade_date < ST_HISTORY_START
            is_st = None if st_status_unknown else (trade_date, ts_code) in st_keys
            tradable = is_active and not is_suspended
            strategy_eligible = (
                tradable
                and not st_status_unknown
                and (not exclude_st or is_st is False)
            )
            daily_row = daily_map.get((trade_date, ts_code), {})
            limit_row = limit_map.get((trade_date, ts_code), {})
            close = _as_float(daily_row.get("close"))
            up_limit = _as_float(limit_row.get("up_limit"))
            down_limit = _as_float(limit_row.get("down_limit"))
            reasons = []
            if not is_active:
                reasons.append("NOT_ACTIVE_ON_DATE")
            if is_suspended:
                reasons.append("SUSPENDED")
            if is_st is True:
                reasons.append("ST")
            if st_status_unknown:
                reasons.append("ST_STATUS_UNKNOWN")
            rows.append(
                {
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "is_active": is_active,
                    "is_suspended": is_suspended,
                    "is_st": is_st,
                    "st_status_unknown": st_status_unknown,
                    "up_limit": up_limit,
                    "down_limit": down_limit,
                    "is_limit_up_close": _price_matches(close, up_limit),
                    "is_limit_down_close": _price_matches(close, down_limit),
                    "tradable": tradable,
                    "strategy_eligible": strategy_eligible,
                    "status_reason": ",".join(reasons) if reasons else None,
                }
            )
    return pd.DataFrame(rows)


def _records_by_key(df: pd.DataFrame, columns: list[str]) -> dict[tuple, dict]:
    if df.empty:
        return {}
    result = {}
    for row in df.to_dict("records"):
        if any(row.get(column) is None for column in columns):
            continue
        key = tuple(
            _as_date(row[column]) if column == "trade_date" else str(row[column])
            for column in columns
        )
        result[key] = row
    return result


def _source_codes_by_date(*frames: pd.DataFrame) -> dict[date, set[str]]:
    result: dict[date, set[str]] = {}
    for frame in frames:
        if frame.empty:
            continue
        for row in frame.to_dict("records"):
            trade_date = _as_date(row.get("trade_date"))
            ts_code = row.get("ts_code")
            if trade_date and ts_code:
                result.setdefault(trade_date, set()).add(str(ts_code))
    return result


def _as_date(value) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _as_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _price_matches(price: float | None, limit: float | None) -> bool | None:
    if price is None or limit is None:
        return None
    tolerance = max(0.001, abs(limit) * 1e-6)
    return abs(price - limit) <= tolerance
