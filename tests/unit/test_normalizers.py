from datetime import date

import pandas as pd
from app.services.ingestion.normalizers import (
    current_sector_members_missing_in_date,
    normalize_adj_factor,
    normalize_sector_members,
    normalize_sectors,
    normalize_stock_basic,
    normalize_stock_daily,
    normalize_stock_limit,
    normalize_stock_st,
    normalize_stock_suspend,
    normalize_trade_calendar,
    parse_tushare_date,
)


def test_parse_tushare_date() -> None:
    assert parse_tushare_date("20260825") == date(2026, 8, 25)
    assert parse_tushare_date("") is None
    assert parse_tushare_date(None) is None


def test_normalize_stock_basic() -> None:
    df = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "market": "主板",
                "exchange": "SZSE",
                "industry": "银行",
                "list_status": "L",
                "list_date": "19910403",
                "delist_date": "",
                "is_hs": "S",
            }
        ]
    )

    rows = normalize_stock_basic(df)

    assert rows == [
        {
            "ts_code": "000001.SZ",
            "symbol": "000001",
            "name": "平安银行",
            "market": "主板",
            "exchange": "SZSE",
            "industry": "银行",
            "list_status": "L",
            "list_date": date(1991, 4, 3),
            "delist_date": None,
            "is_hs": "S",
        }
    ]


def test_normalize_trade_calendar() -> None:
    df = pd.DataFrame(
        [{"cal_date": "20260825", "is_open": 1, "pretrade_date": "20260824", "exchange": "SSE"}]
    )

    rows = normalize_trade_calendar(df)

    assert rows[0]["cal_date"] == date(2026, 8, 25)
    assert rows[0]["is_open"] is True
    assert rows[0]["pretrade_date"] == date(2026, 8, 24)


def test_normalize_stock_daily_and_adj_factor() -> None:
    daily = pd.DataFrame(
        [
            {
                "trade_date": "20260825",
                "ts_code": "000001.SZ",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "pre_close": 10,
                "change": 0.5,
                "pct_chg": 5,
                "vol": 100,
                "amount": 1000,
            }
        ]
    )
    adj = pd.DataFrame([{"trade_date": "20260825", "ts_code": "000001.SZ", "adj_factor": 1.23}])

    assert normalize_stock_daily(daily)[0]["close"] == 10.5
    assert normalize_adj_factor(adj)[0]["adj_factor"] == 1.23


def test_normalize_sectors_and_sw2021_members() -> None:
    sector_df = pd.DataFrame(
        [
            {
                "index_code": "801880.SI",
                "industry_name": "汽车",
                "level": "L1",
                "parent_code": "0",
            }
        ]
    )
    member_df = pd.DataFrame(
        [
            {
                "l1_code": "801880.SI",
                "l1_name": "汽车",
                "l2_code": "801881.SI",
                "l3_code": "858811.SI",
                "ts_code": "600679.SH",
                "in_date": "19931008",
                "out_date": None,
                "is_new": "Y",
            },
            {
                "l1_code": "801880.SI",
                "l1_name": "汽车",
                "ts_code": "600680.SH",
                "in_date": "19931008",
                "out_date": "20211231",
            }
        ]
    )

    sectors = normalize_sectors(sector_df, source="SW")
    members = normalize_sector_members(member_df, {"801880.SI": 1})

    assert sectors[0]["source_code"] == "801880.SI"
    assert sectors[0]["name"] == "汽车"
    assert members[0]["sector_id"] == 1
    assert members[0]["ts_code"] == "600679.SH"
    assert members[0]["valid_from"] == date(1993, 10, 8)
    assert members[0]["is_latest"] is True
    assert members[1]["valid_to"] == date(2021, 12, 31)
    assert members[1]["is_latest"] is False


def test_normalize_milestone9_trade_status_raw_rows() -> None:
    target = date(2026, 9, 15)

    st = normalize_stock_st(
        pd.DataFrame(
            [
                {
                    "trade_date": "20260915",
                    "ts_code": "000001.SZ",
                    "name": "*ST示例",
                    "type": "ST",
                    "type_name": "特别处理",
                }
            ]
        )
    )
    suspend = normalize_stock_suspend(
        pd.DataFrame(
            [
                {
                    "suspend_date": "20260915",
                    "ts_code": "000002.SZ",
                    "suspend_type": "S",
                    "suspend_timing": "全天",
                }
            ]
        )
    )
    limit_rows = normalize_stock_limit(
        pd.DataFrame(
            [
                {
                    "trade_date": "20260915",
                    "ts_code": "000001.SZ",
                    "pre_close": 10,
                    "up_limit": 11,
                    "down_limit": 9,
                }
            ]
        )
    )

    assert st[0]["trade_date"] == target
    assert st[0]["st_type"] == "ST"
    assert suspend[0]["suspend_type"] == "S"
    assert limit_rows[0]["up_limit"] == 11.0


def test_sector_members_never_invent_missing_effective_dates() -> None:
    frame = pd.DataFrame(
        [
            {
                "l1_code": "801010.SI",
                "con_code": "000001.SZ",
                "in_date": None,
                "is_new": "Y",
            },
            {
                "l1_code": "801010.SI",
                "con_code": "000002.SZ",
                "in_date": None,
                "is_new": "N",
            },
        ]
    )

    rows = normalize_sector_members(
        frame,
        {"801010.SI": 1},
        stock_list_dates={"000001.SZ": date(1991, 1, 1)},
    )

    assert rows == []
    assert current_sector_members_missing_in_date(frame) == ["000001.SZ"]
