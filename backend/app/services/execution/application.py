import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.execution import ExecutionBatchResult, OrderIntent
from app.models.portfolio import PortfolioFill, PortfolioOrderAttempt
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import EXECUTION_VERSION
from app.services.execution.contracts import (
    AccountGateway,
    ExecutionOutcome,
    ExecutionSourceNotReadyError,
    ExecutionVersionMismatchError,
)
from app.services.execution.market_data import ExecutionMarketDataProvider
from app.services.execution.resolver import AshareExecutionResolver


class ExecutionApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        account_gateway: AccountGateway,
        settings: Settings | None = None,
        market_provider: ExecutionMarketDataProvider | None = None,
        resolver: AshareExecutionResolver | None = None,
        repository: PortfolioRepository | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.execution_config is None:
            raise RuntimeError("execution configuration must be loaded")
        self.config = self.settings.execution_config
        self.account_gateway = account_gateway
        self.repository = repository or PortfolioRepository(db)
        self.market_provider = market_provider or ExecutionMarketDataProvider(
            db, self.settings
        )
        self.resolver = resolver or AshareExecutionResolver()

    def execute_open_batch(
        self,
        run_id: uuid.UUID,
        trade_date: date,
    ) -> ExecutionBatchResult:
        run = self.repository.get_run(run_id)
        if run is None:
            raise LookupError(f"portfolio backtest run not found: {run_id}")
        if run.account_mode != "BACKTEST":
            raise ValueError("M13.2 execution supports BACKTEST account mode only")
        if run.execution_version != EXECUTION_VERSION:
            raise ExecutionVersionMismatchError(
                "backtest execution version mismatch: "
                f"stored={run.execution_version}, current={EXECUTION_VERSION}"
            )

        orders = self.repository.list_pending_orders(run_id, trade_date)
        intents = tuple(
            OrderIntent(
                order_id=order.id,
                signal_trade_date=order.signal_trade_date,
                scheduled_trade_date=order.scheduled_trade_date,
                ts_code=order.ts_code,
                side=order.side,
                order_type=order.order_type,
                target_weight=order.target_weight,
                target_quantity=order.target_quantity,
                attempt_count=order.attempt_count,
            )
            for order in orders
        )
        account = self.account_gateway.account_state(run_id, trade_date)
        market = self.market_provider.load(trade_date, intents)
        if not market.source_ready:
            raise ExecutionSourceNotReadyError(market)

        try:
            result = self.resolver.resolve_batch(intents, market, account, self.config)
            attempts: list[PortfolioOrderAttempt] = []
            fills: list[PortfolioFill] = []
            for decision in result.decisions:
                if decision.order_id is None or decision.requested_quantity <= 0:
                    raise ValueError(
                        "persisted execution decision requires order_id and positive quantity"
                    )
                attempt = PortfolioOrderAttempt(
                    id=uuid.uuid4(),
                    order_id=decision.order_id,
                    run_id=run_id,
                    attempt_trade_date=trade_date,
                    attempt_no=decision.intent.attempt_count + 1,
                    outcome=decision.outcome,
                    reason_code=decision.reason_code,
                    requested_quantity=decision.requested_quantity,
                    fill_quantity=decision.fill_quantity,
                    reference_price=decision.reference_price,
                    fill_price=decision.fill_price,
                    gross_amount=decision.gross_amount,
                    commission=decision.commission,
                    stamp_tax=decision.stamp_tax,
                    transfer_fee=decision.transfer_fee,
                    cash_fee_total=decision.cash_fee_total,
                    slippage_cost=decision.slippage_cost,
                    total_cost=decision.total_cost,
                    market_snapshot=decision.market_snapshot,
                    account_snapshot=decision.account_snapshot,
                )
                attempts.append(attempt)
                order_reason = (
                    "EXPIRED"
                    if decision.outcome == ExecutionOutcome.EXPIRED.value
                    else decision.reason_code
                )
                self.repository.update_order_execution_state(
                    decision.order_id,
                    status=decision.status_after,
                    reason_code=order_reason,
                    attempt_count=decision.intent.attempt_count + 1,
                )
                if decision.outcome == ExecutionOutcome.EXECUTED.value:
                    if decision.reference_price is None or decision.fill_price is None:
                        raise ValueError("executed decision requires reference and fill prices")
                    fills.append(
                        PortfolioFill(
                            order_id=decision.order_id,
                            attempt_id=attempt.id,
                            run_id=run_id,
                            trade_date=trade_date,
                            ts_code=decision.intent.ts_code,
                            side=decision.intent.side,
                            quantity=decision.fill_quantity,
                            price=decision.fill_price,
                            reference_price=decision.reference_price,
                            gross_amount=decision.gross_amount,
                            commission=decision.commission,
                            stamp_tax=decision.stamp_tax,
                            transfer_fee=decision.transfer_fee,
                            cash_fee_total=decision.cash_fee_total,
                            slippage_cost=decision.slippage_cost,
                            total_cost=decision.total_cost,
                        )
                    )
            self.repository.insert_order_attempts(run_id, attempts)
            self.repository.insert_fills(run_id, fills)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise
