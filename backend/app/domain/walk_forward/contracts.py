from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class WindowPlan:
    window_no: int
    train_trade_dates: tuple[date, ...]
    test_trade_dates: tuple[date, ...]
    train_date_hash: str
    test_date_hash: str

    @property
    def train_start_date(self) -> date:
        return self.train_trade_dates[0]

    @property
    def train_end_date(self) -> date:
        return self.train_trade_dates[-1]

    @property
    def test_start_date(self) -> date:
        return self.test_trade_dates[0]

    @property
    def test_end_date(self) -> date:
        return self.test_trade_dates[-1]


@dataclass(frozen=True)
class WindowPlanResult:
    windows: tuple[WindowPlan, ...]
    unused_tail_trade_days: int


@dataclass(frozen=True)
class DailyReturnPoint:
    trade_date: date
    strategy_return: Decimal
    benchmark_return: Decimal


@dataclass(frozen=True)
class WindowMetricInput:
    window_no: int
    selected_parameter_hash: str
    selected_parameter_values: dict[str, Any]
    daily_returns: tuple[DailyReturnPoint, ...]
    train_annualized_return: Decimal
    train_max_drawdown_abs: Decimal
    train_sharpe_ratio: Decimal | None
    train_annualized_turnover: Decimal
    oos_cumulative_return: Decimal
    oos_annualized_return: Decimal
    oos_max_drawdown_abs: Decimal
    oos_sharpe_ratio: Decimal | None
    oos_annualized_turnover: Decimal
    oos_total_cost_to_initial_capital: Decimal
    oos_win_rate: Decimal | None
    oos_profit_factor: Decimal | None


@dataclass(frozen=True)
class WindowMetricResult:
    window_no: int
    train_annualized_return: Decimal
    train_max_drawdown_abs: Decimal
    train_sharpe_ratio: Decimal | None
    train_annualized_turnover: Decimal
    oos_cumulative_return: Decimal
    oos_annualized_return: Decimal
    oos_max_drawdown_abs: Decimal
    oos_sharpe_ratio: Decimal | None
    oos_annualized_turnover: Decimal
    oos_total_cost_to_initial_capital: Decimal
    oos_win_rate: Decimal | None
    oos_profit_factor: Decimal | None
    return_degradation: Decimal
    sharpe_degradation: Decimal | None
    drawdown_worsening: Decimal
    turnover_change: Decimal


@dataclass(frozen=True)
class StitchedDailyPoint:
    trade_date: date
    strategy_return: Decimal
    benchmark_return: Decimal
    strategy_nav: Decimal
    benchmark_nav: Decimal
    relative_nav: Decimal


@dataclass(frozen=True)
class ValidationMetrics:
    window_count: int
    total_oos_trade_days: int
    stitched_oos_final_nav: Decimal
    stitched_oos_cumulative_return: Decimal
    stitched_oos_annualized_return: Decimal
    stitched_oos_max_drawdown: Decimal
    stitched_oos_annualized_volatility: Decimal | None
    stitched_oos_sharpe_ratio: Decimal | None
    stitched_benchmark_final_nav: Decimal
    stitched_benchmark_cumulative_return: Decimal
    stitched_excess_cumulative_return: Decimal
    positive_oos_window_count: int
    positive_oos_window_rate: Decimal
    mean_oos_annualized_return: Decimal
    median_oos_annualized_return: Decimal
    mean_return_degradation: Decimal
    median_return_degradation: Decimal
    mean_drawdown_worsening: Decimal
    median_drawdown_worsening: Decimal
    warnings: tuple[str, ...]
    stitched_daily: tuple[StitchedDailyPoint, ...]
    windows: tuple[WindowMetricResult, ...]
