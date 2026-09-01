from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SectorConfig:
    benchmark_code: str = "000300.SH"
    heat_main_up: float = 75
    heat_climax: float = 90
    heat_watch: float = 40
    heat_weights: dict[str, float] | None = None

    @classmethod
    def from_strategy(cls, strategy: dict[str, Any]) -> "SectorConfig":
        benchmark = strategy.get("benchmark", {})
        sector = strategy.get("sector", {})
        return cls(
            benchmark_code=benchmark.get("primary", cls.benchmark_code),
            heat_main_up=float(sector.get("heat_main_up", cls.heat_main_up)),
            heat_climax=float(sector.get("heat_climax", cls.heat_climax)),
            heat_watch=float(sector.get("heat_watch", cls.heat_watch)),
            heat_weights=sector.get("heat_weights"),
        )

    @property
    def weights(self) -> dict[str, float]:
        return self.heat_weights or {
            "excess_return5": 0.20,
            "excess_return20": 0.15,
            "breadth20": 0.15,
            "breadth60": 0.10,
            "new_high20_rate": 0.10,
            "rps60_median": 0.10,
            "amount_ratio20": 0.10,
            "up_rate": 0.05,
            "limit_up_density": 0.025,
            "moneyflow_score": 0.025,
        }


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    left = pd.to_numeric(numerator, errors="coerce")
    right = pd.to_numeric(denominator, errors="coerce")
    return left.divide(right.replace(0, np.nan))


def _benchmark_returns(index_daily: pd.DataFrame, config: SectorConfig) -> pd.DataFrame:
    if index_daily.empty:
        return pd.DataFrame(columns=["trade_date", "benchmark_return5", "benchmark_return20"])
    df = index_daily[index_daily["ts_code"] == config.benchmark_code].copy()
    if df.empty:
        return pd.DataFrame(columns=["trade_date", "benchmark_return5", "benchmark_return20"])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df = df.sort_values("trade_date")
    df["benchmark_return5"] = df["close"] / df["close"].shift(5) - 1
    df["benchmark_return20"] = df["close"] / df["close"].shift(20) - 1
    return df[["trade_date", "benchmark_return5", "benchmark_return20"]]


