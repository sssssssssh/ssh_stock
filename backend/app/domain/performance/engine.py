from app.core.performance_config import PerformanceConfig
from app.domain.performance.contracts import (
    PerformanceDailyPoint,
    PerformanceResult,
    PerformanceSourceSnapshot,
)
from app.domain.performance.metrics import (
    ONE,
    ZERO,
    annualized_return,
    cumulative_return,
    daily_return,
)


class PerformanceEngine:
    """Pure Decimal performance calculations over a canonical source snapshot."""

    def calculate(
        self, source: PerformanceSourceSnapshot, config: PerformanceConfig
    ) -> PerformanceResult:
        if not source.rows:
            raise ValueError("performance source rows must not be empty")

        previous_nav = ONE
        running_peak = ONE
        running_peak_date = None
        underwater_days = 0
        max_drawdown = ZERO
        max_peak_date = None
        max_peak_nav = ONE
        max_trough_date = None
        recovery_date = None
        max_episode_duration_days = 0
        positive_days = negative_days = flat_days = 0
        daily_points: list[PerformanceDailyPoint] = []

        for row in source.rows:
            day_return = daily_return(row.nav, previous_nav)
            if day_return > config.zero_return_epsilon:
                positive_days += 1
            elif day_return < -config.zero_return_epsilon:
                negative_days += 1
            else:
                flat_days += 1

            if row.nav > running_peak:
                running_peak = row.nav
            drawdown = row.nav / running_peak - ONE
            if drawdown < ZERO:
                underwater_days += 1
            else:
                if (
                    max_trough_date is not None
                    and recovery_date is None
                    and row.trade_date > max_trough_date
                    and row.nav >= max_peak_nav
                ):
                    recovery_date = row.trade_date
                underwater_days = 0

            if drawdown < max_drawdown:
                max_drawdown = drawdown
                max_peak_date = running_peak_date
                max_peak_nav = running_peak
                max_trough_date = row.trade_date
                recovery_date = None
                max_episode_duration_days = underwater_days
            elif (
                drawdown < ZERO
                and max_trough_date is not None
                and recovery_date is None
                and running_peak == max_peak_nav
                and running_peak_date == max_peak_date
            ):
                max_episode_duration_days = underwater_days

            daily_points.append(
                PerformanceDailyPoint(
                    trade_date=row.trade_date,
                    nav=row.nav,
                    daily_return=day_return,
                    cumulative_return=cumulative_return(row.nav),
                    running_peak_nav=running_peak,
                    drawdown=drawdown,
                    drawdown_duration_days=underwater_days,
                    cash_ratio=(row.cash / row.total_assets if row.total_assets else ZERO),
                    gross_exposure=row.gross_exposure,
                    net_exposure=row.net_exposure,
                    position_count=row.position_count,
                    trading_cost=row.trading_cost,
                )
            )
            if drawdown == ZERO:
                # A repeated high-water mark starts a new episode for any later
                # drawdown, while an already-recorded episode keeps its own peak.
                running_peak_date = row.trade_date
            previous_nav = row.nav

        trade_days = len(source.rows)
        warnings = (
            ("SHORT_SAMPLE_ANNUALIZATION",)
            if trade_days < config.short_sample_warning_trade_days
            else ()
        )
        final_nav = source.rows[-1].nav
        return PerformanceResult(
            start_date=source.rows[0].trade_date,
            end_date=source.rows[-1].trade_date,
            trade_days=trade_days,
            initial_nav=ONE,
            final_nav=final_nav,
            cumulative_return=cumulative_return(final_nav),
            annualized_return=annualized_return(
                final_nav,
                trade_days=trade_days,
                annualization_trade_days=config.annualization_trade_days,
            ),
            max_drawdown=max_drawdown,
            max_drawdown_peak_date=max_peak_date,
            max_drawdown_trough_date=max_trough_date,
            max_drawdown_recovery_date=recovery_date,
            max_drawdown_duration_days=max_episode_duration_days,
            positive_days=positive_days,
            negative_days=negative_days,
            flat_days=flat_days,
            warnings=warnings,
            daily=tuple(daily_points),
        )
