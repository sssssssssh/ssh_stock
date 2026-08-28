from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarketConfig:
    index_codes: tuple[str, ...] = ("000300.SH", "000001.SH", "000852.SH")
    primary_index: str = "000300.SH"
    index_weights: tuple[float, ...] = (0.4, 0.2, 0.4)
    risk_on_score: float = 70
    risk_off_score: float = 45

    @classmethod
    def from_strategy(cls, strategy: dict[str, Any]) -> "MarketConfig":
        benchmark = strategy.get("benchmark", {})
        market = strategy.get("market", {})
        codes = tuple(benchmark.get("market_indices", cls.index_codes))
        weights = tuple(market.get("index_weights", cls.index_weights))
        if len(weights) != len(codes):
            weights = tuple(1 / len(codes) for _ in codes) if codes else ()
        return cls(
            index_codes=codes,
            primary_index=benchmark.get("primary", cls.primary_index),
            index_weights=weights,
            risk_on_score=float(market.get("risk_on_score", cls.risk_on_score)),
            risk_off_score=float(market.get("risk_off_score", cls.risk_off_score)),
        )


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    left = pd.to_numeric(numerator, errors="coerce")
    right = pd.to_numeric(denominator, errors="coerce")
    return left.divide(right.replace(0, np.nan))


def _linear_score(value: float | None, low: float, mid: float, high: float) -> float | None:
    if value is None or pd.isna(value):
        return None
    if value <= low:
        return 0
    if value >= high:
        return 100
    if value <= mid:
        return float((value - low) / (mid - low) * 50)
    return float(50 + (value - mid) / (high - mid) * 50)


def _regime(score: float | None, config: MarketConfig) -> str | None:
    if score is None or pd.isna(score):
        return None
    if score >= config.risk_on_score:
        return "RISK_ON"
    if score <= config.risk_off_score:
        return "RISK_OFF"
    return "NEUTRAL"


