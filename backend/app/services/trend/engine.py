from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

ALLOWED_TRANSITIONS = {
    "S0": {"S0", "S1", "S2", "S3"},
    "S1": {"S0", "S1", "S2", "S3"},
    "S2": {"S0", "S1", "S2", "S3"},
    "S3": {"S2", "S3", "S4", "S6"},
    "S4": {"S3", "S4", "S5", "S6"},
    "S5": {"S4", "S5", "S6"},
    "S6": {"S0", "S1", "S2", "S3", "S4", "S6"},
}


@dataclass(frozen=True)
class TrendConfig:
    algo_version: str = "v1.1"
    right_side_min_score: float = 70
    right_side_min_rps20: float = 70
    volume_ratio_confirm: float = 1.20
    base_ma60_distance_pct: float = 0.10
    s3_max_days: int = 5
    s4_min_score: float = 70
    s4_min_rps60: float = 70
    s5_min_score: float = 85
    s5_min_rps60: float = 90
    s5_min_rps120: float = 80
    s5_max_drawdown60: float = -0.25

    @classmethod
    def from_strategy(cls, strategy: dict[str, Any], algo_version: str = "v1.1") -> "TrendConfig":
        right_side = strategy.get("right_side", {})
        trend = strategy.get("trend", {})
        return cls(
            algo_version=algo_version,
            right_side_min_score=float(right_side.get("min_score", cls.right_side_min_score)),
            right_side_min_rps20=float(right_side.get("min_rps20", cls.right_side_min_rps20)),
            volume_ratio_confirm=float(
                right_side.get("volume_ratio_confirm", cls.volume_ratio_confirm)
            ),
            base_ma60_distance_pct=float(
                right_side.get("base_ma60_distance_pct", cls.base_ma60_distance_pct)
            ),
            s3_max_days=int(right_side.get("s3_max_days", cls.s3_max_days)),
            s4_min_score=float(trend.get("s4_min_score", cls.s4_min_score)),
            s4_min_rps60=float(trend.get("s4_min_rps60", cls.s4_min_rps60)),
            s5_min_score=float(trend.get("s5_min_score", cls.s5_min_score)),
            s5_min_rps60=float(trend.get("s5_min_rps60", cls.s5_min_rps60)),
            s5_min_rps120=float(trend.get("s5_min_rps120", cls.s5_min_rps120)),
            s5_max_drawdown60=float(trend.get("s5_max_drawdown60", cls.s5_max_drawdown60)),
        )


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _clip_score(series: pd.Series) -> pd.Series:
    return _num(series).clip(0, 100)


def _linear_score(value: float | None, points: list[tuple[float, float]]) -> float | None:
    if value is None or pd.isna(value):
        return None
    ordered = sorted(points)
    if value <= ordered[0][0]:
        return ordered[0][1]
    if value >= ordered[-1][0]:
        return ordered[-1][1]
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left[0] <= value <= right[0]:
            scale = (value - left[0]) / (right[0] - left[0])
            return float(left[1] + scale * (right[1] - left[1]))
    return None


def _prepare_factors(factors: pd.DataFrame) -> pd.DataFrame:
    df = factors.copy()
    if df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    numeric_columns = [
        "adj_close",
        "ma20",
        "ma60",
        "ma120",
        "return20",
        "ma20_slope5",
        "ma60_slope10",
        "atr20_pct",
        "amount_ratio20",
        "prev_high20",
        "drawdown_high60",
        "max_drawdown60",
        "trend_efficiency20",
        "rps20",
        "rps60",
        "rps120",
        "rps20_delta5",
        "rps60_delta5",
    ]
    for column in numeric_columns:
        if column in df.columns:
            df[column] = _num(df[column])
        else:
            df[column] = np.nan

    bool_columns = [
        "breakout20",
        "breakout60",
        "cross_above_ma20",
        "cross_above_ma60",
        "higher_low",
        "eligible",
    ]
    for column in bool_columns:
        if column not in df.columns:
            df[column] = False
        df[column] = df[column].fillna(False).astype(bool)

    group = df.groupby("ts_code", group_keys=False)
    df["adj_close_lag5"] = group["adj_close"].shift(5)
    df["ma20_lag5"] = group["ma20"].shift(5)
    df["ma60_lag5"] = group["ma60"].shift(5)
    df["ma20_slope5_lag5"] = group["ma20_slope5"].shift(5)
    df["below_ma20_2d"] = (df["adj_close"] < df["ma20"]) & (
        group["adj_close"].shift(1) < group["ma20"].shift(1)
    )
    df["atr20_pct_q40"] = group["atr20_pct"].transform(
        lambda s: s.rolling(120, min_periods=20).quantile(0.40)
    )
    return df


