from datetime import date

import pandas as pd
import pytest
from app.services.market import MarketConfig, calculate_market_daily


def test_calculate_market_daily_scores_and_regime() -> None:
    dates = pd.bdate_range("2025-01-01", periods=80).date
    factors = []
    daily = []
    for trade_idx, trade_date in enumerate(dates):
        for stock_idx in range(10):
            ts_code = f"0000{stock_idx:02d}.SZ"
            close = 10 + trade_idx * 0.2 + stock_idx * 0.1
            factors.append(
                {
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "adj_close": close,
                    "ma20": close - 1,
                    "ma60": close - 2,
                    "low20": close - 3,
                    "low60": close - 4,
                    "breakout20": stock_idx < 4,
                    "breakout60": stock_idx < 2,
                    "eligible": True,
                }
            )
            daily.append(
                {
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "close": close,
                    "pre_close": close - 0.2,
                    "pct_chg": 1.0 if stock_idx < 8 else -1.0,
                    "amount": 100000 + trade_idx * 1000,
                }
            )

    index_daily = pd.DataFrame(
        [
            {"trade_date": trade_date, "ts_code": "000300.SH", "close": 3000 + idx * 10}
            for idx, trade_date in enumerate(dates)
        ]
    )
    target = dates[-1]
    result = calculate_market_daily(
        factors=pd.DataFrame(factors),
        daily=pd.DataFrame(daily),
        index_daily=index_daily,
        start=target,
        end=target,
        config=MarketConfig(index_codes=("000300.SH",), index_weights=(1.0,)),
    )

    assert len(result.index) == 1
    row = result.iloc[0]
    assert row["trade_date"] == target
    assert row["breadth20"] == 1
    assert row["up_count"] == 8
    assert row["down_count"] == 2
    assert row["market_score"] >= 70
    assert row["regime"] == "RISK_ON"


def test_calculate_market_daily_handles_factor_only_input() -> None:
    target = date(2025, 1, 31)
    factors = pd.DataFrame(
        [
            {
                "trade_date": target,
                "ts_code": "000001.SZ",
                "adj_close": 12,
                "ma20": 10,
                "ma60": 9,
                "low20": 8,
                "low60": 7,
                "breakout20": True,
                "breakout60": True,
                "eligible": True,
            }
        ]
    )

    result = calculate_market_daily(
        factors=factors,
        daily=pd.DataFrame(),
        index_daily=pd.DataFrame(),
        start=target,
        end=target,
        config=MarketConfig(),
    )

    assert len(result.index) == 1
    assert result.iloc[0]["breadth_score"] == 100
    assert result.iloc[0]["market_score"] == pytest.approx(100)


def test_calculate_market_daily_handles_daily_only_startup_input() -> None:
    target = date(2025, 1, 31)
    daily = pd.DataFrame(
        [
            {
                "trade_date": target,
                "ts_code": "000001.SZ",
                "close": 10,
                "pre_close": 9,
                "pct_chg": 1,
                "amount": 100000,
            },
            {
                "trade_date": target,
                "ts_code": "000002.SZ",
                "close": 9,
                "pre_close": 10,
                "pct_chg": -1,
                "amount": 100000,
            },
        ]
    )

    result = calculate_market_daily(
        factors=pd.DataFrame(),
        daily=daily,
        index_daily=pd.DataFrame(),
        start=target,
        end=target,
        config=MarketConfig(),
    )

    row = result.iloc[0]
    assert row["up_count"] == 1
    assert row["down_count"] == 1
    assert row["ad_score"] == 50
    assert row["market_score"] == pytest.approx(50)
