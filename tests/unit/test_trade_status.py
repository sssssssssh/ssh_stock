from datetime import date

import pandas as pd
from app.services.trade_status import calculate_trade_status_rows


def _basic() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "list_date": date(2020, 1, 1),
                "delist_date": None,
            },
            {
                "ts_code": "000002.SZ",
                "list_date": date(2020, 1, 1),
                "delist_date": None,
            },
        ]
    )


def test_point_in_time_st_status_handles_future_st_and_historical_delisting() -> None:
    dates = [date(2023, 6, 1), date(2026, 6, 1)]
    result = calculate_trade_status_rows(
        trade_dates=dates,
        stock_basic=_basic(),
        daily=pd.DataFrame(
            [
                {"trade_date": current, "ts_code": code, "close": 10.0}
                for current in dates
                for code in ["000001.SZ", "000002.SZ"]
            ]
        ),
        stock_st=pd.DataFrame(
            [
                {
                    "trade_date": date(2023, 6, 1),
                    "ts_code": "000002.SZ",
                },
                {
                    "trade_date": date(2026, 6, 1),
                    "ts_code": "000001.SZ",
                },
            ]
        ),
        suspend_daily=pd.DataFrame(),
        stock_limit=pd.DataFrame(),
        exclude_st=True,
    ).set_index(["trade_date", "ts_code"])

    assert bool(result.loc[(date(2023, 6, 1), "000001.SZ"), "is_st"]) is False
    assert bool(result.loc[(date(2023, 6, 1), "000001.SZ"), "strategy_eligible"]) is True
    assert bool(result.loc[(date(2023, 6, 1), "000002.SZ"), "is_st"]) is True
    assert bool(result.loc[(date(2023, 6, 1), "000002.SZ"), "strategy_eligible"]) is False
    assert bool(result.loc[(date(2026, 6, 1), "000001.SZ"), "is_st"]) is True
    assert bool(result.loc[(date(2026, 6, 1), "000002.SZ"), "is_st"]) is False


def test_st_stock_remains_tradable_but_is_not_strategy_eligible() -> None:
    target = date(2026, 9, 15)
    result = calculate_trade_status_rows(
        trade_dates=[target],
        stock_basic=_basic().iloc[:1],
        daily=pd.DataFrame([{"trade_date": target, "ts_code": "000001.SZ", "close": 10}]),
        stock_st=pd.DataFrame([{"trade_date": target, "ts_code": "000001.SZ"}]),
        suspend_daily=pd.DataFrame(),
        stock_limit=pd.DataFrame(),
        exclude_st=True,
    ).iloc[0]

    assert bool(result["tradable"]) is True
    assert bool(result["strategy_eligible"]) is False
    assert result["status_reason"] == "ST"


def test_suspension_and_limit_close_flags_are_independent() -> None:
    target = date(2026, 9, 15)
    result = calculate_trade_status_rows(
        trade_dates=[target],
        stock_basic=_basic(),
        daily=pd.DataFrame(
            [
                {"trade_date": target, "ts_code": "000001.SZ", "close": 11.0},
                {"trade_date": target, "ts_code": "000002.SZ", "close": 9.0},
            ]
        ),
        stock_st=pd.DataFrame(),
        suspend_daily=pd.DataFrame(
            [
                {
                    "trade_date": target,
                    "ts_code": "000002.SZ",
                    "suspend_type": "S",
                }
            ]
        ),
        stock_limit=pd.DataFrame(
            [
                {
                    "trade_date": target,
                    "ts_code": "000001.SZ",
                    "up_limit": 11.0,
                    "down_limit": 9.0,
                },
                {
                    "trade_date": target,
                    "ts_code": "000002.SZ",
                    "up_limit": 11.0,
                    "down_limit": 9.0,
                },
            ]
        ),
        exclude_st=True,
    ).set_index("ts_code")

    assert bool(result.loc["000001.SZ", "is_limit_up_close"]) is True
    assert bool(result.loc["000001.SZ", "tradable"]) is True
    assert bool(result.loc["000002.SZ", "is_limit_down_close"]) is True
    assert bool(result.loc["000002.SZ", "is_suspended"]) is True
    assert bool(result.loc["000002.SZ", "tradable"]) is False


def test_pre_2000_st_status_is_unknown_not_fabricated() -> None:
    target = date(1999, 12, 31)
    basic = pd.DataFrame(
        [{"ts_code": "000001.SZ", "list_date": date(1991, 1, 1), "delist_date": None}]
    )

    result = calculate_trade_status_rows(
        trade_dates=[target],
        stock_basic=basic,
        daily=pd.DataFrame([{"trade_date": target, "ts_code": "000001.SZ", "close": 10}]),
        stock_st=pd.DataFrame(),
        suspend_daily=pd.DataFrame(),
        stock_limit=pd.DataFrame(),
        exclude_st=True,
    ).iloc[0]

    assert result["is_st"] is None
    assert bool(result["st_status_unknown"]) is True
    assert bool(result["strategy_eligible"]) is False


def test_historical_trade_status_recalculation_is_idempotent() -> None:
    dates = [date(2023, 6, 1), date(2023, 6, 2)]
    inputs = {
        "trade_dates": dates,
        "stock_basic": _basic().iloc[:1],
        "daily": pd.DataFrame(
            [
                {"trade_date": current, "ts_code": "000001.SZ", "close": 10.0}
                for current in dates
            ]
        ),
        "stock_st": pd.DataFrame(
            [{"trade_date": dates[0], "ts_code": "000001.SZ"}]
        ),
        "suspend_daily": pd.DataFrame(),
        "stock_limit": pd.DataFrame(),
        "exclude_st": True,
    }

    first = calculate_trade_status_rows(**inputs)
    second = calculate_trade_status_rows(**inputs)

    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 2
    assert not first.duplicated(["trade_date", "ts_code"]).any()