def _breakout_score(row: pd.Series) -> float:
    close = row["adj_close"]
    prev_high20 = row["prev_high20"]
    if row["breakout60"]:
        return 100
    if row["breakout20"]:
        return 85
    if not pd.isna(close) and not pd.isna(prev_high20):
        ratio = close / prev_high20 if prev_high20 else np.nan
        if ratio >= 0.98:
            return 60
        if ratio >= 0.95:
            return 30
    return 0


def _ma20_turn_score(row: pd.Series) -> float:
    slope = row["ma20_slope5"]
    previous = row["ma20_slope5_lag5"]
    if pd.isna(slope):
        return 0
    if not pd.isna(previous) and previous < 0 <= slope:
        return 100
    if slope > 0.002:
        return 80
    if abs(slope) <= 0.002 and (pd.isna(previous) or slope > previous):
        return 50
    if slope < -0.002:
        return 0
    return 30


def _ma_recovery_score(row: pd.Series) -> float:
    close = row["adj_close"]
    if row["cross_above_ma60"]:
        return 100
    if not pd.isna(close) and not pd.isna(row["ma60"]) and close > row["ma60"]:
        if not pd.isna(row["adj_close_lag5"]) and not pd.isna(row["ma60_lag5"]):
            if row["adj_close_lag5"] <= row["ma60_lag5"]:
                return 85
        return 70
    if (
        not pd.isna(close)
        and not pd.isna(row["ma20"])
        and close > row["ma20"]
        and row["ma20_slope5"] > 0
    ):
        return 60
    return 0


def _higher_low_score(row: pd.Series) -> float:
    pct = row.get("higher_low_pct")
    if row["higher_low"] and not pd.isna(pct) and pct >= 0.05:
        return 100
    if row["higher_low"]:
        return 75
    if pd.isna(pct) or pct >= -0.02:
        return 40
    return 0


def _volatility_structure_score(row: pd.Series) -> float:
    atr = row["atr20_pct"]
    q40 = row["atr20_pct_q40"]
    if pd.isna(atr) or pd.isna(q40):
        return 50
    if atr <= q40 and row["breakout20"]:
        return 85
    if atr <= q40:
        return 70
    if row["breakout20"]:
        return 60
    return 50


def _calculate_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["breakout_score"] = df.apply(_breakout_score, axis=1)
    df["ma20_turn_score"] = df.apply(_ma20_turn_score, axis=1)
    df["ma_recovery_score"] = df.apply(_ma_recovery_score, axis=1)
    df["volume_confirmation_score"] = df["amount_ratio20"].map(
        lambda value: _linear_score(
            value,
            [(0.0, 10), (0.8, 10), (1.0, 40), (1.2, 60), (1.5, 80), (2.0, 100)],
        )
    )
    df["higher_low_score"] = df.apply(_higher_low_score, axis=1)
    df["volatility_structure_score"] = df.apply(_volatility_structure_score, axis=1)

    df["rps20_delta5_score"] = (
        df["rps20_delta5"].groupby(df["trade_date"]).rank(pct=True, method="average") * 100
    )
    df["rps60_delta5_score"] = (
        df["rps60_delta5"].groupby(df["trade_date"]).rank(pct=True, method="average") * 100
    )
    df["rps_acceleration_score"] = (
        0.5 * _clip_score(df["rps20"])
        + 0.3 * _clip_score(df["rps20_delta5_score"])
        + 0.2 * _clip_score(df["rps60_delta5_score"])
    )

    right_side_parts = df[
        [
            "breakout_score",
            "ma20_turn_score",
            "ma_recovery_score",
            "rps_acceleration_score",
            "volume_confirmation_score",
            "higher_low_score",
            "volatility_structure_score",
        ]
    ]
    right_side_weights = pd.Series(
        {
            "breakout_score": 0.20,
            "ma20_turn_score": 0.15,
            "ma_recovery_score": 0.15,
            "rps_acceleration_score": 0.20,
            "volume_confirmation_score": 0.10,
            "higher_low_score": 0.10,
            "volatility_structure_score": 0.10,
        }
    )
    df["right_side_score"] = _weighted_average(right_side_parts, right_side_weights)

    df["ma_structure_score"] = (
        (df["adj_close"] > df["ma20"]).astype(float) * 25
        + (df["ma20"] > df["ma60"]).astype(float) * 25
        + (df["ma60"] > df["ma120"]).astype(float) * 25
        + ((df["ma20_slope5"] > 0) & (df["ma60_slope10"] >= 0)).astype(float) * 25
    )
    df["ma20_slope_score"] = (
        df["ma20_slope5"].groupby(df["trade_date"]).rank(pct=True, method="average") * 100
    )
    df["ma60_slope_score"] = (
        df["ma60_slope10"].groupby(df["trade_date"]).rank(pct=True, method="average") * 100
    )
    df["slope_score"] = 0.6 * df["ma20_slope_score"] + 0.4 * df["ma60_slope_score"]
    df["trend_efficiency_score"] = _clip_score(df["trend_efficiency20"] * 100)
    df["drawdown_quality_score"] = (
        df["drawdown_high60"].groupby(df["trade_date"]).rank(pct=True, method="average") * 100
    )

    trend_parts = df[
        [
            "rps20",
            "rps60",
            "rps120",
            "ma_structure_score",
            "slope_score",
            "trend_efficiency_score",
            "drawdown_quality_score",
        ]
    ]
    trend_weights = pd.Series(
        {
            "rps20": 0.15,
            "rps60": 0.25,
            "rps120": 0.15,
            "ma_structure_score": 0.15,
            "slope_score": 0.10,
            "trend_efficiency_score": 0.10,
            "drawdown_quality_score": 0.10,
        }
    )
    df["trend_score"] = _weighted_average(trend_parts, trend_weights)
    return df


