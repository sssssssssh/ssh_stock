from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ThemeConfig:
    benchmark_code: str
    min_member_count: int
    weights: dict[str, float]

    @classmethod
    def from_configs(cls, strategy: dict[str, Any], opportunity: dict[str, Any]) -> "ThemeConfig":
        theme = opportunity.get("theme", {})
        return cls(
            benchmark_code=strategy.get("benchmark", {}).get("primary", "000300.SH"),
            min_member_count=int(theme.get("min_member_count", 5)),
            weights={key: float(value) for key, value in theme.get("heat_weights", {}).items()},
        )


def _rank(series: pd.Series, dates: pd.Series) -> pd.Series:
    return series.groupby(dates).rank(pct=True, method="average") * 100


def _latest_snapshot_members(
    members: pd.DataFrame,
    valid_snapshots: set[date],
    trade_date: date,
) -> tuple[date | None, pd.DataFrame]:
    candidates = [value for value in valid_snapshots if value <= trade_date]
    if not candidates or members.empty:
        return None, pd.DataFrame()
    snapshot = max(candidates)
    return snapshot, members[members["snapshot_date"] == snapshot]


def calculate_theme_factors(
    theme_daily: pd.DataFrame,
    members: pd.DataFrame,
    factors: pd.DataFrame,
    index_daily: pd.DataFrame,
    moneyflow: pd.DataFrame,
    limits: pd.DataFrame,
    valid_snapshots: set[date],
    moneyflow_pass_dates: set[date],
    limit_pass_dates: set[date],
    start: date,
    end: date,
    config: ThemeConfig,
) -> pd.DataFrame:
    if theme_daily.empty:
        return pd.DataFrame()
    daily = theme_daily.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"]).dt.date
    daily = daily.sort_values(["theme_code", "trade_date"])
    by_theme = daily.groupby("theme_code", group_keys=False)
    for horizon in (1, 3, 5, 20):
        daily[f"return{horizon}"] = by_theme["close"].transform(
            lambda values, h=horizon: values / values.shift(h) - 1
        )
    daily["turnover_ratio20"] = by_theme["turnover_rate"].transform(
        lambda values: values / values.rolling(20, min_periods=5).mean()
    )

    benchmark = (
        index_daily[index_daily["ts_code"] == config.benchmark_code].copy()
        if "ts_code" in index_daily.columns
        else pd.DataFrame()
    )
    if not benchmark.empty:
        benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"]).dt.date
        benchmark = benchmark.sort_values("trade_date")
        benchmark["benchmark_return5"] = benchmark["close"] / benchmark["close"].shift(5) - 1
        benchmark["benchmark_return20"] = benchmark["close"] / benchmark["close"].shift(20) - 1
        daily = daily.merge(
            benchmark[["trade_date", "benchmark_return5", "benchmark_return20"]],
            on="trade_date",
            how="left",
        )
    else:
        daily["benchmark_return5"] = np.nan
        daily["benchmark_return20"] = np.nan
    daily["excess_return5"] = daily["return5"] - daily["benchmark_return5"]
    daily["excess_return20"] = daily["return20"] - daily["benchmark_return20"]

    factor_df = factors.copy()
    if not factor_df.empty:
        factor_df["trade_date"] = pd.to_datetime(factor_df["trade_date"]).dt.date
    else:
        factor_df = pd.DataFrame(
            columns=[
                "trade_date",
                "ts_code",
                "eligible",
                "adj_close",
                "ma20",
                "ma60",
                "return1",
                "breakout20",
                "rps60",
            ]
        )
    if not members.empty:
        members = members.copy()
        members["snapshot_date"] = pd.to_datetime(members["snapshot_date"]).dt.date
    breadth_rows = []
    for trade_date in sorted(daily["trade_date"].unique()):
        snapshot_date, snapshot_members = _latest_snapshot_members(
            members, valid_snapshots, trade_date
        )
        if snapshot_date is None:
            continue
        day_factors = factor_df[
            (factor_df["trade_date"] == trade_date) & factor_df["eligible"].fillna(False)
        ]
        merged = snapshot_members.merge(day_factors, on="ts_code", how="left")
        for theme_code, group in merged.groupby("theme_code"):
            eligible = group[group["eligible"].fillna(False)]
            breadth_rows.append(
                {
                    "trade_date": trade_date,
                    "theme_code": theme_code,
                    "member_snapshot_date": snapshot_date,
                    "member_count": int(group["ts_code"].nunique()),
                    "eligible_member_count": int(eligible["ts_code"].nunique()),
                    "breadth20": (eligible["adj_close"] > eligible["ma20"]).mean()
                    if not eligible.empty
                    else None,
                    "breadth60": (eligible["adj_close"] > eligible["ma60"]).mean()
                    if not eligible.empty
                    else None,
                    "up_rate": (eligible["return1"] > 0).mean() if not eligible.empty else None,
                    "new_high20_rate": eligible["breakout20"].fillna(False).mean()
                    if not eligible.empty
                    else None,
                    "rps60_median": eligible["rps60"].median() if not eligible.empty else None,
                }
            )
    breadth = pd.DataFrame(breadth_rows)
    if not breadth.empty:
        daily = daily.merge(breadth, on=["trade_date", "theme_code"], how="left")
    else:
        for column in (
            "member_snapshot_date",
            "member_count",
            "eligible_member_count",
            "breadth20",
            "breadth60",
            "up_rate",
            "new_high20_rate",
            "rps60_median",
        ):
            daily[column] = np.nan
    insufficient_members = daily["eligible_member_count"].fillna(0) < config.min_member_count
    daily.loc[
        insufficient_members,
        ["breadth20", "breadth60", "up_rate", "new_high20_rate", "rps60_median"],
    ] = np.nan

    daily = _merge_optional_sources(
        daily, moneyflow, limits, moneyflow_pass_dates, limit_pass_dates
    )
    inputs = list(config.weights)
    for column in inputs:
        daily[f"{column}_pct"] = _rank(daily[column], daily["trade_date"])
    weighted = pd.Series(0.0, index=daily.index)
    available = pd.Series(0.0, index=daily.index)
    for column, weight in config.weights.items():
        values = daily[f"{column}_pct"]
        weighted += values.fillna(0) * weight
        available += values.notna().astype(float) * weight
    daily["data_coverage"] = available
    daily["heat_score"] = (weighted / available.replace(0, np.nan)).where(available >= 0.50)
    daily["heat_rank"] = daily.groupby("trade_date")["heat_score"].rank(
        method="first", ascending=False
    )
    group = daily.groupby("theme_code", group_keys=False)
    daily["heat_momentum1"] = group["heat_score"].transform(lambda value: value - value.shift(1))
    daily["heat_momentum3"] = group["heat_score"].transform(lambda value: value - value.shift(3))
    daily["prev_heat"] = group["heat_score"].shift(1)
    daily["prev_rank"] = group["heat_rank"].shift(1)
    daily["rank_change"] = daily["prev_rank"] - daily["heat_rank"]
    daily["lifecycle"] = daily.apply(_lifecycle, axis=1)
    output = daily[(daily["trade_date"] >= start) & (daily["trade_date"] <= end)].copy()
    columns = [
        "trade_date",
        "theme_code",
        "member_snapshot_date",
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
        "turnover_rate",
        "turnover_ratio20",
        "net_amount",
        "net_amount_3d",
        "net_amount_per_member",
        "moneyflow_score",
        "limit_up_count",
        "limit_up_density",
        "continuous_limit_count",
        "continuous_limit_density",
        "hot_list_days",
        "hot_rank",
        "limit_strength_score",
        "heat_score",
        "heat_rank",
        "heat_momentum1",
        "heat_momentum3",
        "rank_change",
        "lifecycle",
        "data_coverage",
    ]
    return output[columns].replace({np.nan: None})


