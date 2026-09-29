from collections.abc import Sequence
from dataclasses import asdict, replace
from decimal import Decimal

from app.core.execution_config import ExecutionConfig
from app.domain.execution import (
    ExecutionBatchResult,
    ExecutionDecision,
    ExecutionMarketBatch,
    MarketExecutionSnapshot,
    OrderIntent,
)
from app.domain.portfolio import AccountState
from app.services.execution.contracts import (
    ExecutionOrderStatus,
    ExecutionOutcome,
    ExecutionReason,
    ExecutionSourceNotReadyError,
    ExecutionSourceStatus,
)
from app.services.execution.cost import ExecutionCostCalculator, money
from app.services.execution.instrument_rules import AshareInstrumentRuleResolver
from app.services.execution.price import (
    adverse_fill_price,
    is_positive_price,
    prices_match,
)

_ZERO = Decimal("0")


class AshareExecutionResolver:
    def __init__(
        self,
        *,
        instrument_rules: AshareInstrumentRuleResolver | None = None,
        cost_calculator: ExecutionCostCalculator | None = None,
    ) -> None:
        self.instrument_rules = instrument_rules or AshareInstrumentRuleResolver()
        self.cost_calculator = cost_calculator or ExecutionCostCalculator()

    def resolve(
        self,
        intents: Sequence[OrderIntent],
        market: Sequence[MarketExecutionSnapshot],
        account: AccountState,
        config: ExecutionConfig,
    ) -> tuple[ExecutionDecision, ...]:
        batch = ExecutionMarketBatch(
            trade_date=account.trade_date,
            source_status=ExecutionSourceStatus.READY.value,
            source_reason=None,
            snapshots=tuple(market),
        )
        return self.resolve_batch(intents, batch, account, config).decisions

    def resolve_batch(
        self,
        intents: Sequence[OrderIntent],
        market: ExecutionMarketBatch,
        account: AccountState,
        config: ExecutionConfig,
    ) -> ExecutionBatchResult:
        if not market.source_ready:
            raise ExecutionSourceNotReadyError(market)
        snapshots = {item.ts_code: item for item in market.snapshots}
        missing_codes = sorted({item.ts_code for item in intents} - snapshots.keys())
        invalid_price_codes = sorted(
            code
            for code, snapshot in snapshots.items()
            if not is_positive_price(snapshot.open_price)
        )
        if missing_codes or invalid_price_codes:
            missing = {}
            if missing_codes:
                missing["snapshot"] = tuple(missing_codes)
            if invalid_price_codes:
                missing["stock_daily"] = tuple(invalid_price_codes)
            raise ExecutionSourceNotReadyError(
                ExecutionMarketBatch(
                    trade_date=market.trade_date,
                    source_status=ExecutionSourceStatus.INCOMPLETE.value,
                    source_reason="EXECUTION_SOURCE_INCOMPLETE",
                    snapshots=market.snapshots,
                    missing_by_layer=missing,
                )
            )

        working_cash = account.cash
        working_positions = {
            item.ts_code: [item.quantity, item.available_quantity]
            for item in account.positions
        }
        decisions: list[ExecutionDecision] = []
        for intent in sorted(intents, key=_intent_sort_key):
            snapshot = snapshots[intent.ts_code]
            quantity = intent.target_quantity or 0
            before_cash = working_cash
            total_quantity, available_quantity = working_positions.get(
                intent.ts_code, [0, 0]
            )
            account_snapshot = {
                "cash_before": str(before_cash),
                "quantity_before": total_quantity,
                "available_quantity_before": available_quantity,
            }
            decision = self._resolve_one(
                intent=intent,
                snapshot=snapshot,
                quantity=quantity,
                total_quantity=total_quantity,
                available_quantity=available_quantity,
                working_cash=working_cash,
                config=config,
                account_snapshot=account_snapshot,
            )
            if decision.outcome == ExecutionOutcome.EXECUTED.value:
                working_cash += decision.cash_delta
                if intent.side == "SELL":
                    working_positions[intent.ts_code] = [
                        total_quantity - quantity,
                        available_quantity - quantity,
                    ]
                else:
                    working_positions[intent.ts_code] = [
                        total_quantity + quantity,
                        available_quantity,
                    ]
            after_quantity, after_available = working_positions.get(
                intent.ts_code, [total_quantity, available_quantity]
            )
            decision = replace(
                decision,
                market_snapshot=_snapshot_payload(snapshot),
                account_snapshot={
                    **account_snapshot,
                    "cash_after": str(working_cash),
                    "quantity_after": after_quantity,
                    "available_quantity_after": after_available,
                },
            )
            decisions.append(decision)
        return ExecutionBatchResult(
            trade_date=market.trade_date,
            starting_cash=account.cash,
            ending_cash_preview=working_cash,
            decisions=tuple(decisions),
        )

    def _resolve_one(
        self,
        *,
        intent: OrderIntent,
        snapshot: MarketExecutionSnapshot,
        quantity: int,
        total_quantity: int,
        available_quantity: int,
        working_cash: Decimal,
        config: ExecutionConfig,
        account_snapshot: dict[str, object],
    ) -> ExecutionDecision:
        if intent.order_id is None:
            return _terminal(intent, ExecutionReason.INVALID_ORDER_ID, account_snapshot)
        if quantity <= 0 or intent.side not in {"BUY", "SELL"}:
            return _terminal(intent, ExecutionReason.INVALID_QUANTITY, account_snapshot)
        profile = self.instrument_rules.resolve(
            ts_code=intent.ts_code,
            exchange=snapshot.exchange,
            market=snapshot.market,
        )
        if profile is None:
            return _terminal(
                intent, ExecutionReason.UNSUPPORTED_INSTRUMENT, account_snapshot
            )
        if snapshot.is_active is not True:
            return _terminal(intent, ExecutionReason.NOT_ACTIVE, account_snapshot)
        if snapshot.is_suspended is True:
            return _temporary(intent, ExecutionReason.SUSPENDED, config, account_snapshot)
        if intent.side == "SELL":
            if quantity > total_quantity:
                return _terminal(
                    intent, ExecutionReason.INSUFFICIENT_POSITION, account_snapshot
                )
            if quantity > available_quantity:
                return _temporary(
                    intent, ExecutionReason.T_PLUS_ONE, config, account_snapshot
                )
            valid_lot = self.instrument_rules.valid_sell(
                profile, quantity, total_quantity
            )
        else:
            valid_lot = self.instrument_rules.valid_buy(profile, quantity)
        if not valid_lot:
            return _terminal(intent, ExecutionReason.INVALID_LOT, account_snapshot)

        reference_price = snapshot.open_price
        if not is_positive_price(reference_price):
            raise AssertionError("READY execution batch must contain a positive raw open")
        assert reference_price is not None
        if intent.side == "BUY" and prices_match(reference_price, snapshot.up_limit):
            return _temporary(
                intent, ExecutionReason.LIMIT_UP, config, account_snapshot,
                reference_price=reference_price,
            )
        if intent.side == "SELL" and prices_match(reference_price, snapshot.down_limit):
            return _temporary(
                intent, ExecutionReason.LIMIT_DOWN, config, account_snapshot,
                reference_price=reference_price,
            )

        fill_price = adverse_fill_price(
            side=intent.side,
            reference_price=reference_price,
            slippage_bps=config.trading_cost.slippage_bps,
            price_tick=config.price_tick_cny,
            up_limit=snapshot.up_limit,
            down_limit=snapshot.down_limit,
        )
        gross_amount = money(fill_price * quantity)
        costs = self.cost_calculator.calculate(
            side=intent.side,
            trade_date=snapshot.trade_date,
            exchange=profile.exchange,
            gross_amount=gross_amount,
            config=config.trading_cost,
        )
        slippage_cost = money(abs(fill_price - reference_price) * quantity)
        total_cost = money(costs.cash_fee_total + slippage_cost)
        if intent.side == "BUY":
            cash_delta = -(gross_amount + costs.cash_fee_total)
            if working_cash + cash_delta < 0:
                return _terminal(
                    intent, ExecutionReason.INSUFFICIENT_CASH, account_snapshot
                )
        else:
            cash_delta = gross_amount - costs.cash_fee_total
        return ExecutionDecision(
            order_id=intent.order_id,
            outcome=ExecutionOutcome.EXECUTED.value,
            status_after=ExecutionOrderStatus.EXECUTED.value,
            retryable=False,
            reason_code=None,
            requested_quantity=quantity,
            fill_quantity=quantity,
            reference_price=reference_price,
            fill_price=fill_price,
            gross_amount=gross_amount,
            commission=costs.commission,
            stamp_tax=costs.stamp_tax,
            transfer_fee=costs.transfer_fee,
            cash_fee_total=costs.cash_fee_total,
            slippage_cost=slippage_cost,
            total_cost=total_cost,
            cash_delta=cash_delta,
            intent=intent,
            account_snapshot=account_snapshot,
        )


