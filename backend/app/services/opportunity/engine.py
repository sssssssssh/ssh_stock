from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OpportunityConfig:
    left_weights: dict[str, float]
    trend_weights: dict[str, float]
    left_watch: float
    left_strong: float

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OpportunityConfig":
        left = value.get("left_reversal", {})
        return cls(
            left_weights={key: float(weight) for key, weight in left.get("weights", {}).items()},
            trend_weights={
                key: float(weight)
                for key, weight in value.get("trend_pool", {}).get("weights", {}).items()
            },
            left_watch=float(left.get("watch_score", 60)),
            left_strong=float(left.get("strong_score", 75)),
        )


def calculate_opportunities(
    factors: pd.DataFrame,
    states: pd.DataFrame,
    market: pd.DataFrame,
    sector_members: pd.DataFrame,
    sector_factors: pd.DataFrame,
    themes: pd.DataFrame,
    theme_members: pd.DataFrame,
    theme_factors: pd.DataFrame,
    valid_snapshots: set[date],
    start: date,
    end: date,
    algo_version: str,
    config: OpportunityConfig,
) -> pd.DataFrame:
    if states.empty or factors.empty:
        return pd.DataFrame()
    values = _prepare_factor_context(factors)
    state_values = states.copy()
    state_values["trade_date"] = pd.to_datetime(state_values["trade_date"]).dt.date
    values = values.merge(state_values, on=["trade_date", "ts_code"], how="inner")
    if not market.empty:
        market = market.copy()
        market["trade_date"] = pd.to_datetime(market["trade_date"]).dt.date
        values = values.merge(market[["trade_date", "market_score"]], on="trade_date", how="left")
    else:
        values["market_score"] = np.nan

    values = _left_scores(values, config)
    values = _industry_context(values, sector_members, sector_factors)
    values = _theme_context(values, themes, theme_members, theme_factors, valid_snapshots)
    values["context_score"] = _weighted_available(
        values,
        {"industry_heat": 0.40, "primary_theme_heat": 0.60},
    )
    values["trend_rank_score"] = _weighted_available(
        values,
        {
            "trend_score": config.trend_weights.get("trend_score", 0.55),
            "rps60": config.trend_weights.get("rps60", 0.20),
            "rps120": config.trend_weights.get("rps120", 0.10),
            "context_score": config.trend_weights.get("context", 0.10),
            "market_score": config.trend_weights.get("market", 0.05),
        },
    ).where(values["state"].isin(["S4", "S5"]))
    values["position_score"] = _position_score(values).where(values["state"].isin(["S4", "S5"]))
    values["extension_risk"] = values.apply(_extension_risk, axis=1)
    values["opportunity_stage"] = values.apply(lambda row: _stage(row, config), axis=1)
    values["opportunity_score"] = values.apply(_opportunity_score, axis=1)
    values["reason_codes"] = values.apply(_reason_codes, axis=1)
    values["algo_version"] = algo_version

    output = values[(values["trade_date"] >= start) & (values["trade_date"] <= end)].copy()
    columns = [
        "trade_date",
        "ts_code",
        "algo_version",
        "state",
        "previous_state",
        "state_day_count",
        "left_reversal_score",
        "left_reversal_new",
        "right_side_score",
        "trend_score",
        "trend_rank_score",
        "position_score",
        "extension_risk",
        "market_score",
        "industry_sector_id",
        "industry_heat",
        "industry_lifecycle",
        "primary_theme_code",
        "primary_theme_name",
        "primary_theme_heat",
        "primary_theme_lifecycle",
        "hot_theme_count",
        "context_score",
        "opportunity_stage",
        "opportunity_score",
        "reason_codes",
    ]
    return output[columns].replace({np.nan: None})


def _prepare_factor_context(factors: pd.DataFrame) -> pd.DataFrame:
    values = factors.copy()
    values["trade_date"] = pd.to_datetime(values["trade_date"]).dt.date
    values = values.sort_values(["ts_code", "trade_date"])
    grouped = values.groupby("ts_code", group_keys=False)
    values["return20_lag5"] = grouped["return20"].shift(5)
    values["ma20_slope_prev"] = grouped["ma20_slope5"].shift(1)
    values["left_previous"] = np.nan
    values["atr_percentile60"] = grouped["atr20_pct"].transform(
        lambda series: series.rolling(60, min_periods=10).apply(
            lambda window: pd.Series(window).rank(pct=True).iloc[-1], raw=False
        )
    )
    for column in ("rps20_delta5", "rps60_delta5"):
        values[f"{column}_rank"] = values.groupby("trade_date")[column].rank(pct=True) * 100
    return values


