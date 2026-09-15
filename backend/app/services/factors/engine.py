from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.services.universe import is_stock_active_on


@dataclass(frozen=True)
class FactorConfig:
    ma_windows: tuple[int, ...] = (5, 10, 20, 60, 120, 250)
    return_windows: tuple[int, ...] = (1, 3, 5, 20, 60, 120, 250)
    rps_windows: tuple[int, ...] = (20, 60, 120, 250)
    atr_window: int = 20
    min_listed_trading_days: int = 120
    min_avg_amount_20_cny: float = 50_000_000
    min_close: float | None = 2.0
    exclude_st: bool = True

    @classmethod
    def from_strategy(cls, strategy: dict[str, Any]) -> "FactorConfig":
        factor = strategy.get("factor", {})
        universe = strategy.get("universe", {})
        return cls(
            ma_windows=tuple(factor.get("ma_windows", cls.ma_windows)),
            return_windows=tuple(factor.get("return_windows", cls.return_windows)),
            rps_windows=tuple(factor.get("rps_windows", cls.rps_windows)),
            atr_window=int(factor.get("atr_window", cls.atr_window)),
            min_listed_trading_days=int(
                universe.get("min_listed_trading_days", cls.min_listed_trading_days)
            ),
            min_avg_amount_20_cny=float(
                universe.get("min_avg_amount_20_cny", cls.min_avg_amount_20_cny)
            ),
            min_close=universe.get("min_close", cls.min_close),
            exclude_st=bool(universe.get("exclude_st", cls.exclude_st)),
        )


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.divide(denominator.replace(0, np.nan))


def _max_drawdown(values: pd.Series) -> float:
    if values.isna().any() or values.empty:
        return np.nan
    peak = values.cummax()
    drawdown = values / peak - 1
    return float(drawdown.min())


def _reason_join(reasons: list[str]) -> str | None:
    return ",".join(reasons) if reasons else None


def _assign_eligibility(df: pd.DataFrame, config: FactorConfig) -> pd.DataFrame:
    listed_days = df.groupby("ts_code").cumcount() + 1
    reasons: list[list[str]] = [[] for _ in range(len(df.index))]

    if config.exclude_st and "is_st" in df.columns:
        st_mask = df["is_st"].eq(True)
        for idx in np.flatnonzero(st_mask.to_numpy()):
            reasons[idx].append("ST")

    if "is_suspended" in df.columns:
        suspended_mask = df["is_suspended"].eq(True)
        for idx in np.flatnonzero(suspended_mask.to_numpy()):
            reasons[idx].append("SUSPENDED")

    if "st_status_unknown" in df.columns:
        unknown_mask = df["st_status_unknown"].eq(True)
        for idx in np.flatnonzero(unknown_mask.to_numpy()):
            reasons[idx].append("ST_STATUS_UNKNOWN")

    if config.exclude_st and "trade_status_present" in df.columns:
        missing_status_mask = ~df["trade_status_present"]
        for idx in np.flatnonzero(missing_status_mask.to_numpy()):
            reasons[idx].append("TRADE_STATUS_MISSING")

    active_mask = df.apply(
        lambda row: is_stock_active_on(
            row.get("list_date"),
            row.get("delist_date"),
            row["trade_date"],
        ),
        axis=1,
    )
    if "is_active" in df.columns:
        active_mask = df["is_active"].where(df["trade_status_present"], active_mask)
    inactive_mask = ~active_mask.astype(bool)
    for idx in np.flatnonzero(inactive_mask.to_numpy()):
        reasons[idx].append("NOT_ACTIVE_ON_DATE")

    young_mask = listed_days < config.min_listed_trading_days
    for idx in np.flatnonzero(young_mask.to_numpy()):
        reasons[idx].append("LISTED_DAYS_LT_MIN")

    if config.min_close is not None:
        low_price_mask = df["close"] < float(config.min_close)
        for idx in np.flatnonzero(low_price_mask.fillna(True).to_numpy()):
            reasons[idx].append("CLOSE_LT_MIN")

    # Tushare daily.amount unit is commonly thousand CNY; config is CNY.
    amount_cny = df["amount_ma20"] * 1000
    low_amount_mask = amount_cny < config.min_avg_amount_20_cny
    for idx in np.flatnonzero(low_amount_mask.fillna(True).to_numpy()):
        reasons[idx].append("AMOUNT20_LT_MIN")

    df["exclusion_reason"] = [_reason_join(item) for item in reasons]
    df["eligible"] = df["exclusion_reason"].isna()
    return df


