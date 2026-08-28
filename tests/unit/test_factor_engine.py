import pandas as pd
import pytest
from app.services.factors import FactorConfig, calculate_stock_factors


def _fixture_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.bdate_range("2025-01-01", periods=270).date
    records = []
    adj_records = []
    slopes = {"000001.SZ": 0.20, "000002.SZ": 0.35, "000003.SZ": 0.10}
    for ts_code, slope in slopes.items():
        for idx, trade_date in enumerate(dates):
            close = 10 + slope * idx
            records.append(
                {
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "open": close - 0.1,
                    "high": close + 0.1,
                    "low": close - 0.2,
                    "close": close,
                    "vol": 1000,
                    "amount": 100000,
                }
            )
            adj_records.append(
                {
                    "trade_date": trade_date,
                    "ts_code": ts_code,
                    "adj_factor": 1.0,
                }
            )

    index_records = [
        {"trade_date": trade_date, "ts_code": "000300.SH", "close": 100 + 0.1 * idx}
        for idx, trade_date in enumerate(dates)
    ]
    stock_basic = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "name": "测试A", "list_status": "L"},
            {"ts_code": "000002.SZ", "name": "测试B", "list_status": "L"},
            {"ts_code": "000003.SZ", "name": "*ST测试", "list_status": "L"},
        ]
    )
    return (
        pd.DataFrame(records),
        pd.DataFrame(adj_records),
        stock_basic,
        pd.DataFrame(index_records),
    )


def test_calculate_stock_factors_core_columns() -> None:
    daily, adj_factor, stock_basic, index_daily = _fixture_data()
    target = daily["trade_date"].max()

    result = calculate_stock_factors(
        daily=daily,
        adj_factor=adj_factor,
        stock_basic=stock_basic,
        index_daily=index_daily,
        benchmark_code="000300.SH",
        start=target,
        end=target,
        config=FactorConfig(),
    )

    row = result[result["ts_code"] == "000001.SZ"].iloc[0]
    recent = daily[daily["ts_code"] == "000001.SZ"].tail(20)
    latest_close = daily[daily["ts_code"] == "000001.SZ"].iloc[-1]["close"]

    assert bool(row["eligible"]) is True
    assert row["adj_close"] == latest_close
    assert row["ma20"] == pytest.approx(recent["close"].mean())
    assert bool(row["breakout20"]) is True
    assert bool(row["breakout60"]) is True
    assert bool(row["higher_low"]) is True
    assert row["amount_ratio20"] == pytest.approx(1)
    assert row["atr20"] > 0
    assert 0 < row["trend_efficiency20"] <= 1


def test_rps_uses_only_eligible_universe() -> None:
    daily, adj_factor, stock_basic, index_daily = _fixture_data()
    target = daily["trade_date"].max()

    result = calculate_stock_factors(
        daily=daily,
        adj_factor=adj_factor,
        stock_basic=stock_basic,
        index_daily=index_daily,
        benchmark_code="000300.SH",
        start=target,
        end=target,
        config=FactorConfig(),
    )

    rps_by_code = result.set_index("ts_code")["rps20"].to_dict()
    eligible_by_code = result.set_index("ts_code")["eligible"].to_dict()

    assert rps_by_code["000002.SZ"] == 100
    assert rps_by_code["000001.SZ"] == 50
    assert pd.isna(rps_by_code["000003.SZ"])
    assert bool(eligible_by_code["000003.SZ"]) is False
    assert "ST" in result.set_index("ts_code").loc["000003.SZ", "exclusion_reason"]


def test_breakout_uses_previous_high_not_today_high() -> None:
    dates = pd.bdate_range("2025-01-01", periods=25).date
    daily = pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "ts_code": "000001.SZ",
                "open": 10,
                "high": 100 if idx == 24 else 11,
                "low": 9,
                "close": 12 if idx == 24 else 10,
                "vol": 1000,
                "amount": 100000,
            }
            for idx, trade_date in enumerate(dates)
        ]
    )
    adj_factor = pd.DataFrame([
        {"trade_date": trade_date, "ts_code": "000001.SZ", "adj_factor": 1.0}
        for trade_date in dates
    ])
    stock_basic = pd.DataFrame([{"ts_code": "000001.SZ", "name": "测试A", "list_status": "L"}])

    result = calculate_stock_factors(
        daily=daily,
        adj_factor=adj_factor,
        stock_basic=stock_basic,
        index_daily=None,
        benchmark_code="000300.SH",
        start=dates[-1],
        end=dates[-1],
        config=FactorConfig(min_listed_trading_days=1),
    )

    assert result.iloc[0]["prev_high20"] == 11
    assert bool(result.iloc[0]["breakout20"]) is True