def _left_scores(values: pd.DataFrame, config: OpportunityConfig) -> pd.DataFrame:
    eligible = values["eligible"].fillna(False) & values["state"].isin(["S1", "S2"])
    values["stabilization"] = values.apply(_stabilization, axis=1)
    values["ma20_turn"] = values.apply(_ma20_turn, axis=1)
    values["higher_low_score"] = values.apply(_higher_low, axis=1)
    values["rps_recovery"] = (
        0.50 * values["rps20"].fillna(0)
        + 0.30 * values["rps20_delta5_rank"].fillna(0)
        + 0.20 * values["rps60_delta5_rank"].fillna(0)
    )
    values["price_recovery"] = values.apply(_price_recovery, axis=1)
    values["volatility_contraction"] = values["atr_percentile60"].map(_atr_score)
    values["volume_structure"] = values.apply(_volume_structure, axis=1)
    component_map = {
        "stabilization": "stabilization",
        "ma20_turn": "ma20_turn",
        "higher_low": "higher_low_score",
        "rps_recovery": "rps_recovery",
        "price_recovery": "price_recovery",
        "volatility_contraction": "volatility_contraction",
        "volume_structure": "volume_structure",
    }
    score = pd.Series(0.0, index=values.index)
    for name, column in component_map.items():
        score += values[column].fillna(0) * config.left_weights.get(name, 0)
    values["left_reversal_score"] = score.clip(0, 100).where(eligible)
    previous = values.groupby("ts_code")["left_reversal_score"].shift(1)
    values["left_reversal_new"] = (
        eligible
        & (values["left_reversal_score"] >= config.left_strong)
        & previous.notna()
        & (previous < config.left_strong)
    )
    return values


def _stabilization(row: pd.Series) -> float:
    drawdown = row.get("drawdown_high60")
    if pd.isna(drawdown):
        return 0
    score = (
        30
        if drawdown > -0.05
        else 60
        if drawdown > -0.08
        else 100
        if drawdown >= -0.30
        else 80
        if drawdown >= -0.45
        else 40
    )
    if not pd.isna(row.get("return20_lag5")) and row.get("return20") > row.get("return20_lag5"):
        score += min(20, max(5, (row.get("return20") - row.get("return20_lag5")) * 200))
    return min(100, score)


def _ma20_turn(row: pd.Series) -> float:
    current, previous = row.get("ma20_slope5"), row.get("ma20_slope_prev")
    if pd.isna(current):
        return 0
    if not pd.isna(previous) and previous < 0 <= current:
        return 100
    if current > 0:
        return 75
    if not pd.isna(previous) and current > previous and current >= -0.01:
        return 80
    return max(0, 30 + current * 1000)


def _higher_low(row: pd.Series) -> float:
    pct = row.get("higher_low_pct")
    if bool(row.get("higher_low")):
        return 100 if not pd.isna(pct) and pct >= 0.05 else 80
    return 40 if not pd.isna(pct) and pct >= -0.02 else 0


def _price_recovery(row: pd.Series) -> float:
    if bool(row.get("cross_above_ma60")):
        return 100
    if bool(row.get("cross_above_ma20")):
        return 85
    close, ma20 = row.get("adj_close"), row.get("ma20")
    if pd.isna(close) or pd.isna(ma20) or not ma20:
        return 0
    distance = close / ma20 - 1
    if distance > 0:
        return 70
    return 55 if distance >= -0.03 else 20


def _atr_score(percentile: float | None) -> float:
    if percentile is None or pd.isna(percentile):
        return 0
    return (
        100
        if percentile <= 0.30
        else 80
        if percentile <= 0.50
        else 50
        if percentile <= 0.70
        else 20
    )


def _volume_structure(row: pd.Series) -> float:
    ratio = row.get("amount_ratio20")
    if pd.isna(ratio):
        return 0
    if bool(row.get("cross_above_ma20")) and 1 <= ratio <= 1.8:
        return 100
    if 0.6 <= ratio <= 1:
        return 80
    if ratio > 2.5:
        return 40
    return 60


