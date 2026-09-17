from datetime import date
from typing import Any

import pandas as pd
from loguru import logger


def parse_tushare_date(value: Any) -> date | None:
    if value is None or pd.isna(value) or value == "":
        return None
    text = str(value)
    return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))


def clean_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def normalize_stock_basic(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        rows.append(
            {
                "ts_code": item.get("ts_code"),
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "market": item.get("market"),
                "exchange": item.get("exchange"),
                "industry": item.get("industry"),
                "list_status": item.get("list_status"),
                "list_date": parse_tushare_date(item.get("list_date")),
                "delist_date": parse_tushare_date(item.get("delist_date")),
                "is_hs": item.get("is_hs"),
            }
        )
    return [row for row in rows if row["ts_code"]]


def normalize_trade_calendar(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        rows.append(
            {
                "cal_date": parse_tushare_date(item.get("cal_date")),
                "is_open": bool(int(item.get("is_open", 0))),
                "pretrade_date": parse_tushare_date(item.get("pretrade_date")),
                "exchange": item.get("exchange") or "SSE",
            }
        )
    return [row for row in rows if row["cal_date"]]


def normalize_stock_daily(df: pd.DataFrame) -> list[dict[str, Any]]:
    fields = ["open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"]
    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        row = {
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "ts_code": item.get("ts_code"),
        }
        row.update({field: clean_float(item.get(field)) for field in fields})
        rows.append(row)
    return [row for row in rows if row["trade_date"] and row["ts_code"]]


def normalize_adj_factor(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        rows.append(
            {
                "trade_date": parse_tushare_date(item.get("trade_date")),
                "ts_code": item.get("ts_code"),
                "adj_factor": clean_float(item.get("adj_factor")),
            }
        )
    return [row for row in rows if row["trade_date"] and row["ts_code"]]


def normalize_daily_basic(df: pd.DataFrame) -> list[dict[str, Any]]:
    fields = [
        "close",
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
        "pe",
        "pe_ttm",
        "pb",
        "ps",
        "ps_ttm",
        "total_share",
        "float_share",
        "free_share",
        "total_mv",
        "circ_mv",
    ]
    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        row = {
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "ts_code": item.get("ts_code"),
        }
        row.update({field: clean_float(item.get(field)) for field in fields})
        rows.append(row)
    return [row for row in rows if row["trade_date"] and row["ts_code"]]


def normalize_index_daily(df: pd.DataFrame) -> list[dict[str, Any]]:
    fields = ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"]
    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        row = {
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "ts_code": item.get("ts_code"),
        }
        row.update({field: clean_float(item.get(field)) for field in fields})
        rows.append(row)
    return [row for row in rows if row["trade_date"] and row["ts_code"]]


def normalize_stock_st(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = [
        {
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "ts_code": item.get("ts_code"),
            "name": item.get("name"),
            "st_type": item.get("st_type") or item.get("type"),
            "st_type_name": item.get("st_type_name") or item.get("type_name"),
        }
        for item in df.to_dict("records")
    ]
    return [row for row in rows if row["trade_date"] and row["ts_code"]]


def normalize_stock_suspend(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = [
        {
            "trade_date": parse_tushare_date(
                item.get("trade_date") or item.get("suspend_date")
            ),
            "ts_code": item.get("ts_code"),
            "suspend_type": item.get("suspend_type") or "S",
            "suspend_timing": item.get("suspend_timing"),
        }
        for item in df.to_dict("records")
    ]
    return [
        row
        for row in rows
        if row["trade_date"] and row["ts_code"] and row["suspend_type"]
    ]


def normalize_stock_limit(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = [
        {
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "ts_code": item.get("ts_code"),
            "pre_close": clean_float(item.get("pre_close")),
            "up_limit": clean_float(item.get("up_limit")),
            "down_limit": clean_float(item.get("down_limit")),
            "asset_type": item.get("asset_type"),
            "exchange": item.get("exchange"),
        }
        for item in df.to_dict("records")
    ]
    return [row for row in rows if row["trade_date"] and row["ts_code"]]


def normalize_sectors(df: pd.DataFrame, source: str = "SW") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in df.to_dict("records"):
        source_code = item.get("index_code") or item.get("industry_code") or item.get("ts_code")
        name = item.get("industry_name") or item.get("name")
        rows.append(
            {
                "source": source,
                "source_code": source_code,
                "name": name,
                "level": item.get("level") or item.get("industry_level"),
                "parent_code": item.get("parent_code"),
                "is_active": True,
            }
        )
    return [row for row in rows if row["source_code"] and row["name"]]


def normalize_sector_members(
    df: pd.DataFrame,
    sector_code_to_id: dict[str, int],
    sector_level: str = "L1",
    stock_list_dates: dict[str, date] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    level_code_column = f"{sector_level.lower()}_code"
    for item in df.to_dict("records"):
        sector_code = (
            item.get(level_code_column) or item.get("index_code") or item.get("industry_code")
        )
        ts_code = item.get("con_code") or item.get("ts_code")
        valid_from = parse_tushare_date(item.get("in_date"))
        if valid_from is None:
            logger.warning(
                "sector member PIT_INVALID missing in_date sector_code={} ts_code={}",
                sector_code,
                ts_code,
            )
            continue
        valid_to = parse_tushare_date(item.get("out_date"))
        sector_id = sector_code_to_id.get(str(sector_code))
        rows.append(
            {
                "sector_id": sector_id,
                "ts_code": ts_code,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "is_latest": valid_to is None,
            }
        )
    return [row for row in rows if row["sector_id"] and row["ts_code"]]


def current_sector_members_missing_in_date(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    missing: list[str] = []
    for item in df.to_dict("records"):
        if str(item.get("is_new", "")).upper() != "Y":
            continue
        if parse_tushare_date(item.get("in_date")) is not None:
            continue
        code = item.get("con_code") or item.get("ts_code") or "UNKNOWN"
        missing.append(str(code))
    return sorted(set(missing))


def normalize_themes(df: pd.DataFrame, seen_date: date) -> list[dict[str, Any]]:
    rows = [
        {
            "theme_code": item.get("ts_code"),
            "source": "THS",
            "name": item.get("name"),
            "theme_type": "CONCEPT",
            "exchange": item.get("exchange"),
            "constituent_count": int(item["count"]) if not pd.isna(item.get("count")) else None,
            "list_date": parse_tushare_date(item.get("list_date")),
            "is_active": True,
            "first_seen_date": seen_date,
            "last_seen_date": seen_date,
        }
        for item in df.to_dict("records")
    ]
    return [row for row in rows if row["theme_code"] and row["name"]]


def normalize_theme_members(df: pd.DataFrame, snapshot_date: date) -> list[dict[str, Any]]:
    source = df
    has_valid_flags = False
    if "is_new" in df.columns:
        flags = df["is_new"].astype("string").str.strip().str.upper()
        has_valid_flags = bool(flags.isin(["Y", "N"]).any())
        if has_valid_flags:
            source = df[flags == "Y"]
    rows = [
        {
            "snapshot_date": snapshot_date,
            "theme_code": item.get("ts_code"),
            "ts_code": item.get("con_code"),
            "stock_name": item.get("con_name"),
            "is_new": True if has_valid_flags else None,
            "source": "THS",
        }
        for item in source.to_dict("records")
    ]
    return [row for row in rows if row["theme_code"] and row["ts_code"]]


def normalize_theme_daily(df: pd.DataFrame) -> list[dict[str, Any]]:
    fields = [
        "open", "high", "low", "close", "pre_close", "avg_price", "change",
        "pct_change", "vol", "turnover_rate", "total_mv",
    ]
    rows = []
    for item in df.to_dict("records"):
        row = {
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "theme_code": item.get("ts_code"),
        }
        row.update({field: clean_float(item.get(field)) for field in fields})
        rows.append(row)
    return [row for row in rows if row["trade_date"] and row["theme_code"]]


def normalize_theme_moneyflow(df: pd.DataFrame) -> list[dict[str, Any]]:
    mapping = {
        "name": "name", "lead_stock": "lead_stock", "close_price": "close_price",
        "pct_change": "pct_change", "industry_index": "theme_index",
        "company_num": "company_num", "pct_change_stock": "lead_stock_pct_change",
        "net_buy_amount": "net_buy_amount", "net_sell_amount": "net_sell_amount",
        "net_amount": "net_amount",
    }
    rows = []
    for item in df.to_dict("records"):
        row = {
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "theme_code": item.get("ts_code"),
        }
        for source, target in mapping.items():
            value = item.get(source)
            row[target] = value if target in {"name", "lead_stock"} else clean_float(value)
        rows.append(row)
    return [row for row in rows if row["trade_date"] and row["theme_code"]]


def normalize_theme_limit(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for item in df.to_dict("records"):
        rows.append({
            "trade_date": parse_tushare_date(item.get("trade_date")),
            "theme_code": item.get("ts_code"),
            "name": item.get("name"),
            "days": int(item["days"]) if not pd.isna(item.get("days")) else None,
            "up_stat": item.get("up_stat"),
            "cons_nums": int(item["cons_nums"]) if not pd.isna(item.get("cons_nums")) else None,
            "up_nums": int(item["up_nums"]) if not pd.isna(item.get("up_nums")) else None,
            "pct_chg": clean_float(item.get("pct_chg")),
            "hot_rank": int(item["rank"]) if not pd.isna(item.get("rank")) else None,
        })
    return [row for row in rows if row["trade_date"] and row["theme_code"]]
