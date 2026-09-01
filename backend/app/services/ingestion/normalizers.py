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
    stock_list_dates = stock_list_dates or {}
    for item in df.to_dict("records"):
        sector_code = (
            item.get(level_code_column) or item.get("index_code") or item.get("industry_code")
        )
        ts_code = item.get("con_code") or item.get("ts_code")
        valid_from = parse_tushare_date(item.get("in_date"))
        if valid_from is None and ts_code:
            valid_from = stock_list_dates.get(str(ts_code))
        if valid_from is None:
            logger.warning(
                "sector member missing in_date sector_code={} ts_code={}",
                sector_code,
                ts_code,
            )
            valid_from = date(1900, 1, 1)
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