def _weighted_average(parts: pd.DataFrame, weights: pd.Series) -> pd.Series:
    weighted = parts.mul(weights, axis=1)
    present_weight = parts.notna().mul(weights, axis=1).sum(axis=1)
    return weighted.sum(axis=1, min_count=1) / present_weight.replace(0, np.nan)


def _raw_state(row: pd.Series, config: TrendConfig) -> tuple[str, list[str]]:
    reasons: list[str] = []
    close = row["adj_close"]
    ma20 = row["ma20"]
    ma60 = row["ma60"]
    ma120 = row["ma120"]

    if not row["eligible"]:
        return "S0", ["NOT_ELIGIBLE"]

    is_s5 = (
        row["trend_score"] >= config.s5_min_score
        and row["rps60"] >= config.s5_min_rps60
        and row["rps120"] >= config.s5_min_rps120
        and close > ma20
        and ma20 > ma60
        and ma60 > ma120
        and (pd.isna(row["max_drawdown60"]) or row["max_drawdown60"] >= config.s5_max_drawdown60)
    )
    if is_s5:
        return "S5", ["TREND_SCORE_STRONG", "RPS_LEADER", "MA_MULTI_BULL"]

    is_s4 = (
        close > ma20
        and ma20 > ma60
        and row["ma20_slope5"] > 0
        and row["ma60_slope10"] >= 0
        and row["rps60"] >= config.s4_min_rps60
        and row["trend_score"] >= config.s4_min_score
    )
    if is_s4:
        return "S4", ["TREND_SCORE_OK", "RPS60_HIGH", "MA20_MA60_BULL"]

    is_s3 = (
        row["right_side_score"] >= config.right_side_min_score
        and close > ma20
        and row["ma20_slope5"] > 0
        and (row["breakout20"] or row["cross_above_ma60"])
        and row["rps20"] >= config.right_side_min_rps20
    )
    if is_s3:
        return "S3", ["RIGHT_SIDE_SCORE_OK", "BREAKOUT_OR_MA60_CROSS", "RPS20_HIGH"]

    decay_reasons = []
    if row["below_ma20_2d"]:
        decay_reasons.append("BELOW_MA20_2D")
    if row["ma20_slope5"] < 0:
        decay_reasons.append("MA20_SLOPE_DOWN")
    if row["rps20"] < 50:
        decay_reasons.append("RPS20_WEAK")
    if close < ma60:
        decay_reasons.append("CLOSE_BELOW_MA60")
    if len(decay_reasons) >= 2:
        return "S6", decay_reasons

    down_votes = [
        close < ma60,
        ma20 < ma60,
        row["ma20_slope5"] < 0,
        row["rps60"] < 50,
    ]
    if sum(bool(vote) for vote in down_votes) >= 3:
        return "S0", ["DOWN_TREND"]

    if row["rps20_delta5"] > 0 or row["cross_above_ma20"]:
        reasons.append("DECELERATING_OR_RECOVERING")
        return "S1", reasons

    if not pd.isna(close) and not pd.isna(ma60):
        distance = abs(close / ma60 - 1) if ma60 else np.nan
        if (
            not pd.isna(distance)
            and distance <= config.base_ma60_distance_pct
            and (row["higher_low"] or row["ma20_slope5"] >= -0.002)
        ):
            return "S2", ["BASE_NEAR_MA60"]

    return "S2", ["DEFAULT_BASE"]