def _industry_context(
    values: pd.DataFrame, members: pd.DataFrame, factors: pd.DataFrame
) -> pd.DataFrame:
    result = values.copy()
    result[["industry_sector_id", "industry_heat", "industry_lifecycle"]] = np.nan
    if members.empty or factors.empty:
        return result
    member_values = members.copy()
    member_values["valid_from"] = pd.to_datetime(member_values["valid_from"]).dt.date
    member_values["valid_to"] = pd.to_datetime(member_values["valid_to"], errors="coerce").dt.date
    factor_values = factors.copy()
    factor_values["trade_date"] = pd.to_datetime(factor_values["trade_date"]).dt.date
    for index, row in result.iterrows():
        matching = member_values[
            (member_values["ts_code"] == row["ts_code"])
            & (member_values["valid_from"] <= row["trade_date"])
            & (member_values["valid_to"].isna() | (member_values["valid_to"] >= row["trade_date"]))
        ]
        candidates = factor_values[
            (factor_values["trade_date"] == row["trade_date"])
            & factor_values["sector_id"].isin(matching["sector_id"])
        ].sort_values("heat_score", ascending=False)
        if not candidates.empty:
            top = candidates.iloc[0]
            result.at[index, "industry_sector_id"] = top["sector_id"]
            result.at[index, "industry_heat"] = top["heat_score"]
            result.at[index, "industry_lifecycle"] = top.get("lifecycle")
    return result


def _theme_context(
    values: pd.DataFrame,
    themes: pd.DataFrame,
    members: pd.DataFrame,
    factors: pd.DataFrame,
    valid_snapshots: set[date],
) -> pd.DataFrame:
    result = values.copy()
    columns = [
        "primary_theme_code",
        "primary_theme_name",
        "primary_theme_heat",
        "primary_theme_lifecycle",
        "hot_theme_count",
    ]
    for column in columns:
        result[column] = None
    if members.empty or factors.empty:
        return result
    member_values, factor_values = members.copy(), factors.copy()
    member_values["snapshot_date"] = pd.to_datetime(member_values["snapshot_date"]).dt.date
    factor_values["trade_date"] = pd.to_datetime(factor_values["trade_date"]).dt.date
    names = dict(zip(themes.get("theme_code", []), themes.get("name", []), strict=False))
    for trade_date, day_indexes in result.groupby("trade_date").groups.items():
        available = [snapshot for snapshot in valid_snapshots if snapshot <= trade_date]
        if not available:
            continue
        snapshot = max(available)
        day_members = member_values[member_values["snapshot_date"] == snapshot]
        day_factors = factor_values[factor_values["trade_date"] == trade_date]
        for index in day_indexes:
            codes = day_members.loc[
                day_members["ts_code"] == result.at[index, "ts_code"], "theme_code"
            ]
            candidates = day_factors[day_factors["theme_code"].isin(codes)].sort_values(
                "heat_score", ascending=False
            )
            if candidates.empty:
                continue
            top = candidates.iloc[0]
            code = top["theme_code"]
            result.at[index, "primary_theme_code"] = code
            result.at[index, "primary_theme_name"] = names.get(code)
            result.at[index, "primary_theme_heat"] = top["heat_score"]
            result.at[index, "primary_theme_lifecycle"] = top.get("lifecycle")
            result.at[index, "hot_theme_count"] = int((candidates["heat_score"] >= 60).sum())
    return result


