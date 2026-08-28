import pandas as pd
from app.services.quality.raw_checks import check_raw_daily


def test_check_raw_daily_passes_valid_frame() -> None:
    df = pd.DataFrame(
        [
            {
                "trade_date": "20260825",
                "ts_code": "000001.SZ",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "vol": 100,
                "amount": 1000,
            }
        ]
    )

    assert check_raw_daily(df, min_rows=1) == []


def test_check_raw_daily_catches_invalid_ohlc_and_duplicates() -> None:
    df = pd.DataFrame(
        [
            {
                "trade_date": "20260825",
                "ts_code": "000001.SZ",
                "open": 10,
                "high": 9,
                "low": 11,
                "close": 10.5,
                "vol": 100,
                "amount": 1000,
            },
            {
                "trade_date": "20260825",
                "ts_code": "000001.SZ",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "vol": -1,
                "amount": 1000,
            },
        ]
    )

    codes = {issue.code for issue in check_raw_daily(df, min_rows=1)}

    assert "DAILY_DUPLICATED_PK" in codes
    assert "DAILY_INVALID_OHLC" in codes
    assert "DAILY_NEGATIVE_VOLUME" in codes

