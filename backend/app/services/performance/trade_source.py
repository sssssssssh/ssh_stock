import uuid
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.performance_config import PERFORMANCE_VERSION
from app.domain.performance.trade_contracts import (
    TradeSourceAttempt,
    TradeSourceFill,
    TradeSourceNav,
    TradeSourceOrder,
    TradeSourcePosition,
    TradeSourceSnapshot,
)
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioFill,
    PortfolioNavDaily,
    PortfolioOrder,
    PortfolioOrderAttempt,
    PortfolioPositionDaily,
)
from app.services.performance.trade_identity import trade_source_hash
from app.services.portfolio.ledger_precision import cost, money, price


class PerformanceTradeSourceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class BaseTradeArtifact:
    run: PortfolioBacktestRun
    report: PortfolioPerformanceReport
    daily: tuple[PortfolioPerformanceDaily, ...]
    annualization_trade_days: int


class PerformanceTradeSourceProvider:
    """Fresh, read-only audit boundary over M13 and M14.1 facts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def select_base(
        self, run_id: uuid.UUID, performance_id: uuid.UUID | None = None
    ) -> BaseTradeArtifact:
        run = self.db.get(PortfolioBacktestRun, run_id, populate_existing=True)
        if run is None:
            raise PerformanceTradeSourceError(
                "PERFORMANCE_TRADE_BASE_NOT_FOUND", "portfolio backtest run not found"
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
                .execution_options(populate_existing=True)
            )
        else:
            report = self.db.get(
                PortfolioPerformanceReport,
                performance_id,
                populate_existing=True,
            )
        if report is None:
            raise PerformanceTradeSourceError(
                "PERFORMANCE_TRADE_BASE_NOT_FOUND",
                "base performance artifact not found",
            )
        if report.run_id != run_id:
            raise PerformanceTradeSourceError(
                "PERFORMANCE_TRADE_ARTIFACT_RUN_MISMATCH",
                "base performance artifact belongs to another run",
            )
        daily = tuple(
            self.db.scalars(
                select(PortfolioPerformanceDaily)
                .where(PortfolioPerformanceDaily.performance_id == report.id)
                .order_by(PortfolioPerformanceDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        annualization = self._validate_base(report, daily)
        return BaseTradeArtifact(run, report, daily, annualization)

    def load(
        self,
        run_id: uuid.UUID,
        *,
        performance_id: uuid.UUID,
        trade_version: str,
        trade_config_hash: str,
    ) -> TradeSourceSnapshot:
        base = self.select_base(run_id, performance_id)
        dates = tuple(row.trade_date for row in base.daily)
        date_set = set(dates)
        orders = tuple(
            self.db.scalars(
                select(PortfolioOrder)
                .where(PortfolioOrder.run_id == run_id)
                .order_by(PortfolioOrder.id)
                .execution_options(populate_existing=True)
            ).all()
        )
        attempts = tuple(
            self.db.scalars(
                select(PortfolioOrderAttempt)
                .where(PortfolioOrderAttempt.run_id == run_id)
                .order_by(
                    PortfolioOrderAttempt.attempt_trade_date,
                    PortfolioOrderAttempt.order_id,
                    PortfolioOrderAttempt.attempt_no,
                    PortfolioOrderAttempt.id,
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        fills = tuple(
            self.db.scalars(
                select(PortfolioFill)
                .where(PortfolioFill.run_id == run_id)
                .order_by(PortfolioFill.trade_date, PortfolioFill.id)
                .execution_options(populate_existing=True)
            ).all()
        )
        nav = tuple(
            self.db.scalars(
                select(PortfolioNavDaily)
                .where(PortfolioNavDaily.run_id == run_id)
                .order_by(PortfolioNavDaily.trade_date)
                .execution_options(populate_existing=True)
            ).all()
        )
        positions = tuple(
            self.db.scalars(
                select(PortfolioPositionDaily)
                .where(PortfolioPositionDaily.run_id == run_id)
                .order_by(
                    PortfolioPositionDaily.trade_date,
                    PortfolioPositionDaily.ts_code,
                )
                .execution_options(populate_existing=True)
            ).all()
        )
        if tuple(row.trade_date for row in nav) != dates:
            raise PerformanceTradeSourceError(
                "TRADE_SOURCE_INCOMPLETE",
                "NAV dates must exactly match performance dates",
            )
        if any(row.attempt_trade_date not in date_set for row in attempts):
            raise PerformanceTradeSourceError(
                "TRADE_SOURCE_INCOMPLETE",
                "attempt date is outside performance dates",
            )
        if any(row.trade_date not in date_set for row in fills):
            raise PerformanceTradeSourceError(
                "TRADE_SOURCE_INCOMPLETE", "fill date is outside performance dates"
            )
        if any(row.trade_date not in date_set for row in positions):
            raise PerformanceTradeSourceError(
                "TRADE_SOURCE_INCOMPLETE",
                "position date is outside performance dates",
            )
        self._validate_execution(run_id, orders, attempts, fills)
        self._validate_nav_and_positions(dates, nav, positions, fills)

        order_map = {row.id: row for row in orders}
        source = TradeSourceSnapshot(
            run_id=run_id,
            performance_id=base.report.id,
            performance_version=base.report.performance_version,
            performance_config_hash=base.report.performance_config_hash,
            performance_source_hash=base.report.source_hash,
            trade_version=trade_version,
            trade_config_hash=trade_config_hash,
            trade_source_hash="",
            backtest_engine_version=base.run.backtest_engine_version,
            portfolio_version=base.run.portfolio_version,
            execution_version=base.run.execution_version,
            accounting_version=base.run.accounting_version,
            start_date=base.report.start_date,
            end_date=base.report.end_date,
            trade_days=base.report.trade_days,
            annualization_trade_days=base.annualization_trade_days,
            initial_cash=base.run.initial_cash,
            dates=dates,
            orders=tuple(self._order(row) for row in orders),
            attempts=tuple(self._attempt(row) for row in attempts),
            fills=tuple(self._fill(row, order_map[row.order_id]) for row in fills),
            nav=tuple(
                TradeSourceNav(row.trade_date, row.total_assets, row.trading_cost) for row in nav
            ),
            positions=tuple(
                TradeSourcePosition(
                    row.trade_date,
                    row.ts_code,
                    row.quantity,
                    row.avg_cost,
                    row.realized_pnl,
                    row.unrealized_pnl,
                )
                for row in positions
            ),
        )
        return replace(source, trade_source_hash=trade_source_hash(source))

    @staticmethod
    def _validate_base(
        report: PortfolioPerformanceReport,
        daily: tuple[PortfolioPerformanceDaily, ...],
    ) -> int:
        if report.performance_version != PERFORMANCE_VERSION or report.status != "SUCCESS":
            raise PerformanceTradeSourceError(
                "TRADE_BASE_IDENTITY_INVALID",
                "base artifact must be a successful performance_v1 report",
            )
        if any(
            not value.is_finite()
            for row in daily
            for value in (row.nav, row.daily_return, row.cumulative_return)
        ) or any(row.nav <= 0 for row in daily):
            raise PerformanceTradeSourceError(
                "TRADE_BASE_DAILY_INCOMPLETE",
                "base daily values must be finite and NAV must be positive",
            )
        dates = tuple(row.trade_date for row in daily)
        if (
            len(daily) != report.trade_days
            or not dates
            or dates[0] != report.start_date
            or dates[-1] != report.end_date
            or any(right <= left for left, right in zip(dates, dates[1:], strict=False))
        ):
            raise PerformanceTradeSourceError(
                "TRADE_BASE_DAILY_INCOMPLETE",
                "base daily rows do not match the performance report",
            )
        annualization = dict(report.result_summary or {}).get("annualization_trade_days")
        if type(annualization) is not int or annualization <= 0:
            raise PerformanceTradeSourceError(
                "TRADE_BASE_IDENTITY_INVALID",
                "base annualization_trade_days is invalid",
            )
        return annualization

    @classmethod
    def _validate_execution(
        cls,
        run_id: uuid.UUID,
        orders: tuple[PortfolioOrder, ...],
        attempts: tuple[PortfolioOrderAttempt, ...],
        fills: tuple[PortfolioFill, ...],
    ) -> None:
        order_map = {row.id: row for row in orders}
        attempt_map = {row.id: row for row in attempts}
        attempts_by_order: dict[uuid.UUID, list[PortfolioOrderAttempt]] = {}
        for attempt in attempts:
            attempts_by_order.setdefault(attempt.order_id, []).append(attempt)
            order = order_map.get(attempt.order_id)
            if order is None or attempt.run_id != run_id or order.run_id != run_id:
                raise PerformanceTradeSourceError(
                    "TRADE_ATTEMPT_IDENTITY_MISMATCH",
                    "attempt does not belong to an order in the selected run",
                )
        for order in orders:
            if order.run_id != run_id or order.attempt_count != len(
                attempts_by_order.get(order.id, [])
            ):
                raise PerformanceTradeSourceError(
                    "TRADE_ORDER_IDENTITY_MISMATCH",
                    "order attempt count or owner is inconsistent",
                )

        fills_by_attempt: dict[uuid.UUID, list[PortfolioFill]] = {}
        for fill in fills:
            if fill.attempt_id is None:
                raise PerformanceTradeSourceError(
                    "TRADE_SOURCE_INCOMPLETE", "fill has no attempt identity"
                )
            fills_by_attempt.setdefault(fill.attempt_id, []).append(fill)
            order = order_map.get(fill.order_id)
            attempt = attempt_map.get(fill.attempt_id)
            if order is None or order.run_id != fill.run_id or fill.run_id != run_id:
                raise PerformanceTradeSourceError(
                    "TRADE_ORDER_IDENTITY_MISMATCH",
                    "fill order identity is inconsistent",
                )
            if (
                attempt is None
                or attempt.run_id != fill.run_id
                or attempt.order_id != fill.order_id
                or attempt.outcome != "EXECUTED"
            ):
                raise PerformanceTradeSourceError(
                    "TRADE_ATTEMPT_IDENTITY_MISMATCH",
                    "fill attempt identity is inconsistent",
                )
            if order.ts_code != fill.ts_code or order.side != fill.side:
                raise PerformanceTradeSourceError(
                    "TRADE_ORDER_IDENTITY_MISMATCH",
                    "order side or security differs from fill",
                )
            if order.status != "EXECUTED" or order.target_quantity != fill.quantity:
                raise PerformanceTradeSourceError(
                    "TRADE_ORDER_IDENTITY_MISMATCH",
                    "filled order status or quantity is inconsistent",
                )
            if attempt.attempt_trade_date != fill.trade_date:
                raise PerformanceTradeSourceError(
                    "TRADE_ATTEMPT_IDENTITY_MISMATCH",
                    "attempt and fill trade dates differ",
                )
            cls._validate_fill_ledger(attempt, fill)

        for attempt in attempts:
            linked = fills_by_attempt.get(attempt.id, [])
            if (attempt.outcome == "EXECUTED" and len(linked) != 1) or (
                attempt.outcome != "EXECUTED" and linked
            ):
                raise PerformanceTradeSourceError(
                    "TRADE_SOURCE_INCOMPLETE",
                    "attempt and fill cardinality is inconsistent",
                )

    @staticmethod
    def _validate_fill_ledger(attempt: PortfolioOrderAttempt, fill: PortfolioFill) -> None:
        attempt_values = (
            attempt.fill_quantity,
            attempt.fill_price,
            attempt.reference_price,
            attempt.gross_amount,
            attempt.commission,
            attempt.stamp_tax,
            attempt.transfer_fee,
            attempt.cash_fee_total,
            attempt.slippage_cost,
            attempt.total_cost,
        )
        fill_values = (
            fill.quantity,
            fill.price,
            fill.reference_price,
            fill.gross_amount,
            fill.commission,
            fill.stamp_tax,
            fill.transfer_fee,
            fill.cash_fee_total,
            fill.slippage_cost,
            fill.total_cost,
        )
        if attempt_values != fill_values or (
            fill.quantity <= 0
            or not fill.price.is_finite()
            or fill.price <= 0
            or not fill.reference_price.is_finite()
            or fill.reference_price <= 0
        ):
            raise PerformanceTradeSourceError(
                "TRADE_FILL_LEDGER_MISMATCH",
                "attempt and fill execution ledger differs",
            )
        if (
            money(fill.price * fill.quantity) != money(fill.gross_amount)
            or money(fill.commission + fill.stamp_tax + fill.transfer_fee)
            != money(fill.cash_fee_total)
            or money(fill.cash_fee_total + fill.slippage_cost) != money(fill.total_cost)
            or money(abs(fill.price - fill.reference_price) * fill.quantity)
            != money(fill.slippage_cost)
        ):
            raise PerformanceTradeSourceError(
                "TRADE_FILL_LEDGER_MISMATCH", "fill ledger arithmetic is invalid"
            )

    @staticmethod
    def _validate_nav_and_positions(
        dates: tuple[date, ...],
        nav: tuple[PortfolioNavDaily, ...],
        positions: tuple[PortfolioPositionDaily, ...],
        fills: tuple[PortfolioFill, ...],
    ) -> None:
        cost_by_date = {trade_date: Decimal("0") for trade_date in dates}
        for fill in fills:
            cost_by_date[fill.trade_date] += fill.total_cost
        for row in nav:
            if (
                not row.total_assets.is_finite()
                or row.total_assets <= 0
                or not row.trading_cost.is_finite()
                or row.trading_cost < 0
            ):
                raise PerformanceTradeSourceError(
                    "TRADE_SOURCE_INCOMPLETE", "NAV trade source values are invalid"
                )
            if money(cost_by_date[row.trade_date]) != money(row.trading_cost):
                raise PerformanceTradeSourceError(
                    "TRADE_DAILY_COST_MISMATCH",
                    f"fill cost and NAV trading_cost differ on {row.trade_date}",
                )
        for row in positions:
            if (
                row.quantity <= 0
                or not row.avg_cost.is_finite()
                or cost(row.avg_cost) <= 0
                or not row.realized_pnl.is_finite()
                or not row.unrealized_pnl.is_finite()
            ):
                raise PerformanceTradeSourceError(
                    "TRADE_SOURCE_INCOMPLETE", "position source values are invalid"
                )

    @staticmethod
    def _order(row: PortfolioOrder) -> TradeSourceOrder:
        return TradeSourceOrder(
            row.id,
            row.signal_trade_date,
            row.scheduled_trade_date,
            row.ts_code,
            row.side,
            row.status,
            row.attempt_count,
        )

    @staticmethod
    def _attempt(row: PortfolioOrderAttempt) -> TradeSourceAttempt:
        return TradeSourceAttempt(
            row.id,
            row.order_id,
            row.attempt_trade_date,
            row.attempt_no,
            row.outcome,
            row.reason_code,
            row.requested_quantity,
            row.fill_quantity,
            row.reference_price,
            row.fill_price,
            row.gross_amount,
            row.commission,
            row.stamp_tax,
            row.transfer_fee,
            row.cash_fee_total,
            row.slippage_cost,
            row.total_cost,
        )

    @staticmethod
    def _fill(row: PortfolioFill, order: PortfolioOrder) -> TradeSourceFill:
        if row.attempt_id is None:
            raise PerformanceTradeSourceError(
                "TRADE_SOURCE_INCOMPLETE", "fill has no attempt identity"
            )
        return TradeSourceFill(
            row.id,
            row.order_id,
            row.attempt_id,
            order.scheduled_trade_date,
            row.trade_date,
            row.ts_code,
            row.side,
            row.quantity,
            price(row.price),
            price(row.reference_price),
            money(row.gross_amount),
            money(row.commission),
            money(row.stamp_tax),
            money(row.transfer_fee),
            money(row.cash_fee_total),
            money(row.slippage_cost),
            money(row.total_cost),
        )