def _apply_transition(
    raw_state: str,
    raw_reasons: list[str],
    previous_state: str | None,
    previous_count: int | None,
    config: TrendConfig,
) -> tuple[str, list[str], bool]:
    if previous_state is None:
        return raw_state, raw_reasons, False

    fast_transition = False
    if previous_state in {"S0", "S1", "S2"} and raw_state in {"S4", "S5"}:
        return "S3", raw_reasons + ["FAST_TRANSITION_LIMITED_TO_S3"], True

    if previous_state == "S3" and raw_state == "S3" and (previous_count or 0) >= config.s3_max_days:
        return "S2", raw_reasons + ["S3_EXPIRED"], False

    if raw_state in ALLOWED_TRANSITIONS.get(previous_state, set()):
        return raw_state, raw_reasons, fast_transition

    if previous_state in {"S4", "S5"} and raw_state in {"S0", "S1", "S2"}:
        return "S6", raw_reasons + ["TREND_DECAY_BY_TRANSITION"], False

    return previous_state, raw_reasons + ["TRANSITION_BLOCKED"], False


def _momentum_score(value: float | None) -> float | None:
    return _linear_score(value, [(-20, 0), (0, 50), (20, 100)])


def _opportunity_score(row: pd.Series) -> float | None:
    stock_score = row["right_side_score"] if row["state"] == "S3" else row["trend_score"]
    parts = {
        "stock": stock_score,
        "sector": row.get("sector_heat"),
        "sector_momentum": _momentum_score(row.get("sector_heat_momentum3")),
        "market": row.get("market_score"),
    }
    weights = {"stock": 0.45, "sector": 0.35, "sector_momentum": 0.10, "market": 0.10}
    present = {
        key: value for key, value in parts.items() if value is not None and not pd.isna(value)
    }
    if not present:
        return None
    numerator = sum(present[key] * weights[key] for key in present)
    denominator = sum(weights[key] for key in present)
    return float(numerator / denominator)


def _merge_context(
    df: pd.DataFrame,
    market: pd.DataFrame,
    sector_members: pd.DataFrame,
    sector_factors: pd.DataFrame,
) -> pd.DataFrame:
    result = df.copy()
    if not market.empty:
        market_df = market.copy()
        market_df["trade_date"] = pd.to_datetime(market_df["trade_date"]).dt.date
        result = result.merge(
            market_df[["trade_date", "market_score"]], on="trade_date", how="left"
        )
    else:
        result["market_score"] = np.nan

    if not sector_members.empty:
        primary_sector = _primary_sector_context(result, sector_members)
        result = result.merge(primary_sector, on=["trade_date", "ts_code"], how="left")
    else:
        result["primary_sector_id"] = np.nan

    if not sector_factors.empty:
        sector_df = sector_factors.copy()
        sector_df["trade_date"] = pd.to_datetime(sector_df["trade_date"]).dt.date
        result = result.merge(
            sector_df[["trade_date", "sector_id", "heat_score", "heat_momentum3"]],
            left_on=["trade_date", "primary_sector_id"],
            right_on=["trade_date", "sector_id"],
            how="left",
        )
        result = result.rename(
            columns={"heat_score": "sector_heat", "heat_momentum3": "sector_heat_momentum3"}
        )
    else:
        result["sector_heat"] = np.nan
        result["sector_heat_momentum3"] = np.nan
    return result


def _primary_sector_context(df: pd.DataFrame, sector_members: pd.DataFrame) -> pd.DataFrame:
    keys = df[["trade_date", "ts_code"]].drop_duplicates().copy()
    members = sector_members.copy()
    members["valid_from"] = pd.to_datetime(members["valid_from"]).dt.date
    members["valid_to"] = pd.to_datetime(members["valid_to"]).dt.date
    if "is_latest" not in members.columns:
        members["is_latest"] = False

    merged = keys.merge(members, on="ts_code", how="left")
    valid_to = merged["valid_to"].fillna(date(9999, 12, 31))
    valid_member = (merged["trade_date"] >= merged["valid_from"]) & (
        merged["trade_date"] <= valid_to
    )
    valid = merged[valid_member].copy()
    if valid.empty:
        keys["primary_sector_id"] = np.nan
        return keys

    valid = valid.sort_values(
        ["trade_date", "ts_code", "is_latest", "valid_from", "sector_id"],
        ascending=[True, True, False, False, True],
    )
    primary = valid.drop_duplicates(["trade_date", "ts_code"], keep="first")[
        ["trade_date", "ts_code", "sector_id"]
    ].rename(columns={"sector_id": "primary_sector_id"})
    return keys.merge(primary, on=["trade_date", "ts_code"], how="left")