def _calculate_index_scores(index_daily: pd.DataFrame, config: MarketConfig) -> pd.DataFrame:
    if index_daily.empty:
        return pd.DataFrame(columns=["trade_date", "index_trend_score"])

    df = index_daily.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df[df["ts_code"].isin(config.index_codes)].sort_values(["ts_code", "trade_date"])
    if df.empty:
        return pd.DataFrame(columns=["trade_date", "index_trend_score"])

    group = df.groupby("ts_code", group_keys=False)
    df["ma20"] = group["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["ma60"] = group["close"].transform(lambda s: s.rolling(60, min_periods=60).mean())
    df["return20"] = group["close"].transform(lambda s: s / s.shift(20) - 1)
    df["ma20_slope5"] = group["ma20"].transform(lambda s: (s / s.shift(5) - 1) / 5)

    checks = pd.concat(
        [
            (df["close"] > df["ma20"]).astype(float) * 25,
            (df["ma20"] > df["ma60"]).astype(float) * 25,
            (df["return20"] > 0).astype(float) * 25,
            (df["ma20_slope5"] > 0).astype(float) * 25,
        ],
        axis=1,
    )
    df["code_score"] = checks.where(checks.notna()).sum(axis=1, min_count=1)

    weight_map = dict(zip(config.index_codes, config.index_weights, strict=False))
    df["weight"] = df["ts_code"].map(weight_map).fillna(0)
    df["weighted_score"] = df["code_score"] * df["weight"]
    weighted = (
        df.groupby("trade_date")
        .agg(weighted_score=("weighted_score", "sum"), weight=("weight", "sum"))
        .reset_index()
    )
    weighted["index_trend_score"] = _safe_divide(
        weighted["weighted_score"], weighted["weight"]
    )
    return weighted[["trade_date", "index_trend_score"]]


def calculate_market_daily(
    factors: pd.DataFrame,
    daily: pd.DataFrame,
    index_daily: pd.DataFrame,
    start: date,
    end: date,
    config: MarketConfig,
) -> pd.DataFrame:
    if factors.empty and daily.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    if not factors.empty:
        factor_df = factors.copy()
        factor_df["trade_date"] = pd.to_datetime(factor_df["trade_date"]).dt.date
        eligible = factor_df[factor_df["eligible"].fillna(False)].copy()
        if not eligible.empty:
            eligible["above_ma20"] = eligible["adj_close"] > eligible["ma20"]
            eligible["above_ma60"] = eligible["adj_close"] > eligible["ma60"]
            eligible["new_low20"] = eligible["adj_close"] <= eligible["low20"]
            eligible["new_low60"] = eligible["adj_close"] <= eligible["low60"]
            factor_agg = (
                eligible.groupby("trade_date")
                .agg(
                    breadth20=("above_ma20", "mean"),
                    breadth60=("above_ma60", "mean"),
                    new_high20_count=("breakout20", "sum"),
                    new_low20_count=("new_low20", "sum"),
                    new_high60_count=("breakout60", "sum"),
                    new_low60_count=("new_low60", "sum"),
                )
                .reset_index()
            )
            frames.append(factor_agg)

    if not daily.empty:
        daily_df = daily.copy()
        daily_df["trade_date"] = pd.to_datetime(daily_df["trade_date"]).dt.date
        pct_chg = daily_df["pct_chg"]
        if "pre_close" in daily_df.columns:
            pct_chg = pct_chg.fillna(daily_df["close"] / daily_df["pre_close"] - 1)
        daily_df["up"] = pct_chg > 0
        daily_df["down"] = pct_chg < 0
        daily_df["flat"] = pct_chg == 0
        daily_agg = (
            daily_df.groupby("trade_date")
            .agg(
                up_count=("up", "sum"),
                down_count=("down", "sum"),
                flat_count=("flat", "sum"),
                total_amount=("amount", "sum"),
            )
            .reset_index()
            .sort_values("trade_date")
        )
        total_direction = daily_agg["up_count"] + daily_agg["down_count"] + daily_agg["flat_count"]
        daily_agg["up_rate"] = _safe_divide(daily_agg["up_count"], total_direction)
        daily_agg["amount_ratio20"] = _safe_divide(
            daily_agg["total_amount"],
            daily_agg["total_amount"].rolling(20, min_periods=5).mean(),
        )
        frames.append(daily_agg)

    index_scores = _calculate_index_scores(index_daily, config)
    if not index_scores.empty:
        frames.append(index_scores)

    if not frames:
        return pd.DataFrame()

    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on="trade_date", how="outer")
    result = result.sort_values("trade_date")

    default_columns = {
        "breadth20": None,
        "breadth60": None,
        "new_high20_count": None,
        "new_low20_count": None,
        "new_high60_count": None,
        "new_low60_count": None,
        "up_count": None,
        "down_count": None,
        "flat_count": None,
        "up_rate": None,
        "total_amount": None,
        "amount_ratio20": None,
        "index_trend_score": None,
    }
    for column, default in default_columns.items():
        if column not in result.columns:
            result[column] = default

    result["breadth_score"] = (
        result[["breadth20", "breadth60"]].mean(axis=1, skipna=True) * 100
    )
    result["ad_score"] = result["up_rate"] * 100
    denominator20 = result["new_high20_count"] + result["new_low20_count"]
    denominator60 = result["new_high60_count"] + result["new_low60_count"]
    high_low20 = _safe_divide(result["new_high20_count"], denominator20) * 100
    high_low60 = _safe_divide(result["new_high60_count"], denominator60) * 100
    result["new_high_low_score"] = pd.concat([high_low20, high_low60], axis=1).mean(
        axis=1, skipna=True
    )
    result["liquidity_score"] = result["amount_ratio20"].map(
        lambda value: _linear_score(value, low=0.7, mid=1.0, high=1.6)
    )

    score_parts = result[
        [
            "index_trend_score",
            "breadth_score",
            "ad_score",
            "new_high_low_score",
            "liquidity_score",
        ]
    ]
    weights = pd.Series(
        {
            "index_trend_score": 0.25,
            "breadth_score": 0.30,
            "ad_score": 0.15,
            "new_high_low_score": 0.15,
            "liquidity_score": 0.15,
        }
    )
    weighted = score_parts.mul(weights, axis=1)
    present_weight = score_parts.notna().mul(weights, axis=1).sum(axis=1)
    result["market_score"] = weighted.sum(axis=1, min_count=1) / present_weight
    result["regime"] = result["market_score"].map(lambda score: _regime(score, config))

    columns = [
        "trade_date",
        "market_score",
        "regime",
        "breadth20",
        "breadth60",
        "up_count",
        "down_count",
        "flat_count",
        "up_rate",
        "new_high20_count",
        "new_low20_count",
        "new_high60_count",
        "new_low60_count",
        "total_amount",
        "amount_ratio20",
        "index_trend_score",
        "breadth_score",
        "ad_score",
        "new_high_low_score",
        "liquidity_score",
    ]
    output = result[(result["trade_date"] >= start) & (result["trade_date"] <= end)].copy()
    return output[columns].replace({np.nan: None})
