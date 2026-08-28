from datetime import date

import pandas as pd
from app.services.trend import TrendConfig, calculate_stock_states, generate_strategy_signals


def _base_factor(trade_date: date, ts_code: str) -> dict:
    return {
        "trade_date": trade_date,
        "ts_code": ts_code,
        "adj_close": 12.0,
        "ma20": 10.0,
        "ma60": 9.0,
        "ma120": 8.0,
        "return20": 0.20,
        "ma20_slope5": 0.004,
        "ma60_slope10": 0.002,
        "atr20_pct": 0.03,
        "amount_ratio20": 1.6,
        "prev_high20": 11.0,
        "breakout20": True,
        "breakout60": False,
        "cross_above_ma20": False,
        "cross_above_ma60": False,
        "higher_low": True,
        "higher_low_pct": 0.08,
        "drawdown_high60": -0.04,
        "max_drawdown60": -0.10,
        "trend_efficiency20": 0.75,
        "rps20": 80.0,
        "rps60": 65.0,
        "rps120": 60.0,
        "rps20_delta5": 20.0,
        "rps60_delta5": 15.0,
        "eligible": True,
    }


def test_calculate_stock_states_identifies_new_right_side_signal() -> None:
    target = date(2026, 8, 26)
    factors = pd.DataFrame([_base_factor(target, "000001.SZ")])
    previous = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 8, 25),
                "ts_code": "000001.SZ",
                "state": "S2",
                "state_day_count": 7,
            }
        ]
    )

    states = calculate_stock_states(
        factors=factors,
        market=pd.DataFrame([{"trade_date": target, "market_score": 70.0}]),
        sector_members=pd.DataFrame(),
        sector_factors=pd.DataFrame(),
        previous_states=previous,
        start=target,
        end=target,
        config=TrendConfig(),
    )
    signals = generate_strategy_signals(states, TrendConfig())

    row = states.iloc[0]
    assert row["state"] == "S3"
    assert row["previous_state"] == "S2"
    assert bool(row["is_new_state"]) is True
    assert "RIGHT_SIDE_NEW" in set(signals["signal_type"])


def test_calculate_stock_states_identifies_main_up() -> None:
    target = date(2026, 8, 26)
    factor = _base_factor(target, "000002.SZ")
    factor.update({"rps20": 95.0, "rps60": 96.0, "rps120": 92.0})

    states = calculate_stock_states(
        factors=pd.DataFrame([factor]),
        market=pd.DataFrame(),
        sector_members=pd.DataFrame(),
        sector_factors=pd.DataFrame(),
        previous_states=pd.DataFrame(),
        start=target,
        end=target,
        config=TrendConfig(),
    )
    signals = generate_strategy_signals(states, TrendConfig())

    assert states.iloc[0]["state"] == "S5"
    assert "MAIN_UP_ENTER" in set(signals["signal_type"])
    assert "LEADER_BREAKOUT" in set(signals["signal_type"])


def test_fast_transition_from_s0_is_limited_to_s3() -> None:
    target = date(2026, 8, 26)
    factor = _base_factor(target, "000003.SZ")
    factor.update({"rps20": 96.0, "rps60": 96.0, "rps120": 92.0})
    previous = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 8, 25),
                "ts_code": "000003.SZ",
                "state": "S0",
                "state_day_count": 10,
            }
        ]
    )

    states = calculate_stock_states(
        factors=pd.DataFrame([factor]),
        market=pd.DataFrame(),
        sector_members=pd.DataFrame(),
        sector_factors=pd.DataFrame(),
        previous_states=previous,
        start=target,
        end=target,
        config=TrendConfig(),
    )

    row = states.iloc[0]
    assert row["state"] == "S3"
    assert bool(row["fast_transition"]) is True
    assert "FAST_TRANSITION_LIMITED_TO_S3" in row["reason_codes"]
