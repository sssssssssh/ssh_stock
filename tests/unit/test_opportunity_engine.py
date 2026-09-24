from datetime import date, timedelta

import pandas as pd
from app.services.opportunity.engine import OpportunityConfig, calculate_opportunities


def _factors(dates: list[date], code: str = "000001.SZ") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": current,
                "ts_code": code,
                "eligible": True,
                "adj_close": 10,
                "ma20": 9.9,
                "ma60": 9.5,
                "return20": -0.05 + index / 1000,
                "ma20_slope5": -0.01 if index < len(dates) - 1 else 0.01,
                "atr20_pct": 0.02 if index == len(dates) - 1 else 0.05,
                "amount_ratio20": 1.2,
                "cross_above_ma20": index == len(dates) - 1,
                "cross_above_ma60": False,
                "higher_low": True,
                "higher_low_pct": 0.06,
                "drawdown_high60": -0.15,
                "rps20": 85,
                "rps60": 75,
                "rps120": 65,
                "rps20_delta5": 10,
                "rps60_delta5": 8,
            }
            for index, current in enumerate(dates)
        ]
    )


def _config() -> OpportunityConfig:
    return OpportunityConfig.from_dict(
        {
            "left_reversal": {
                "watch_score": 60,
                "strong_score": 75,
                "weights": {
                    "stabilization": 0.15,
                    "ma20_turn": 0.20,
                    "higher_low": 0.15,
                    "rps_recovery": 0.20,
                    "price_recovery": 0.15,
                    "volatility_contraction": 0.10,
                    "volume_structure": 0.05,
                },
            },
            "trend_pool": {
                "weights": {
                    "trend_score": 0.55,
                    "rps60": 0.20,
                    "rps120": 0.10,
                    "context": 0.10,
                    "market": 0.05,
                }
            },
        }
    )


def _calculate(factors: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    start, end = states["trade_date"].min(), states["trade_date"].max()
    return calculate_opportunities(
        factors=factors,
        states=states,
        market=pd.DataFrame([{"trade_date": end, "market_score": 70}]),
        sector_members=pd.DataFrame(),
        sector_factors=pd.DataFrame(),
        themes=pd.DataFrame(),
        theme_members=pd.DataFrame(),
        theme_factors=pd.DataFrame(),
        start=start,
        end=end,
        algo_version="v1.0",
        config=_config(),
    )


def test_left_reversal_high_score_and_new_crossing() -> None:
    dates = [date(2026, 5, 1) + timedelta(days=index) for index in range(70)]
    factors = _factors(dates)
    states = pd.DataFrame(
        [
            {
                "trade_date": dates[-2],
                "ts_code": "000001.SZ",
                "state": "S2",
                "previous_state": "S2",
                "state_day_count": 2,
                "is_new_state": False,
                "right_side_score": None,
                "trend_score": 30,
            },
            {
                "trade_date": dates[-1],
                "ts_code": "000001.SZ",
                "state": "S2",
                "previous_state": "S2",
                "state_day_count": 3,
                "is_new_state": False,
                "right_side_score": None,
                "trend_score": 35,
            },
        ]
    )

    result = _calculate(factors, states)

    assert result.iloc[-1]["left_reversal_score"] >= 75
    assert result.iloc[-1]["opportunity_stage"] == "LEFT_REVERSAL"
    assert bool(result.iloc[-1]["left_reversal_new"]) is True


def test_state_drives_right_and_trend_stages_and_position_risk() -> None:
    target = date(2026, 9, 1)
    factors = _factors([target])
    factors["adj_close"] = 12.5
    factors["ma20"] = 10.0
    factors["ma60"] = 9.0
    states = pd.DataFrame(
        [
            {
                "trade_date": target,
                "ts_code": "000001.SZ",
                "state": "S5",
                "previous_state": "S4",
                "state_day_count": 1,
                "is_new_state": True,
                "right_side_score": 90,
                "trend_score": 90,
            }
        ]
    )

    result = _calculate(factors, states).iloc[0]

    assert result["opportunity_stage"] == "STRONG_TREND"
    assert result["extension_risk"] == "EXTREME"
    assert result["left_reversal_score"] is None


def test_s3_reuses_right_side_and_does_not_enter_left_pool() -> None:
    target = date(2026, 9, 1)
    states = pd.DataFrame(
        [
            {
                "trade_date": target,
                "ts_code": "000001.SZ",
                "state": "S3",
                "previous_state": "S2",
                "state_day_count": 1,
                "is_new_state": True,
                "right_side_score": 92,
                "trend_score": 70,
            }
        ]
    )

    result = _calculate(_factors([target]), states).iloc[0]

    assert result["opportunity_stage"] == "RIGHT_SIDE_NEW"
    assert result["right_side_score"] == 92
    assert result["left_reversal_score"] is None
