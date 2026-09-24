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
    lifecycle_watch: float = 40
    lifecycle_starting: float = 55
    lifecycle_heating: float = 60
    lifecycle_divergence_min_heat: float = 70
    lifecycle_main_up: float = 75
    lifecycle_climax: float = 90
    min_data_coverage: float = 0.50

    @classmethod
    def from_configs(cls, strategy: dict[str, Any], opportunity: dict[str, Any]) -> "ThemeConfig":
        theme = opportunity.get("theme", {})
        lifecycle = theme.get("lifecycle", {})
        return cls(
            benchmark_code=strategy.get("benchmark", {}).get("primary", "000300.SH"),
            min_member_count=int(theme.get("min_member_count", 5)),
            weights={key: float(value) for key, value in theme.get("heat_weights", {}).items()},
            lifecycle_watch=float(lifecycle.get("watch", 40)),
            lifecycle_starting=float(lifecycle.get("starting", 55)),
            lifecycle_heating=float(lifecycle.get("heating", 60)),
            lifecycle_divergence_min_heat=float(lifecycle.get("divergence_min_heat", 70)),
            lifecycle_main_up=float(lifecycle.get("main_up", 75)),
            lifecycle_climax=float(lifecycle.get("climax", 90)),
            min_data_coverage=float(theme.get("min_data_coverage", 0.50)),
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
    market_trade_dates: list[date] | None = None,
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
    snapshots = pd.DataFrame({"member_snapshot_date": sorted(valid_snapshots)})
    trade_dates = pd.DataFrame({"trade_date": sorted(daily["trade_date"].unique())})
    assignment = (
        pd.merge_asof(
            trade_dates.assign(_merge_date=pd.to_datetime(trade_dates["trade_date"])),
            snapshots.assign(
                _merge_date=pd.to_datetime(snapshots["member_snapshot_date"])
            ),
            on="_merge_date",
            direction="backward",
        ).drop(columns="_merge_date")
        if not snapshots.empty
        else pd.DataFrame(columns=["trade_date", "member_snapshot_date"])
    )
    member_values = (
        members.rename(columns={"snapshot_date": "member_snapshot_date"})
        if not members.empty
        else pd.DataFrame(columns=["member_snapshot_date", "theme_code", "ts_code"])
    )
    expanded = (
        daily[["trade_date", "theme_code"]]
        .drop_duplicates()
        .merge(assignment, on="trade_date", how="left")
        .merge(
            member_values[["member_snapshot_date", "theme_code", "ts_code"]],
            on=["member_snapshot_date", "theme_code"],
            how="inner",
        )
        .merge(factor_df, on=["trade_date", "ts_code"], how="left")
    )
    group_keys = ["trade_date", "theme_code", "member_snapshot_date"]
    if expanded.empty:
        breadth = pd.DataFrame()
    else:
        counts = (
            expanded.groupby(group_keys, as_index=False)["ts_code"]
            .nunique()
            .rename(columns={"ts_code": "member_count"})
        )
        eligible = expanded[expanded["eligible"].fillna(False)].copy()
        if eligible.empty:
            breadth = counts
            breadth["eligible_member_count"] = 0
            for column in (
                "breadth20",
                "breadth60",
                "up_rate",
                "new_high20_rate",
                "rps60_median",
            ):
                breadth[column] = np.nan
        else:
            eligible["above_ma20"] = eligible["adj_close"] > eligible["ma20"]
            eligible["above_ma60"] = eligible["adj_close"] > eligible["ma60"]
            eligible["up"] = eligible["return1"] > 0
            eligible["new_high20"] = eligible["breakout20"].fillna(False)
            metrics = eligible.groupby(group_keys, as_index=False).agg(
                eligible_member_count=("ts_code", "nunique"),
                breadth20=("above_ma20", "mean"),
                breadth60=("above_ma60", "mean"),
                up_rate=("up", "mean"),
                new_high20_rate=("new_high20", "mean"),
                rps60_median=("rps60", "median"),
            )
            breadth = counts.merge(metrics, on=group_keys, how="left")
            breadth["eligible_member_count"] = breadth["eligible_member_count"].fillna(0)
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
        daily,
        moneyflow,
        limits,
        moneyflow_pass_dates,
        limit_pass_dates,
        market_trade_dates or sorted(daily["trade_date"].unique()),
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
    total_weight = sum(config.weights.values())
    daily["data_coverage"] = available / total_weight if total_weight else 0.0
    daily["heat_score"] = (weighted / available.replace(0, np.nan)).where(
        daily["data_coverage"] >= config.min_data_coverage
    )
    daily["heat_rank"] = daily.groupby("trade_date")["heat_score"].rank(
        method="first", ascending=False
    )
    group = daily.groupby("theme_code", group_keys=False)
    daily["heat_momentum1"] = group["heat_score"].transform(lambda value: value - value.shift(1))
    daily["heat_momentum3"] = group["heat_score"].transform(lambda value: value - value.shift(3))
    daily["prev_heat"] = group["heat_score"].shift(1)
    daily["prev_rank"] = group["heat_rank"].shift(1)
    daily["rank_change"] = daily["prev_rank"] - daily["heat_rank"]
    daily["lifecycle"] = daily.apply(lambda row: _lifecycle(row, config), axis=1)
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
    market_trade_dates: list[date],
) -> pd.DataFrame:
    if not moneyflow.empty:
        flow = moneyflow.copy()
        flow["trade_date"] = pd.to_datetime(flow["trade_date"]).dt.date
        flow = flow[flow["trade_date"].isin(moneyflow_pass_dates)].copy()
        flow = flow.sort_values(["theme_code", "trade_date"])
        positions = {trade_date: index for index, trade_date in enumerate(market_trade_dates)}
        flow["market_position"] = flow["trade_date"].map(positions)
        grouped = flow.groupby("theme_code")
        previous_position = grouped["market_position"].shift(1)
        first_position = grouped["market_position"].shift(2)
        flow["net_amount_3d"] = (
            flow["net_amount"]
            + grouped["net_amount"].shift(1)
            + grouped["net_amount"].shift(2)
        ).where(
            (flow["market_position"] - previous_position == 1)
            & (flow["market_position"] - first_position == 2)
        )
        flow["net_amount_per_member"] = flow["net_amount"] / flow["company_num"].clip(lower=1)
        for column in ("net_amount", "net_amount_3d", "net_amount_per_member"):
            flow[f"{column}_rank"] = _rank(flow[column], flow["trade_date"])
        components = {
            "net_amount_rank": 0.50,
            "net_amount_3d_rank": 0.30,
            "net_amount_per_member_rank": 0.20,
        }
        weighted = sum(flow[column].fillna(0) * weight for column, weight in components.items())
        available = sum(
            flow[column].notna().astype(float) * weight
            for column, weight in components.items()
        )
        flow["moneyflow_score"] = weighted / available.replace(0, np.nan)
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
    hot_rank_score = (
        daily.groupby("trade_date")["hot_rank"]
        .rank(pct=True, ascending=False, method="average")
        .mul(100)
        .fillna(0)
    )
    daily["limit_strength_score"] = (
        0.50 * density_rank + 0.30 * continuous_rank + 0.20 * hot_rank_score
    )
    daily["_limit_density_pct"] = density_rank
    return daily


def _lifecycle(row: pd.Series, config: ThemeConfig) -> str | None:
    heat = row.get("heat_score")
    if heat is None or pd.isna(heat):
        return None
    momentum = row.get("heat_momentum3")
    momentum = 0 if pd.isna(momentum) else float(momentum)
    if heat >= config.lifecycle_climax and (
        (row.get("breadth20", 0) or 0) >= 0.80 or (row.get("_limit_density_pct", 0) or 0) >= 90
    ):
        return "CLIMAX"
    if heat >= config.lifecycle_divergence_min_heat and momentum <= -8:
        return "DIVERGENCE"
    if heat >= config.lifecycle_main_up and momentum >= 0:
        return "MAIN_UP"
    if heat >= config.lifecycle_heating and momentum > 5:
        return "HEATING"
    if (
        not pd.isna(row.get("prev_heat"))
        and row["prev_heat"] < config.lifecycle_starting <= heat
        and momentum >= 10
    ):
        return "STARTING"
    if config.lifecycle_watch <= heat < config.lifecycle_heating:
        return "WATCH"
    if heat < config.lifecycle_heating and momentum < 0:
        return "COOLING"
    return "COLD" if heat < config.lifecycle_watch else "WATCH"
