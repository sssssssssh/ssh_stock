import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.performance.contracts import PerformanceSourceRow, PerformanceSourceSnapshot
from app.models.market_data import TradeCalendar
from app.models.portfolio import PortfolioBacktestRun, PortfolioNavDaily
from app.services.performance.identity import performance_source_hash

NAV_PERSISTENCE_QUANTUM = Decimal("0.00000001")
MONEY_PERSISTENCE_QUANTUM = Decimal("0.0001")


class PerformanceSourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class PerformanceSourceProvider:
    """Read-only adapter from persisted M13 facts to the pure M14 domain."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def load(
        self,
        run_id: uuid.UUID,
        *,
        performance_version: str,
        performance_config_hash: str,
    ) -> PerformanceSourceSnapshot:
        run = self.db.get(PortfolioBacktestRun, run_id)
        if run is None:
            raise PerformanceSourceError("PERFORMANCE_RUN_NOT_FOUND", "backtest run not found")
        if run.account_mode != "BACKTEST" or run.status != "SUCCESS":
            raise PerformanceSourceError(
                "PERFORMANCE_RUN_NOT_SUCCESS",
                "performance requires a successful BACKTEST run",
            )

        open_dates = tuple(
            self.db.scalars(
                select(TradeCalendar.cal_date)
                .where(
                    TradeCalendar.cal_date >= run.start_date,
                    TradeCalendar.cal_date <= run.end_date,
                    TradeCalendar.is_open.is_(True),
                )
                .order_by(TradeCalendar.cal_date)
            ).all()
        )
        nav_models = tuple(
            self.db.scalars(
                select(PortfolioNavDaily)
                .where(PortfolioNavDaily.run_id == run.id)
                .order_by(PortfolioNavDaily.trade_date)
            ).all()
        )
        self._validate(run, open_dates, nav_models)
        rows = tuple(
            PerformanceSourceRow(
                trade_date=row.trade_date,
                nav=row.nav,
                total_assets=row.total_assets,
                cash=row.cash,
                market_value=row.market_value,
                gross_exposure=row.gross_exposure,
                net_exposure=row.net_exposure,
                position_count=row.position_count,
                trading_cost=row.trading_cost,
            )
            for row in nav_models
        )
        source_hash = performance_source_hash(
            run,
            rows,
            performance_version=performance_version,
            performance_config_hash=performance_config_hash,
        )
        return PerformanceSourceSnapshot(
            run_id=run.id,
            start_date=run.start_date,
            end_date=run.end_date,
            initial_cash=run.initial_cash,
            backtest_engine_version=run.backtest_engine_version,
            portfolio_version=run.portfolio_version,
            execution_version=run.execution_version,
            accounting_version=run.accounting_version,
            performance_version=performance_version,
            performance_config_hash=performance_config_hash,
            source_hash=source_hash,
            rows=rows,
        )

    @staticmethod
    def _validate(
        run: PortfolioBacktestRun,
        open_dates: tuple,
        rows: tuple[PortfolioNavDaily, ...],
    ) -> None:
        if not open_dates:
            raise PerformanceSourceError(
                "PERFORMANCE_SOURCE_INCOMPLETE", "run interval has no open trade dates"
            )
        nav_dates = tuple(row.trade_date for row in rows)
        if len(nav_dates) != len(set(nav_dates)):
            raise PerformanceSourceError(
                "PERFORMANCE_NAV_IDENTITY_MISMATCH", "duplicate NAV trade dates"
            )
        if nav_dates != tuple(sorted(nav_dates)) or any(
            current <= previous
            for previous, current in zip(nav_dates, nav_dates[1:], strict=False)
        ):
            raise PerformanceSourceError(
                "PERFORMANCE_NAV_IDENTITY_MISMATCH", "NAV dates are not strictly increasing"
            )
        if nav_dates != open_dates:
            raise PerformanceSourceError(
                "PERFORMANCE_SOURCE_INCOMPLETE",
                "NAV date set must exactly match the run open-date set",
            )
        if run.initial_cash <= 0 or any(
            row.nav <= 0
            or row.total_assets <= 0
            or row.cash < 0
            or row.market_value < 0
            or row.position_count < 0
            or row.gross_exposure < 0
            or row.net_exposure < 0
            or row.trading_cost < 0
            for row in rows
        ):
            raise PerformanceSourceError(
                "PERFORMANCE_SOURCE_INCOMPLETE",
                "performance source contains invalid ledger values",
            )
        for row in rows:
            total_components = (row.cash + row.market_value).quantize(
                MONEY_PERSISTENCE_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            persisted_total = row.total_assets.quantize(
                MONEY_PERSISTENCE_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            expected_nav = (row.total_assets / run.initial_cash).quantize(
                NAV_PERSISTENCE_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            persisted_nav = row.nav.quantize(
                NAV_PERSISTENCE_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            if total_components != persisted_total or expected_nav != persisted_nav:
                raise PerformanceSourceError(
                    "PERFORMANCE_LEDGER_IDENTITY_MISMATCH",
                    "cash, market value, total assets, and NAV do not reconcile",
                )
        final_value = dict(run.result_summary or {}).get("final_nav")
        try:
            expected = Decimal(str(final_value)).quantize(
                NAV_PERSISTENCE_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PerformanceSourceError(
                "PERFORMANCE_NAV_IDENTITY_MISMATCH",
                "backtest result_summary.final_nav is missing or invalid",
            ) from exc
        actual = rows[-1].nav.quantize(
            NAV_PERSISTENCE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if actual != expected:
            raise PerformanceSourceError(
                "PERFORMANCE_NAV_IDENTITY_MISMATCH",
                "final persisted NAV does not match backtest result summary",
            )
