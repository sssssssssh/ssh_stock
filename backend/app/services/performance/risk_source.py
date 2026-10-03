import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.performance_config import PERFORMANCE_VERSION
from app.domain.performance.risk_contracts import RiskSourceRow, RiskSourceSnapshot
from app.models.market_data import IndexDaily
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.portfolio import PortfolioBacktestRun
from app.services.performance.risk_identity import (
    benchmark_source_hash,
    risk_source_hash,
)

BENCHMARK_PRICE_QUANTUM = Decimal("0.0001")


class PerformanceRiskSourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class BasePerformanceArtifact:
    run: PortfolioBacktestRun
    report: PortfolioPerformanceReport
    daily: tuple[PortfolioPerformanceDaily, ...]
    annualization_trade_days: int


class PerformanceRiskSourceProvider:
    """Read-only boundary over M14.1 artifacts and benchmark market facts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def select_base(
        self, run_id: uuid.UUID, performance_id: uuid.UUID | None = None
    ) -> BasePerformanceArtifact:
        run = self.db.get(PortfolioBacktestRun, run_id)
        if run is None:
            raise PerformanceRiskSourceError(
                "PERFORMANCE_BASE_NOT_FOUND", "portfolio backtest run not found"
            )
        if performance_id is None:
            report = self.db.scalar(
                select(PortfolioPerformanceReport)
                .where(PortfolioPerformanceReport.run_id == run_id)
                .order_by(
                    PortfolioPerformanceReport.calculated_at.desc(),
                    PortfolioPerformanceReport.id.desc(),
                )
                .limit(1)
            )
        else:
            report = self.db.get(PortfolioPerformanceReport, performance_id)
        if report is None:
            raise PerformanceRiskSourceError(
                "PERFORMANCE_BASE_NOT_FOUND", "base performance artifact not found"
            )
        if report.run_id != run_id:
            raise PerformanceRiskSourceError(
                "PERFORMANCE_ARTIFACT_RUN_MISMATCH",
                "base performance artifact belongs to another run",
            )
        daily = tuple(
            self.db.scalars(
                select(PortfolioPerformanceDaily)
                .where(PortfolioPerformanceDaily.performance_id == report.id)
                .order_by(PortfolioPerformanceDaily.trade_date)
            ).all()
        )
        annualization = self._validate_base(report, daily)
        return BasePerformanceArtifact(run, report, daily, annualization)

    def load(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID,
        risk_version: str,
        risk_config_hash: str,
    ) -> RiskSourceSnapshot:
        base = self.select_base(run_id, performance_id)
        benchmark_code = base.run.benchmark_code.strip()
        if not benchmark_code:
            raise PerformanceRiskSourceError(
                "BENCHMARK_CODE_MISSING", "backtest run has no benchmark code"
            )
        dates = tuple(row.trade_date for row in base.daily)
        benchmark_models = tuple(
            self.db.scalars(
                select(IndexDaily)
                .where(
                    IndexDaily.ts_code == benchmark_code,
                    IndexDaily.trade_date.in_(dates),
                )
                .order_by(IndexDaily.trade_date)
            ).all()
        )
        if tuple(row.trade_date for row in benchmark_models) != dates:
            raise PerformanceRiskSourceError(
                "BENCHMARK_SOURCE_INCOMPLETE",
                "benchmark dates must exactly match base performance dates",
            )

        rows: list[RiskSourceRow] = []
        previous_close: Decimal | None = None
        for performance_daily, benchmark in zip(
            base.daily, benchmark_models, strict=True
        ):
            pre_close = self._benchmark_price(benchmark.pre_close)
            close = self._benchmark_price(benchmark.close)
            if previous_close is not None and pre_close != previous_close:
                raise PerformanceRiskSourceError(
                    "BENCHMARK_PRE_CLOSE_MISMATCH",
                    "benchmark pre_close does not match the previous close",
                )
            rows.append(
                RiskSourceRow(
                    trade_date=performance_daily.trade_date,
                    strategy_nav=performance_daily.nav,
                    strategy_daily_return=performance_daily.daily_return,
                    benchmark_pre_close=pre_close,
                    benchmark_close=close,
                )
            )
            previous_close = close
        source_rows = tuple(rows)
        benchmark_hash = benchmark_source_hash(
            benchmark_code=benchmark_code, rows=source_rows
        )
        source_hash = risk_source_hash(
            performance_id=base.report.id,
            performance_version=base.report.performance_version,
            performance_config_hash=base.report.performance_config_hash,
            performance_source_hash=base.report.source_hash,
            risk_version=risk_version,
            risk_config_hash=risk_config_hash,
            benchmark_code=benchmark_code,
            benchmark_hash=benchmark_hash,
        )
        return RiskSourceSnapshot(
            run_id=base.run.id,
            performance_id=base.report.id,
            performance_version=base.report.performance_version,
            performance_config_hash=base.report.performance_config_hash,
            performance_source_hash=base.report.source_hash,
            risk_version=risk_version,
            risk_config_hash=risk_config_hash,
            benchmark_code=benchmark_code,
            benchmark_source_hash=benchmark_hash,
            risk_source_hash=source_hash,
            start_date=base.report.start_date,
            end_date=base.report.end_date,
            trade_days=base.report.trade_days,
            annualization_trade_days=base.annualization_trade_days,
            strategy_annualized_return=base.report.annualized_return,
            strategy_max_drawdown=base.report.max_drawdown,
            rows=source_rows,
        )

    @staticmethod
    def _validate_base(
        report: PortfolioPerformanceReport,
        daily: tuple[PortfolioPerformanceDaily, ...],
    ) -> int:
        if report.performance_version != PERFORMANCE_VERSION or report.status != "SUCCESS":
            raise PerformanceRiskSourceError(
                "PERFORMANCE_BASE_IDENTITY_INVALID",
                "base artifact must be a successful performance_v1 report",
            )
        dates = tuple(row.trade_date for row in daily)
        if (
            len(daily) != report.trade_days
            or not dates
            or dates[0] != report.start_date
            or dates[-1] != report.end_date
            or any(
                current <= previous
                for previous, current in zip(dates, dates[1:], strict=False)
            )
        ):
            raise PerformanceRiskSourceError(
                "PERFORMANCE_BASE_DAILY_INCOMPLETE",
                "base daily rows do not match the performance report",
            )
        if any(
            row.nav <= 0
            or not row.nav.is_finite()
            or not row.daily_return.is_finite()
            or not row.cumulative_return.is_finite()
            for row in daily
        ):
            raise PerformanceRiskSourceError(
                "PERFORMANCE_BASE_IDENTITY_INVALID",
                "base performance daily values are invalid",
            )
        annualization = dict(report.result_summary or {}).get(
            "annualization_trade_days"
        )
        if type(annualization) is not int or annualization <= 0:
            raise PerformanceRiskSourceError(
                "PERFORMANCE_BASE_IDENTITY_INVALID",
                "base performance annualization_trade_days is invalid",
            )
        return annualization

    @staticmethod
    def _benchmark_price(value: float | None) -> Decimal:
        try:
            price = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PerformanceRiskSourceError(
                "BENCHMARK_SOURCE_INVALID", "benchmark price is missing or invalid"
            ) from exc
        if not price.is_finite() or price <= 0:
            raise PerformanceRiskSourceError(
                "BENCHMARK_SOURCE_INVALID", "benchmark price must be finite and positive"
            )
        return price.quantize(BENCHMARK_PRICE_QUANTUM, rounding=ROUND_HALF_UP)