def _prepare_member_factors(factors: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    if factors.empty or members.empty:
        return pd.DataFrame()

    factor_df = factors.copy()
    member_df = members.copy()
    factor_df["trade_date"] = pd.to_datetime(factor_df["trade_date"]).dt.date
    member_df["valid_from"] = pd.to_datetime(member_df["valid_from"]).dt.date
    member_df["valid_to"] = pd.to_datetime(member_df["valid_to"]).dt.date

    merged = factor_df.merge(member_df, on="ts_code", how="inner")
    valid_to = merged["valid_to"].fillna(date(9999, 12, 31))
    merged = merged[
        (merged["trade_date"] >= merged["valid_from"]) & (merged["trade_date"] <= valid_to)
    ].copy()
    if merged.empty:
        return merged

    for column in ["return1", "return3", "return5", "return20"]:
        if column not in merged.columns:
            merged[column] = np.nan
    numeric_columns = [
        "adj_close",
        "ma20",
        "ma60",
        "return1",
        "return3",
        "return5",
        "return20",
        "rps60",
        "amount_ma20",
        "amount_ratio20",
    ]
    for column in numeric_columns:
        if column in merged.columns:
            merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged["eligible"] = merged["eligible"].fillna(False)
    merged["above_ma20"] = merged["adj_close"] > merged["ma20"]
    merged["above_ma60"] = merged["adj_close"] > merged["ma60"]
    merged["new_high20"] = merged["breakout20"].fillna(False)
    merged["up"] = merged["return1"] > 0
    merged["rps60_top20"] = merged["rps60"] >= 80
    merged["estimated_amount"] = merged["amount_ma20"] * merged["amount_ratio20"]
    return merged


def _label_lifecycle(row: pd.Series, config: SectorConfig) -> str | None:
    heat = row.get("heat_score")
    if heat is None or pd.isna(heat):
        return None

    momentum3 = row.get("heat_momentum3")
    momentum3 = 0 if momentum3 is None or pd.isna(momentum3) else float(momentum3)
    prev_heat = row.get("prev_heat_score")
    breadth20 = row.get("breadth20")
    return5_score = row.get("return5_score")

    if (
        heat >= config.heat_climax
        and not pd.isna(breadth20)
        and breadth20 >= 0.80
        and not pd.isna(return5_score)
        and return5_score >= 90
    ):
        return "CLIMAX"
    if heat >= 70 and momentum3 <= -8:
        return "DIVERGENCE"
    if heat >= config.heat_main_up and momentum3 >= 0:
        return "MAIN_UP"
    if heat >= 60 and momentum3 > 5:
        return "HEATING"
    if not pd.isna(prev_heat) and prev_heat < 55 <= heat and momentum3 >= 10:
        return "STARTING"
    if config.heat_watch <= heat < 60:
        return "WATCH"
    if heat < 60 and momentum3 < 0:
        return "COOLING"
    if heat < config.heat_watch:
        return "COLD"
    return "WATCH"


def calculate_sector_factors(
    factors: pd.DataFrame,
    members: pd.DataFrame,
    index_daily: pd.DataFrame,
    start: date,
    end: date,
    config: SectorConfig,
) -> pd.DataFrame:
    member_factors = _prepare_member_factors(factors, members)
    if member_factors.empty:
        return pd.DataFrame()

    total_counts = (
        member_factors.groupby(["trade_date", "sector_id"])
        .agg(member_count=("ts_code", "nunique"))
        .reset_index()
    )

    eligible = member_factors[member_factors["eligible"]].copy()
    if eligible.empty:
        return pd.DataFrame()

    grouped = (
        eligible.groupby(["trade_date", "sector_id"])
        .agg(
            eligible_member_count=("ts_code", "nunique"),
            return1=("return1", "mean"),
            return3=("return3", "mean"),
            return5=("return5", "mean"),
            return20=("return20", "mean"),
            breadth20=("above_ma20", "mean"),
            breadth60=("above_ma60", "mean"),
            up_rate=("up", "mean"),
            new_high20_rate=("new_high20", "mean"),
            rps60_median=("rps60", "median"),
            rps60_top20_rate=("rps60_top20", "mean"),
            amount=("estimated_amount", "sum"),
        )
        .reset_index()
        .sort_values(["sector_id", "trade_date"])
    )
    grouped = grouped.merge(total_counts, on=["trade_date", "sector_id"], how="left")
    grouped["amount_ratio20"] = grouped.groupby("sector_id")["amount"].transform(
        lambda s: _safe_divide(s, s.rolling(20, min_periods=5).mean())
    )
    grouped["limit_up_density"] = np.nan
    grouped["moneyflow_score"] = np.nan

    benchmark = _benchmark_returns(index_daily, config)
    grouped = grouped.merge(benchmark, on="trade_date", how="left")
    grouped["excess_return5"] = grouped["return5"] - grouped["benchmark_return5"]
    grouped["excess_return20"] = grouped["return20"] - grouped["benchmark_return20"]

    score_inputs = {
        "excess_return5": "excess_return5_score",
        "excess_return20": "excess_return20_score",
        "breadth20": "breadth20_score",
        "breadth60": "breadth60_score",
        "new_high20_rate": "new_high20_rate_score",
        "rps60_median": "rps60_median_score",
        "amount_ratio20": "amount_ratio20_score",
        "up_rate": "up_rate_score",
        "limit_up_density": "limit_up_density_score",
        "moneyflow_score": "moneyflow_score_pct",
        "return5": "return5_score",
    }
    for input_col, score_col in score_inputs.items():
        grouped[score_col] = (
            grouped[input_col].groupby(grouped["trade_date"]).rank(pct=True, method="average")
            * 100
        )

    weights = config.weights
    score_cols = {column: f"{column}_score" for column in weights}
    score_cols["moneyflow_score"] = "moneyflow_score_pct"
    weighted = pd.Series(0.0, index=grouped.index)
    present_weight = pd.Series(0.0, index=grouped.index)
    for input_col, weight in weights.items():
        score_col = score_cols[input_col]
        values = grouped[score_col]
        weighted = weighted.add(values.fillna(0) * weight, fill_value=0)
        present_weight = present_weight.add(values.notna().astype(float) * weight, fill_value=0)
    grouped["heat_score"] = weighted / present_weight.replace(0, np.nan)

    grouped["heat_rank"] = (
        grouped.groupby("trade_date")["heat_score"]
        .rank(method="first", ascending=False)
        .astype("Int64")
    )
    by_sector = grouped.groupby("sector_id", group_keys=False)
    grouped["heat_momentum1"] = by_sector["heat_score"].transform(lambda s: s - s.shift(1))
    grouped["heat_momentum3"] = by_sector["heat_score"].transform(lambda s: s - s.shift(3))
    grouped["prev_heat_score"] = by_sector["heat_score"].shift(1)
    grouped["prev_heat_rank"] = by_sector["heat_rank"].shift(1)
    grouped["rank_change"] = grouped["prev_heat_rank"] - grouped["heat_rank"]
    grouped["lifecycle"] = grouped.apply(lambda row: _label_lifecycle(row, config), axis=1)

    columns = [
        "trade_date",
        "sector_id",
        "member_count",
        "eligible_member_count",
        "return1",
        "return3",
        "return5",
        "return20",
        "excess_return5",
        "excess_return20",
        "breadth20",
        "breadth60",
        "up_rate",
        "new_high20_rate",
        "rps60_median",
        "rps60_top20_rate",
        "amount",
        "amount_ratio20",
        "limit_up_density",
        "moneyflow_score",
        "heat_score",
        "heat_momentum1",
        "heat_momentum3",
        "heat_rank",
        "rank_change",
        "lifecycle",
    ]
    output = grouped[(grouped["trade_date"] >= start) & (grouped["trade_date"] <= end)].copy()
    return output[columns].replace({np.nan: None})