def _weighted_available(values: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    numerator = pd.Series(0.0, index=values.index)
    denominator = pd.Series(0.0, index=values.index)
    for column, weight in weights.items():
        numerator += values[column].fillna(0) * weight
        denominator += values[column].notna().astype(float) * weight
    return numerator.div(denominator.replace(0, np.nan))


def _position_score(values: pd.DataFrame) -> pd.Series:
    distance = values["adj_close"] / values["ma20"] - 1
    ma_score = distance.map(_ma20_distance_score)
    drawdown_score = values["drawdown_high60"].map(_drawdown_position_score)
    atr_score = values["atr_percentile60"].map(_atr_position_score)
    volume_score = values["amount_ratio20"].map(_volume_heat_score)
    return 0.40 * ma_score + 0.30 * drawdown_score + 0.20 * atr_score + 0.10 * volume_score


def _ma20_distance_score(value: float) -> float:
    if pd.isna(value):
        return 0
    if value < -0.05:
        return 20
    if value < 0:
        return 70
    if value <= 0.05:
        return 100
    if value <= 0.10:
        return 90
    if value <= 0.15:
        return 65
    if value <= 0.20:
        return 35
    return 10


def _drawdown_position_score(value: float) -> float:
    if pd.isna(value):
        return 0
    if value >= -0.03:
        return 70
    if value >= -0.10:
        return 100
    if value >= -0.15:
        return 70
    if value >= -0.20:
        return 40
    return 15


def _atr_position_score(value: float) -> float:
    if pd.isna(value):
        return 0
    return 70 if value <= 0.30 else 100 if value <= 0.60 else 60 if value <= 0.80 else 25


def _volume_heat_score(value: float) -> float:
    if pd.isna(value):
        return 0
    if 0.8 <= value <= 1.5:
        return 100
    if value <= 2.5:
        return 65
    return 25


def _extension_risk(row: pd.Series) -> str | None:
    if row.get("state") not in {"S4", "S5"}:
        return None
    close, ma20, ma60 = row.get("adj_close"), row.get("ma20"), row.get("ma60")
    if pd.isna(close) or pd.isna(ma20) or not ma20:
        return None
    distance = close / ma20 - 1
    if not pd.isna(ma60) and close < ma60:
        return "BROKEN"
    if -0.03 <= distance <= 0.03 and (pd.isna(ma60) or close > ma60):
        return "PULLBACK"
    if distance > 0.20 or row.get("amount_ratio20", 0) > 3:
        return "EXTREME"
    if distance > 0.15 or row.get("amount_ratio20", 0) > 2.5:
        return "EXTENDED"
    return "NORMAL"


def _stage(row: pd.Series, config: OpportunityConfig) -> str:
    state, left = row.get("state"), row.get("left_reversal_score")
    if state == "S5":
        return "STRONG_TREND"
    if state == "S4":
        return "TREND"
    if state == "S3":
        return "RIGHT_SIDE_NEW" if bool(row.get("is_new_state")) else "RIGHT_SIDE"
    if state in {"S1", "S2"} and not pd.isna(left):
        if left >= config.left_strong:
            return "LEFT_REVERSAL"
        if left >= config.left_watch:
            return "LEFT_WATCH"
    return "OTHER"


def _opportunity_score(row: pd.Series) -> float | None:
    stage = row["opportunity_stage"]
    if stage.startswith("LEFT"):
        context = row.get("context_score")
        return (
            row["left_reversal_score"]
            if pd.isna(context)
            else 0.8 * row["left_reversal_score"] + 0.2 * context
        )
    if stage.startswith("RIGHT"):
        scores = [
            (row.get("right_side_score"), 0.75),
            (row.get("context_score"), 0.15),
            (row.get("market_score"), 0.10),
        ]
        valid = [
            (score, weight) for score, weight in scores if score is not None and not pd.isna(score)
        ]
        return (
            sum(score * weight for score, weight in valid) / sum(weight for _, weight in valid)
            if valid
            else None
        )
    if stage in {"TREND", "STRONG_TREND"}:
        return 0.70 * row["trend_rank_score"] + 0.30 * row["position_score"]
    return None


def _reason_codes(row: pd.Series) -> dict[str, list[str]]:
    codes: list[str] = []
    if row.get("drawdown_high60", 0) <= -0.08:
        codes.append("DRAWDOWN_BASE")
    if row.get("return20", 0) > row.get("return20_lag5", 0):
        codes.append("RETURN20_STABILIZING")
    if row.get("ma20_turn", 0) >= 75:
        codes.append("MA20_TURN_UP")
    if bool(row.get("higher_low")):
        codes.append("HIGHER_LOW")
    if row.get("rps20_delta5", 0) > 0:
        codes.append("RPS20_RECOVERING")
    if row.get("rps60_delta5", 0) > 0:
        codes.append("RPS60_RECOVERING")
    if bool(row.get("cross_above_ma20")):
        codes.append("CROSS_MA20")
    elif row.get("price_recovery", 0) >= 70:
        codes.append("ABOVE_MA20")
    if row.get("volatility_contraction", 0) >= 80:
        codes.append("VOLATILITY_CONTRACTING")
    if row.get("volume_structure") == 80:
        codes.append("VOLUME_CONTRACTION")
    if row.get("volume_structure") == 100:
        codes.append("VOLUME_CONFIRMATION")
    if _number(row.get("primary_theme_heat")) >= 60:
        codes.append("HOT_THEME")
    if _number(row.get("industry_heat")) >= 60:
        codes.append("HOT_INDUSTRY")
    if _number(row.get("position_score")) >= 70:
        codes.append("GOOD_POSITION")
    if row.get("extension_risk") in {"EXTENDED", "EXTREME"}:
        codes.append("OVEREXTENDED")
    if _number(row.get("rps60")) >= 80:
        codes.append("STRONG_RPS")
    if _number(row.get("trend_score")) >= 80:
        codes.append("STRONG_TREND")
    return {"codes": codes}


def _number(value: Any) -> float:
    return 0.0 if value is None or pd.isna(value) else float(value)
