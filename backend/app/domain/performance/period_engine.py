from collections import defaultdict
from datetime import date
from decimal import Decimal, localcontext

from app.core.performance_period_config import PerformancePeriodConfig
from app.domain.performance.period_contracts import (
    PeriodPoint,
    PeriodResult,
    PeriodSourceDaily,
    PeriodSourceEpisode,
    PeriodSourceSnapshot,
)

ONE = Decimal("1")
ZERO = Decimal("0")


class PeriodCalculationError(RuntimeError):
    code = "PERIOD_SOURCE_INVALID"


class PeriodEngine:
    def calculate(
        self, source: PeriodSourceSnapshot, config: PerformancePeriodConfig
    ) -> PeriodResult:
        if config.version != source.period_version:
            raise PeriodCalculationError("period config version does not match source")
        if not source.daily or len(source.daily) != source.trade_days:
            raise PeriodCalculationError("period source must contain every declared trade day")
        dates = tuple(row.trade_date for row in source.daily)
        if (
            dates[0] != source.start_date
            or dates[-1] != source.end_date
            or any(right <= left for left, right in zip(dates, dates[1:], strict=False))
        ):
            raise PeriodCalculationError("period source dates are invalid")
        for row in source.daily:
            values = (
                row.strategy_daily_return,
                row.benchmark_daily_return,
                row.daily_turnover,
                row.traded_gross_amount,
                row.commission,
                row.stamp_tax,
                row.transfer_fee,
                row.cash_fee_total,
                row.slippage_cost,
                row.total_execution_cost,
            )
            if any(not value.is_finite() for value in values):
                raise PeriodCalculationError("period source contains non-finite values")
            if row.strategy_daily_return <= -ONE or row.benchmark_daily_return <= -ONE:
                raise PeriodCalculationError("daily returns must be greater than -1")

        points: list[PeriodPoint] = []
        for period_type in config.period_types:
            daily_buckets: dict[str, list[PeriodSourceDaily]] = defaultdict(list)
            episode_buckets: dict[str, list[PeriodSourceEpisode]] = defaultdict(list)
            for row in source.daily:
                daily_buckets[self._key(row.trade_date, period_type)].append(row)
            for episode in source.closed_episodes:
                if episode.classification not in {"WIN", "LOSS", "BREAKEVEN"}:
                    raise PeriodCalculationError("closed episode classification is invalid")
                if episode.exit_date < source.start_date or episode.exit_date > source.end_date:
                    raise PeriodCalculationError("closed episode exit date is outside source range")
                episode_buckets[self._key(episode.exit_date, period_type)].append(episode)
            for key, rows in daily_buckets.items():
                points.append(self._aggregate(period_type, key, rows, episode_buckets[key]))

        points.sort(key=lambda row: (0 if row.period_type == "MONTH" else 1, row.period_key))
        month_count = sum(row.period_type == "MONTH" for row in points)
        year_count = sum(row.period_type == "YEAR" for row in points)
        warnings = () if source.closed_episodes else ("NO_CLOSED_EPISODES",)
        return PeriodResult(
            start_date=source.start_date,
            end_date=source.end_date,
            trade_days=source.trade_days,
            month_count=month_count,
            year_count=year_count,
            warnings=warnings,
            periods=tuple(points),
        )

    @staticmethod
    def _key(value: date, period_type: str) -> str:
        return value.strftime("%Y-%m" if period_type == "MONTH" else "%Y")

    @staticmethod
    def _aggregate(
        period_type: str,
        period_key: str,
        rows: list[PeriodSourceDaily],
        episodes: list[PeriodSourceEpisode],
    ) -> PeriodPoint:
        with localcontext() as context:
            context.prec = 60
            strategy_nav = ONE
            benchmark_nav = ONE
            for row in rows:
                strategy_nav *= ONE + row.strategy_daily_return
                benchmark_nav *= ONE + row.benchmark_daily_return
            strategy_return = strategy_nav - ONE
            benchmark_return = benchmark_nav - ONE
            relative_return = strategy_nav / benchmark_nav - ONE
            counts = {
                classification: sum(row.classification == classification for row in episodes)
                for classification in ("WIN", "LOSS", "BREAKEVEN")
            }
            closed_count = len(episodes)
            return PeriodPoint(
                period_type=period_type,
                period_key=period_key,
                period_start_date=rows[0].trade_date,
                period_end_date=rows[-1].trade_date,
                trade_days=len(rows),
                strategy_return=strategy_return,
                benchmark_return=benchmark_return,
                relative_return=relative_return,
                return_spread=strategy_return - benchmark_return,
                period_turnover=sum((row.daily_turnover for row in rows), ZERO),
                traded_gross_amount=sum((row.traded_gross_amount for row in rows), ZERO),
                commission=sum((row.commission for row in rows), ZERO),
                stamp_tax=sum((row.stamp_tax for row in rows), ZERO),
                transfer_fee=sum((row.transfer_fee for row in rows), ZERO),
                cash_fee_total=sum((row.cash_fee_total for row in rows), ZERO),
                slippage_cost=sum((row.slippage_cost for row in rows), ZERO),
                total_execution_cost=sum(
                    (row.total_execution_cost for row in rows), ZERO
                ),
                closed_episode_count=closed_count,
                win_count=counts["WIN"],
                loss_count=counts["LOSS"],
                breakeven_count=counts["BREAKEVEN"],
                win_rate=(Decimal(counts["WIN"]) / Decimal(closed_count))
                if closed_count
                else None,
                closed_realized_pnl=sum((row.realized_pnl for row in episodes), ZERO),
            )