def _merge_optional_sources(
    daily: pd.DataFrame,
    moneyflow: pd.DataFrame,
    limits: pd.DataFrame,
    moneyflow_pass_dates: set[date],
    limit_pass_dates: set[date],
) -> pd.DataFrame:
    if not moneyflow.empty:
        flow = moneyflow.copy()
        flow["trade_date"] = pd.to_datetime(flow["trade_date"]).dt.date
        flow = flow.sort_values(["theme_code", "trade_date"])
        flow["net_amount_3d"] = flow.groupby("theme_code")["net_amount"].transform(
            lambda value: value.rolling(3, min_periods=1).sum()
        )
        flow["net_amount_per_member"] = flow["net_amount"] / flow["company_num"].clip(lower=1)
        for column in ("net_amount", "net_amount_3d", "net_amount_per_member"):
            flow[f"{column}_rank"] = _rank(flow[column], flow["trade_date"])
        flow["moneyflow_score"] = (
            0.50 * flow["net_amount_rank"]
            + 0.30 * flow["net_amount_3d_rank"]
            + 0.20 * flow["net_amount_per_member_rank"]
        )
        daily = daily.merge(
            flow[
                [
                    "trade_date",
                    "theme_code",
                    "net_amount",
                    "net_amount_3d",
                    "net_amount_per_member",
                    "moneyflow_score",
                    "company_num",
                ]
            ],
            on=["trade_date", "theme_code"],
            how="left",
        )
    else:
        for column in (
            "net_amount",
            "net_amount_3d",
            "net_amount_per_member",
            "moneyflow_score",
            "company_num",
        ):
            daily[column] = np.nan
    for index in daily.index:
        if daily.at[index, "trade_date"] not in moneyflow_pass_dates:
            daily.loc[
                index, ["net_amount", "net_amount_3d", "net_amount_per_member", "moneyflow_score"]
            ] = np.nan

    limit_columns = [
        "limit_up_count",
        "continuous_limit_count",
        "hot_list_days",
        "hot_rank",
    ]
    if not limits.empty:
        limit_df = limits.copy()
        limit_df["trade_date"] = pd.to_datetime(limit_df["trade_date"]).dt.date
        limit_df = limit_df.rename(
            columns={
                "up_nums": "limit_up_count",
                "cons_nums": "continuous_limit_count",
                "days": "hot_list_days",
            }
        )
        daily = daily.merge(
            limit_df[["trade_date", "theme_code", *limit_columns]],
            on=["trade_date", "theme_code"],
            how="left",
        )
    else:
        for column in limit_columns:
            daily[column] = np.nan
    for index in daily.index:
        current = daily.at[index, "trade_date"]
        if current in limit_pass_dates:
            daily.loc[index, ["limit_up_count", "continuous_limit_count"]] = daily.loc[
                index, ["limit_up_count", "continuous_limit_count"]
            ].fillna(0)
        else:
            daily.loc[index, limit_columns] = np.nan
    denominator = daily["company_num"].where(daily["company_num"].notna(), daily["member_count"])
    daily["limit_up_density"] = daily["limit_up_count"] / denominator.replace(0, np.nan)
    daily["continuous_limit_density"] = daily["continuous_limit_count"] / denominator.replace(
        0, np.nan
    )
    density_rank = _rank(daily["limit_up_density"], daily["trade_date"])
    continuous_rank = _rank(daily["continuous_limit_density"], daily["trade_date"])
    hot_rank_score = (100 - _rank(daily["hot_rank"], daily["trade_date"])).fillna(0)
    daily["limit_strength_score"] = (
        0.50 * density_rank + 0.30 * continuous_rank + 0.20 * hot_rank_score
    )
    daily["_limit_density_pct"] = density_rank
    return daily


def _lifecycle(row: pd.Series) -> str | None:
    heat = row.get("heat_score")
    if heat is None or pd.isna(heat):
        return None
    momentum = row.get("heat_momentum3")
    momentum = 0 if pd.isna(momentum) else float(momentum)
    if heat >= 90 and (
        (row.get("breadth20", 0) or 0) >= 0.80 or (row.get("_limit_density_pct", 0) or 0) >= 90
    ):
        return "CLIMAX"
    if heat >= 70 and momentum <= -8:
        return "DIVERGENCE"
    if heat >= 75 and momentum >= 0:
        return "MAIN_UP"
    if heat >= 60 and momentum > 5:
        return "HEATING"
    if not pd.isna(row.get("prev_heat")) and row["prev_heat"] < 55 <= heat and momentum >= 10:
        return "STARTING"
    if 40 <= heat < 60:
        return "WATCH"
    if heat < 60 and momentum < 0:
        return "COOLING"
    return "COLD" if heat < 40 else "WATCH"
