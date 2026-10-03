from decimal import ROUND_HALF_UP, Decimal, localcontext

from app.core.performance_risk_config import PerformanceRiskConfig
from app.domain.performance.metrics import annualized_return
from app.domain.performance.risk_contracts import (
    RiskDailyPoint,
    RiskResult,
    RiskSourceSnapshot,
)
from app.domain.performance.statistics import (
    mean,
    sample_covariance,
    sample_stddev,
    sample_variance,
)

ONE = Decimal("1")
ZERO = Decimal("0")
BENCHMARK_PRICE_QUANTUM = Decimal("0.0001")


class RiskEngine:
    def calculate(
        self, source: RiskSourceSnapshot, config: PerformanceRiskConfig
    ) -> RiskResult:
        if not source.rows or source.trade_days != len(source.rows):
            raise ValueError("risk source must contain the declared observations")
        if config.version != source.risk_version:
            raise ValueError("risk config version does not match source identity")

        with localcontext() as context:
            context.prec = 60
            annualization = Decimal(source.annualization_trade_days)
            sqrt_annualization = annualization.sqrt()
            rf_daily = self._daily_risk_free_rate(
                config.risk_free_rate_annual, source.annualization_trade_days
            )
            benchmark_nav = ONE
            previous_close: Decimal | None = None
            strategy_returns: list[Decimal] = []
            benchmark_returns: list[Decimal] = []
            active_returns: list[Decimal] = []
            daily: list[RiskDailyPoint] = []

            for row in source.rows:
                if row.strategy_nav <= ZERO:
                    raise ValueError("strategy NAV must be positive")
                reference_close = (
                    row.benchmark_pre_close
                    if previous_close is None
                    else previous_close
                )
                if reference_close <= ZERO or row.benchmark_close <= ZERO:
                    raise ValueError("benchmark prices must be positive")
                if (
                    previous_close is not None
                    and self._price(row.benchmark_pre_close)
                    != self._price(previous_close)
                ):
                    raise ValueError("BENCHMARK_PRE_CLOSE_MISMATCH")
                benchmark_return = row.benchmark_close / reference_close - ONE
                benchmark_nav *= ONE + benchmark_return
                active_return = row.strategy_daily_return - benchmark_return
                relative_nav = row.strategy_nav / benchmark_nav
                excess_cumulative_return = relative_nav - ONE
                strategy_returns.append(row.strategy_daily_return)
                benchmark_returns.append(benchmark_return)
                active_returns.append(active_return)
                daily.append(
                    RiskDailyPoint(
                        trade_date=row.trade_date,
                        benchmark_reference_close=reference_close,
                        benchmark_close=row.benchmark_close,
                        benchmark_daily_return=benchmark_return,
                        benchmark_nav=benchmark_nav,
                        active_return=active_return,
                        relative_nav=relative_nav,
                        excess_cumulative_return=excess_cumulative_return,
                    )
                )
                previous_close = row.benchmark_close

            benchmark_cumulative = benchmark_nav - ONE
            benchmark_annualized = annualized_return(
                benchmark_nav,
                trade_days=source.trade_days,
                annualization_trade_days=source.annualization_trade_days,
            )
            warnings: set[str] = set()
            if source.trade_days < config.short_sample_warning_trade_days:
                warnings.add("RISK_SHORT_SAMPLE")

            calmar: Decimal | None
            if abs(source.strategy_max_drawdown) <= config.zero_denominator_epsilon:
                calmar = None
                warnings.add("ZERO_MAX_DRAWDOWN")
            else:
                calmar = source.strategy_annualized_return / abs(
                    source.strategy_max_drawdown
                )

            strategy_volatility: Decimal | None = None
            benchmark_volatility: Decimal | None = None
            downside_annualized: Decimal | None = None
            sharpe: Decimal | None = None
            sortino: Decimal | None = None
            tracking_error: Decimal | None = None
            information_ratio: Decimal | None = None
            alpha_daily: Decimal | None = None
            alpha_annualized: Decimal | None = None
            beta: Decimal | None = None
            correlation: Decimal | None = None

            if source.trade_days < config.minimum_observations:
                warnings.add("INSUFFICIENT_RISK_OBSERVATIONS")
            else:
                strategy_values = tuple(strategy_returns)
                benchmark_values = tuple(benchmark_returns)
                active_values = tuple(active_returns)
                strategy_std = sample_stddev(strategy_values)
                benchmark_std = sample_stddev(benchmark_values)
                active_std = sample_stddev(active_values)
                strategy_volatility = strategy_std * sqrt_annualization
                benchmark_volatility = benchmark_std * sqrt_annualization
                tracking_error = active_std * sqrt_annualization

                excess_rf = tuple(value - rf_daily for value in strategy_values)
                downside_values = tuple(min(value, ZERO) for value in excess_rf)
                downside_daily = (
                    sum((value * value for value in downside_values), ZERO)
                    / Decimal(source.trade_days)
                ).sqrt()
                downside_annualized = downside_daily * sqrt_annualization

                if strategy_std <= config.zero_denominator_epsilon:
                    warnings.add("ZERO_STRATEGY_VOLATILITY")
                else:
                    sharpe = mean(excess_rf) / strategy_std * sqrt_annualization

                if benchmark_std <= config.zero_denominator_epsilon:
                    warnings.add("ZERO_BENCHMARK_VOLATILITY")

                if downside_daily <= config.zero_denominator_epsilon:
                    warnings.add("ZERO_DOWNSIDE_DEVIATION")
                else:
                    sortino = mean(excess_rf) / downside_daily * sqrt_annualization

                if active_std <= config.zero_denominator_epsilon:
                    warnings.add("ZERO_TRACKING_ERROR")
                else:
                    information_ratio = (
                        mean(active_values) / active_std * sqrt_annualization
                    )

                benchmark_variance = sample_variance(benchmark_values)
                covariance = sample_covariance(strategy_values, benchmark_values)
                if benchmark_variance <= config.zero_denominator_epsilon:
                    warnings.add("ZERO_BENCHMARK_VARIANCE")
                else:
                    beta = covariance / benchmark_variance
                    alpha_daily = mean(excess_rf) - beta * mean(
                        tuple(value - rf_daily for value in benchmark_values)
                    )
                    alpha_annualized = alpha_daily * annualization

                if (
                    strategy_std <= config.zero_denominator_epsilon
                    or benchmark_std <= config.zero_denominator_epsilon
                ):
                    warnings.add("CORRELATION_UNDEFINED")
                else:
                    correlation = covariance / (strategy_std * benchmark_std)

            return RiskResult(
                start_date=source.start_date,
                end_date=source.end_date,
                trade_days=source.trade_days,
                risk_free_rate_annual=config.risk_free_rate_annual,
                benchmark_initial_nav=ONE,
                benchmark_final_nav=benchmark_nav,
                benchmark_cumulative_return=benchmark_cumulative,
                benchmark_annualized_return=benchmark_annualized,
                excess_cumulative_return=daily[-1].excess_cumulative_return,
                relative_nav_final=daily[-1].relative_nav,
                strategy_annualized_volatility=strategy_volatility,
                benchmark_annualized_volatility=benchmark_volatility,
                downside_deviation_annualized=downside_annualized,
                sharpe_ratio=sharpe,
                sortino_ratio=sortino,
                calmar_ratio=calmar,
                tracking_error=tracking_error,
                information_ratio=information_ratio,
                alpha_daily=alpha_daily,
                alpha_annualized=alpha_annualized,
                beta=beta,
                correlation=correlation,
                warnings=tuple(sorted(warnings)),
                daily=tuple(daily),
            )

    @staticmethod
    def _daily_risk_free_rate(annual: Decimal, annualization_days: int) -> Decimal:
        with localcontext() as context:
            context.prec = 60
            return ((ONE + annual).ln() / Decimal(annualization_days)).exp() - ONE

    @staticmethod
    def _price(value: Decimal) -> Decimal:
        return value.quantize(BENCHMARK_PRICE_QUANTUM, rounding=ROUND_HALF_UP)
