from decimal import Decimal, localcontext

from app.domain.performance.metrics import annualized_return
from app.domain.performance.statistics import mean, sample_stddev
from app.domain.walk_forward.contracts import (
    StitchedDailyPoint,
    ValidationMetrics,
    WindowMetricInput,
    WindowMetricResult,
)

ONE = Decimal("1")
ZERO = Decimal("0")


def _median(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("median requires at least one observation")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _max_drawdown(values: tuple[Decimal, ...]) -> Decimal:
    nav = ONE
    peak = ONE
    worst = ZERO
    for value in values:
        nav *= ONE + value
        peak = max(peak, nav)
        worst = min(worst, nav / peak - ONE)
    return worst


def _risk_free_daily(annual: Decimal, annualization_trade_days: int) -> Decimal:
    if annual <= -ONE:
        raise ValueError("risk-free annual rate must be greater than -1")
    with localcontext() as context:
        context.prec = 60
        return ((ONE + annual).ln() / Decimal(annualization_trade_days)).exp() - ONE


def calculate_validation_metrics(
    windows: tuple[WindowMetricInput, ...],
    *,
    annualization_trade_days: int,
    risk_free_rate_annual: Decimal,
    minimum_observations: int,
    short_sample_warning_trade_days: int,
) -> ValidationMetrics:
    if not windows:
        raise ValueError("walk-forward validation requires at least one window")
    if tuple(sorted(row.window_no for row in windows)) != tuple(
        row.window_no for row in windows
    ):
        raise ValueError("walk-forward windows must be sorted")
    points = tuple(point for window in windows for point in window.daily_returns)
    dates = tuple(point.trade_date for point in points)
    if len(set(dates)) != len(dates) or tuple(sorted(dates)) != dates:
        raise ValueError("stitched OOS dates must be unique and strictly increasing")
    if len(points) < minimum_observations:
        raise ValueError("stitched OOS sample is too short")
    strategy = tuple(point.strategy_return for point in points)
    strategy_nav = ONE
    benchmark_nav = ONE
    stitched_daily: list[StitchedDailyPoint] = []
    for point in points:
        if point.strategy_return <= -ONE or point.benchmark_return <= -ONE:
            raise ValueError("daily return must be greater than -1")
        strategy_nav *= ONE + point.strategy_return
        benchmark_nav *= ONE + point.benchmark_return
        stitched_daily.append(
            StitchedDailyPoint(
                trade_date=point.trade_date,
                strategy_return=point.strategy_return,
                benchmark_return=point.benchmark_return,
                strategy_nav=strategy_nav,
                benchmark_nav=benchmark_nav,
                relative_nav=strategy_nav / benchmark_nav,
            )
        )
    volatility = sample_stddev(strategy) * Decimal(annualization_trade_days).sqrt()
    warnings: set[str] = set()
    if len(points) < short_sample_warning_trade_days:
        warnings.add("SHORT_STITCHED_OOS_SAMPLE")
    if any(
        row.train_sharpe_ratio is None
        or row.oos_sharpe_ratio is None
        or row.oos_win_rate is None
        or row.oos_profit_factor is None
        for row in windows
    ):
        warnings.add("NULL_OOS_OPTIONAL_METRICS_PRESENT")
    rf_daily = _risk_free_daily(risk_free_rate_annual, annualization_trade_days)
    if volatility == ZERO:
        sharpe = None
        warnings.add("ZERO_STITCHED_OOS_VOLATILITY")
    else:
        sharpe = (
            mean(tuple(value - rf_daily for value in strategy))
            / sample_stddev(strategy)
            * Decimal(annualization_trade_days).sqrt()
        )

    results = tuple(
        WindowMetricResult(
            window_no=row.window_no,
            train_annualized_return=row.train_annualized_return,
            train_max_drawdown_abs=row.train_max_drawdown_abs,
            train_sharpe_ratio=row.train_sharpe_ratio,
            train_annualized_turnover=row.train_annualized_turnover,
            oos_cumulative_return=row.oos_cumulative_return,
            oos_annualized_return=row.oos_annualized_return,
            oos_max_drawdown_abs=row.oos_max_drawdown_abs,
            oos_sharpe_ratio=row.oos_sharpe_ratio,
            oos_annualized_turnover=row.oos_annualized_turnover,
            oos_total_cost_to_initial_capital=(
                row.oos_total_cost_to_initial_capital
            ),
            oos_win_rate=row.oos_win_rate,
            oos_profit_factor=row.oos_profit_factor,
            return_degradation=(
                row.train_annualized_return - row.oos_annualized_return
            ),
            sharpe_degradation=(
                row.train_sharpe_ratio - row.oos_sharpe_ratio
                if row.train_sharpe_ratio is not None
                and row.oos_sharpe_ratio is not None
                else None
            ),
            drawdown_worsening=(
                row.oos_max_drawdown_abs - row.train_max_drawdown_abs
            ),
            turnover_change=(
                row.oos_annualized_turnover - row.train_annualized_turnover
            ),
        )
        for row in windows
    )
    if any(row.sharpe_degradation is None for row in results):
        warnings.add("TRAIN_OOS_OPTIONAL_METRIC_NOT_COMPARABLE")
    oos_returns = tuple(row.oos_annualized_return for row in results)
    return_degradations = tuple(row.return_degradation for row in results)
    drawdown_worsenings = tuple(row.drawdown_worsening for row in results)
    positive = sum(row.oos_cumulative_return > ZERO for row in results)
    return ValidationMetrics(
        window_count=len(results),
        total_oos_trade_days=len(points),
        stitched_oos_final_nav=strategy_nav,
        stitched_oos_cumulative_return=strategy_nav - ONE,
        stitched_oos_annualized_return=annualized_return(
            strategy_nav,
            trade_days=len(points),
            annualization_trade_days=annualization_trade_days,
        ),
        stitched_oos_max_drawdown=_max_drawdown(strategy),
        stitched_oos_annualized_volatility=volatility,
        stitched_oos_sharpe_ratio=sharpe,
        stitched_benchmark_final_nav=benchmark_nav,
        stitched_benchmark_cumulative_return=benchmark_nav - ONE,
        stitched_excess_cumulative_return=strategy_nav / benchmark_nav - ONE,
        positive_oos_window_count=positive,
        positive_oos_window_rate=Decimal(positive) / Decimal(len(results)),
        mean_oos_annualized_return=mean(oos_returns),
        median_oos_annualized_return=_median(oos_returns),
        mean_return_degradation=mean(return_degradations),
        median_return_degradation=_median(return_degradations),
        mean_drawdown_worsening=mean(drawdown_worsenings),
        median_drawdown_worsening=_median(drawdown_worsenings),
        warnings=tuple(sorted(warnings)),
        stitched_daily=tuple(stitched_daily),
        windows=results,
    )
