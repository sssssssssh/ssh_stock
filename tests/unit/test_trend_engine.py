from datetime import date

import app.services.trend.engine as trend_engine
import pandas as pd
import pytest
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


@pytest.mark.parametrize("previous_state", ["S1", "S2"])
@pytest.mark.parametrize("raw_state", ["S4", "S5"])
def test_fast_transition_from_early_state_is_limited_to_s3(
    previous_state: str,
    raw_state: str,
) -> None:
    state, reasons, fast_transition = trend_engine._apply_transition(
        raw_state,
        ["RAW_TREND"],
        previous_state,
        5,
        TrendConfig(),
    )

    assert state == "S3"
    assert fast_transition is True
    assert reasons == ["RAW_TREND", "FAST_TRANSITION_LIMITED_TO_S3"]


def test_fast_transition_progresses_s2_to_s3_to_s4_with_correct_day_count(
    monkeypatch,
) -> None:
    dates = [date(2026, 8, day) for day in (26, 27, 28)]
    factors = pd.DataFrame([_base_factor(current, "000004.SZ") for current in dates])
    previous = pd.DataFrame(
        [
            {
                "trade_date": date(2026, 8, 25),
                "ts_code": "000004.SZ",
                "state": "S2",
                "state_day_count": 8,
            }
        ]
    )
    monkeypatch.setattr(
        trend_engine,
        "_raw_state",
        lambda row, config: ("S4", ["RAW_TREND"]),
    )

    states = calculate_stock_states(
        factors=factors,
        market=pd.DataFrame(),
        sector_members=pd.DataFrame(),
        sector_factors=pd.DataFrame(),
        previous_states=previous,
        start=dates[0],
        end=dates[-1],
        config=TrendConfig(),
    )

    assert states["previous_state"].tolist() == ["S2", "S3", "S4"]
    assert states["state"].tolist() == ["S3", "S4", "S4"]
    assert states["state_day_count"].tolist() == [1, 1, 2]
    assert states["is_new_state"].tolist() == [True, True, False]
    assert states["fast_transition"].tolist() == [True, False, False]


def test_calculate_stock_states_keeps_one_row_with_historical_sector_memberships() -> None:
    target = date(2026, 8, 26)
    factor = _base_factor(target, "000007.SZ")
    sector_members = pd.DataFrame(
        [
            {
                "sector_id": 1,
                "ts_code": "000007.SZ",
                "valid_from": date(2025, 1, 1),
                "valid_to": date(2025, 12, 31),
                "is_latest": False,
            },
            {
                "sector_id": 2,
                "ts_code": "000007.SZ",
                "valid_from": date(2026, 1, 1),
                "valid_to": None,
                "is_latest": True,
            },
            {
                "sector_id": 3,
                "ts_code": "000007.SZ",
                "valid_from": date(2027, 1, 1),
                "valid_to": None,
                "is_latest": False,
            },
        ]
    )
    sector_factors = pd.DataFrame(
        [
            {
                "trade_date": target,
                "sector_id": 2,
                "heat_score": 88.0,
                "heat_momentum3": 6.0,
            }
        ]
    )

    states = calculate_stock_states(
        factors=pd.DataFrame([factor]),
        market=pd.DataFrame(),
        sector_members=sector_members,
        sector_factors=sector_factors,
        previous_states=pd.DataFrame(),
        start=target,
        end=target,
        config=TrendConfig(),
    )

    assert len(states) == 1
    assert states.iloc[0]["ts_code"] == "000007.SZ"
    assert states.iloc[0]["primary_sector_id"] == 2
    assert states.iloc[0]["sector_heat"] == 88.0