def calculate_stock_factors(
    daily: pd.DataFrame,
    adj_factor: pd.DataFrame,
    stock_basic: pd.DataFrame | None,
    index_daily: pd.DataFrame | None,
    benchmark_code: str,
    start: date,
    end: date,
    config: FactorConfig,
    trade_status: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()

    df = daily.merge(adj_factor, on=["trade_date", "ts_code"], how="left")
    if stock_basic is not None and not stock_basic.empty:
        stock_basic = stock_basic.copy()
        stock_basic["list_date"] = pd.to_datetime(stock_basic["list_date"]).dt.date
        stock_basic["delist_date"] = pd.to_datetime(stock_basic["delist_date"]).dt.date
        df = df.merge(
            stock_basic[["ts_code", "list_date", "delist_date"]],
            on="ts_code",
            how="left",
        )
    else:
        df["list_date"] = None
        df["delist_date"] = None

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    if trade_status is not None and not trade_status.empty:
        status = trade_status.copy()
        status["trade_date"] = pd.to_datetime(status["trade_date"]).dt.date
        status["trade_status_present"] = True
        df = df.merge(
            status[
                [
                    "trade_date",
                    "ts_code",
                    "is_active",
                    "is_suspended",
                    "is_st",
                    "st_status_unknown",
                    "trade_status_present",
                ]
            ],
            on=["trade_date", "ts_code"],
            how="left",
        )
        df["trade_status_present"] = df["trade_status_present"].fillna(False)
    else:
        df["is_active"] = None
        df["is_suspended"] = None
        df["is_st"] = None
        df["st_status_unknown"] = None
        df["trade_status_present"] = False
    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    for col in ["open", "high", "low", "close"]:
        df[f"adj_{col}"] = df[col] * df["adj_factor"]

    group = df.groupby("ts_code", group_keys=False)
    for window in config.ma_windows:
        df[f"ma{window}"] = group["adj_close"].transform(
            lambda s, w=window: s.rolling(w, min_periods=w).mean()
        )

    for window in config.return_windows:
        df[f"return{window}"] = group["adj_close"].transform(lambda s, w=window: s / s.shift(w) - 1)

    df["ma20_slope5"] = group["ma20"].transform(lambda s: (s / s.shift(5) - 1) / 5)
    df["ma60_slope10"] = group["ma60"].transform(lambda s: (s / s.shift(10) - 1) / 10)

    prev_close = group["adj_close"].shift(1)
    tr = pd.concat(
        [
            df["adj_high"] - df["adj_low"],
            (df["adj_high"] - prev_close).abs(),
            (df["adj_low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr20"] = tr.groupby(df["ts_code"]).transform(
        lambda s: s.rolling(config.atr_window, min_periods=config.atr_window).mean()
    )
    df["atr20_pct"] = _safe_divide(df["atr20"], df["adj_close"])

    df["amount_ma20"] = group["amount"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["amount_ratio20"] = _safe_divide(df["amount"], df["amount_ma20"])

    for window in (20, 60, 120):
        df[f"prev_high{window}"] = group["adj_high"].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=w).max()
        )
    for window in (20, 60):
        df[f"low{window}"] = group["adj_low"].transform(
            lambda s, w=window: s.rolling(w, min_periods=w).min()
        )

    df["breakout20"] = df["adj_close"] > df["prev_high20"]
    df["breakout60"] = df["adj_close"] > df["prev_high60"]
    df["cross_above_ma20"] = (df["adj_close"] > df["ma20"]) & (
        group["adj_close"].shift(1) <= group["ma20"].shift(1)
    )
    df["cross_above_ma60"] = (df["adj_close"] > df["ma60"]) & (
        group["adj_close"].shift(1) <= group["ma60"].shift(1)
    )

    low20 = group["adj_low"].transform(lambda s: s.rolling(20, min_periods=20).min())
    prior_low40 = group["adj_low"].transform(
        lambda s: s.shift(20).rolling(40, min_periods=40).min()
    )
    df["higher_low"] = low20 > prior_low40
    df["higher_low_pct"] = low20 / prior_low40 - 1

    df["drawdown_high60"] = df["adj_close"] / group["adj_close"].transform(
        lambda s: s.rolling(60, min_periods=60).max()
    ) - 1
    df["drawdown_high120"] = df["adj_close"] / group["adj_close"].transform(
        lambda s: s.rolling(120, min_periods=120).max()
    ) - 1
    df["max_drawdown60"] = group["adj_close"].transform(
        lambda s: s.rolling(60, min_periods=60).apply(_max_drawdown, raw=False)
    )

    daily_abs_path = group["adj_close"].pct_change().abs()
    path20 = daily_abs_path.groupby(df["ts_code"]).transform(lambda s: s.rolling(20).sum())
    df["trend_efficiency20"] = _safe_divide(df["return20"].abs(), path20).clip(0, 1)

    df = _assign_eligibility(df, config)

    for window in config.rps_windows:
        ret_col = f"return{window}"
        rps_col = f"rps{window}"
        eligible_returns = df[ret_col].where(df["eligible"])
        df[rps_col] = (
            eligible_returns.groupby(df["trade_date"]).rank(pct=True, method="average") * 100
        )

    df["rps20_delta5"] = group["rps20"].transform(lambda s: s - s.shift(5))
    df["rps60_delta5"] = group["rps60"].transform(lambda s: s - s.shift(5))

    if index_daily is not None and not index_daily.empty:
        benchmark = index_daily[index_daily["ts_code"] == benchmark_code].copy()
        benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"]).dt.date
        benchmark = benchmark.sort_values("trade_date")
        benchmark["benchmark_return20"] = benchmark["close"] / benchmark["close"].shift(20) - 1
        benchmark["benchmark_return60"] = benchmark["close"] / benchmark["close"].shift(60) - 1
        df = df.merge(
            benchmark[["trade_date", "benchmark_return20", "benchmark_return60"]],
            on="trade_date",
            how="left",
        )
        df["relative_return20"] = df["return20"] - df["benchmark_return20"]
        df["relative_return60"] = df["return60"] - df["benchmark_return60"]
    else:
        df["relative_return20"] = np.nan
        df["relative_return60"] = np.nan

    output = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)].copy()
    columns = [
        "trade_date",
        "ts_code",
        "adj_open",
        "adj_high",
        "adj_low",
        "adj_close",
        "ma5",
        "ma10",
        "ma20",
        "ma60",
        "ma120",
        "ma250",
        "return1",
        "return3",
        "return5",
        "return20",
        "return60",
        "return120",
        "return250",
        "ma20_slope5",
        "ma60_slope10",
        "atr20",
        "atr20_pct",
        "amount_ma20",
        "amount_ratio20",
        "prev_high20",
        "prev_high60",
        "prev_high120",
        "low20",
        "low60",
        "breakout20",
        "breakout60",
        "cross_above_ma20",
        "cross_above_ma60",
        "higher_low",
        "higher_low_pct",
        "drawdown_high60",
        "drawdown_high120",
        "max_drawdown60",
        "trend_efficiency20",
        "rps20",
        "rps60",
        "rps120",
        "rps250",
        "rps20_delta5",
        "rps60_delta5",
        "relative_return20",
        "relative_return60",
        "eligible",
        "exclusion_reason",
    ]
    return output[columns].replace({np.nan: None})