def _intent_sort_key(intent: OrderIntent) -> tuple[object, ...]:
    side_order = 0 if intent.side == "SELL" else 1
    stable_id = str(intent.order_id) if intent.order_id is not None else intent.ts_code
    return side_order, intent.scheduled_trade_date, stable_id, intent.ts_code


def _terminal(
    intent: OrderIntent,
    reason: ExecutionReason,
    account_snapshot: dict[str, object],
) -> ExecutionDecision:
    return _empty_decision(
        intent=intent,
        outcome=ExecutionOutcome.REJECTED,
        status=ExecutionOrderStatus.REJECTED,
        retryable=False,
        reason=reason,
        account_snapshot=account_snapshot,
    )


def _temporary(
    intent: OrderIntent,
    reason: ExecutionReason,
    config: ExecutionConfig,
    account_snapshot: dict[str, object],
    *,
    reference_price: Decimal | None = None,
) -> ExecutionDecision:
    expired = intent.attempt_count + 1 >= config.pending_order_max_trade_days
    return _empty_decision(
        intent=intent,
        outcome=(ExecutionOutcome.EXPIRED if expired else ExecutionOutcome.RETRY),
        status=(
            ExecutionOrderStatus.CANCELLED
            if expired
            else ExecutionOrderStatus.PENDING
        ),
        retryable=not expired,
        reason=reason,
        account_snapshot=account_snapshot,
        reference_price=reference_price,
    )


def _empty_decision(
    *,
    intent: OrderIntent,
    outcome: ExecutionOutcome,
    status: ExecutionOrderStatus,
    retryable: bool,
    reason: ExecutionReason,
    account_snapshot: dict[str, object],
    reference_price: Decimal | None = None,
) -> ExecutionDecision:
    return ExecutionDecision(
        order_id=intent.order_id,
        outcome=outcome.value,
        status_after=status.value,
        retryable=retryable,
        reason_code=reason.value,
        requested_quantity=intent.target_quantity or 0,
        fill_quantity=0,
        reference_price=reference_price,
        fill_price=None,
        gross_amount=_ZERO,
        commission=_ZERO,
        stamp_tax=_ZERO,
        transfer_fee=_ZERO,
        cash_fee_total=_ZERO,
        slippage_cost=_ZERO,
        total_cost=_ZERO,
        cash_delta=_ZERO,
        intent=intent,
        account_snapshot=account_snapshot,
    )


def _snapshot_payload(snapshot: MarketExecutionSnapshot) -> dict[str, object]:
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else str(value)
        if isinstance(value, Decimal)
        else value
        for key, value in asdict(snapshot).items()
    }