def calculate_stock_states(
    factors: pd.DataFrame,
    market: pd.DataFrame,
    sector_members: pd.DataFrame,
    sector_factors: pd.DataFrame,
    previous_states: pd.DataFrame,
    start: date,
    end: date,
    config: TrendConfig,
) -> pd.DataFrame:
    if factors.empty:
        return pd.DataFrame()

    df = _prepare_factors(factors)
    df = _calculate_scores(df)
    df = _merge_context(df, market, sector_members, sector_factors)
    df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)].copy()
    if df.empty:
        return pd.DataFrame()

    previous_by_code: dict[str, tuple[str | None, int | None]] = {}
    if not previous_states.empty:
        previous = previous_states.copy()
        previous["trade_date"] = pd.to_datetime(previous["trade_date"]).dt.date
        previous = previous.sort_values(["ts_code", "trade_date"])
        for row in previous.to_dict("records"):
            previous_by_code[row["ts_code"]] = (row.get("state"), row.get("state_day_count"))

    output_rows = []
    for current_date in sorted(df["trade_date"].unique()):
        day = df[df["trade_date"] == current_date].sort_values("ts_code")
        for _, row in day.iterrows():
            previous_state, previous_count = previous_by_code.get(row["ts_code"], (None, None))
            raw_state, raw_reasons = _raw_state(row, config)
            state, reasons, fast_transition = _apply_transition(
                raw_state, raw_reasons, previous_state, previous_count, config
            )
            is_new_state = previous_state != state
            state_day_count = (previous_count or 0) + 1 if previous_state == state else 1
            row = row.copy()
            row["state"] = state
            opportunity_score = _opportunity_score(row)
            output_rows.append(
                {
                    "trade_date": current_date,
                    "ts_code": row["ts_code"],
                    "algo_version": config.algo_version,
                    "previous_state": previous_state,
                    "state": state,
                    "state_day_count": state_day_count,
                    "is_new_state": is_new_state,
                    "right_side_score": row["right_side_score"],
                    "trend_score": row["trend_score"],
                    "opportunity_score": opportunity_score,
                    "primary_sector_id": row.get("primary_sector_id"),
                    "sector_heat": row.get("sector_heat"),
                    "market_score": row.get("market_score"),
                    "fast_transition": fast_transition,
                    "reason_codes": reasons,
                }
            )
            previous_by_code[row["ts_code"]] = (state, state_day_count)

    return pd.DataFrame(output_rows).replace({np.nan: None})


def generate_strategy_signals(states: pd.DataFrame, config: TrendConfig) -> pd.DataFrame:
    if states.empty:
        return pd.DataFrame()

    rows = []
    for row in states.to_dict("records"):
        signal_types = []
        previous = row.get("previous_state")
        state = row.get("state")
        if state == "S3" and row.get("is_new_state"):
            signal_types.append("RIGHT_SIDE_NEW")
        if state == "S4" and previous != "S4":
            signal_types.append("TREND_ENTER")
        if state == "S5" and previous != "S5":
            signal_types.append("MAIN_UP_ENTER")
        if state == "S6" and previous in {"S3", "S4", "S5"}:
            signal_types.append("TREND_DECAY")
        if state in {"S3", "S4", "S5"} and (row.get("trend_score") or 0) >= config.s5_min_score:
            signal_types.append("LEADER_BREAKOUT")

        for signal_type in signal_types:
            rows.append(
                {
                    "trade_date": row["trade_date"],
                    "ts_code": row["ts_code"],
                    "signal_type": signal_type,
                    "score": row.get("right_side_score")
                    if signal_type == "RIGHT_SIDE_NEW"
                    else row.get("trend_score"),
                    "opportunity_score": row.get("opportunity_score"),
                    "reason_codes": row.get("reason_codes"),
                    "payload": {
                        "state": state,
                        "previous_state": previous,
                        "fast_transition": row.get("fast_transition", False),
                    },
                    "algo_version": config.algo_version,
                }
            )
    return pd.DataFrame(rows).replace({np.nan: None})
