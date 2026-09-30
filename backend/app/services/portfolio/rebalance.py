from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from app.core.portfolio_config import PortfolioConfig
from app.domain.execution import InstrumentExecutionProfile
from app.domain.portfolio import (
    DailyPortfolioSnapshot,
    PendingOrderAction,
    PendingOrderState,
    PlannedOrder,
    PortfolioTarget,
    RebalancePlanResult,
    RebalanceTarget,
    SkippedTarget,
)

SUPERSEDED_BY_REBALANCE = "SUPERSEDED_BY_REBALANCE"
DELTA_BELOW_MIN_ORDER = "DELTA_BELOW_MIN_ORDER"
NEW_POSITION_DAILY_CAP = "NEW_POSITION_DAILY_CAP"
REBALANCE_SOURCE_INCOMPLETE = "REBALANCE_SOURCE_INCOMPLETE"


class RebalanceSourceIncompleteError(RuntimeError):
    reason_code = REBALANCE_SOURCE_INCOMPLETE


class RebalancePlanner:
    """Convert close targets into deterministic, executable NEXT_OPEN children."""

    def plan(
        self,
        *,
        target: PortfolioTarget,
        account: DailyPortfolioSnapshot,
        pending_orders: Sequence[PendingOrderState],
        close_prices: Mapping[str, Decimal],
        instrument_profiles: Mapping[str, InstrumentExecutionProfile],
        scheduled_trade_date: date,
        config: PortfolioConfig,
    ) -> RebalancePlanResult:
        target_by_code = {item.ts_code: item for item in target.targets}
        current_by_code = {item.ts_code: item.quantity for item in account.positions}
        pending_by_code: dict[str, list[PendingOrderState]] = defaultdict(list)
        for order in pending_orders:
            pending_by_code[order.ts_code].append(order)

        required_codes = set(target_by_code) | set(pending_by_code) | set(current_by_code)
        missing = sorted(code for code in required_codes if code not in instrument_profiles)
        missing.extend(
            sorted(
                code
                for code in target_by_code
                if close_prices.get(code, Decimal("0")) <= 0
            )
        )
        if missing or not target.source_available:
            raise RebalanceSourceIncompleteError(
                f"{REBALANCE_SOURCE_INCOMPLETE}: {sorted(set(missing))}"
            )

        desired: dict[str, int] = {}
        for code, item in target_by_code.items():
            desired[code] = self._desired_quantity(
                account.total_assets,
                item.target_weight,
                close_prices[code],
                instrument_profiles[code],
            )
        for code in current_by_code:
            desired.setdefault(code, 0)

        # Existing matching pending buys represent a position already opened by an
        # earlier signal and therefore do not consume today's new-position cap.
        kept_pending_buy_codes = {
            code
            for code, orders in pending_by_code.items()
            if (
                (pending_buy := sum(order.quantity for order in orders if order.side == "BUY"))
                > 0
                and pending_buy <= desired.get(code, 0)
            )
        }
        cap_candidates = [
            item
            for item in target.targets
            if current_by_code.get(item.ts_code, 0) == 0
            and desired.get(item.ts_code, 0) > 0
            and item.ts_code not in kept_pending_buy_codes
        ]
        cap_candidates.sort(key=lambda item: (-item.source_score, item.ts_code))
        allowed_new = {
            item.ts_code
            for item in cap_candidates[: config.construction.max_new_positions_per_day]
        }
        capped = {item.ts_code for item in cap_candidates} - allowed_new

        targets: list[RebalanceTarget] = []
        actions: list[PendingOrderAction] = []
        new_orders: list[PlannedOrder] = []
        skipped: list[SkippedTarget] = []
        all_codes = sorted(set(desired) | set(pending_by_code))
        for code in all_codes:
            current = current_by_code.get(code, 0)
            target_item = target_by_code.get(code)
            target_weight = target_item.target_weight if target_item else Decimal("0")
            source_score = target_item.source_score if target_item else Decimal("0")
            desired_qty = desired.get(code, 0)
            if code in capped:
                desired_qty = 0
                skipped.append(SkippedTarget(code, NEW_POSITION_DAILY_CAP))

            delta = desired_qty - current
            code_pending = sorted(
                pending_by_code.get(code, ()), key=lambda item: str(item.order_id)
            )
            keep_quantity = 0
            kept_buy = 0
            kept_sell = 0
            wanted_side = "BUY" if delta > 0 else "SELL" if delta < 0 else None
            wanted_quantity = abs(delta)

            same_side = [item for item in code_pending if item.side == wanted_side]
            opposite = [item for item in code_pending if item.side != wanted_side]
            for item in opposite:
                actions.append(
                    PendingOrderAction(
                        item.order_id, "CANCEL", SUPERSEDED_BY_REBALANCE
                    )
                )
            same_total = sum(item.quantity for item in same_side)
            if wanted_side is not None and same_total <= wanted_quantity:
                for item in same_side:
                    actions.append(PendingOrderAction(item.order_id, "KEEP"))
                keep_quantity = same_total
            else:
                for item in same_side:
                    actions.append(
                        PendingOrderAction(
                            item.order_id, "CANCEL", SUPERSEDED_BY_REBALANCE
                        )
                    )
            if wanted_side == "BUY":
                kept_buy = keep_quantity
            elif wanted_side == "SELL":
                kept_sell = keep_quantity

            residual = max(0, wanted_quantity - keep_quantity)
            profile = instrument_profiles[code]
            if residual:
                is_full_liquidation = (
                    wanted_side == "SELL" and residual == current and keep_quantity == 0
                )
                children = self._split_quantity(
                    residual,
                    side=wanted_side or "BUY",
                    profile=profile,
                    full_liquidation=is_full_liquidation,
                )
                if not children:
                    skipped.append(SkippedTarget(code, DELTA_BELOW_MIN_ORDER))
                else:
                    for index, quantity in enumerate(children, start=1):
                        new_orders.append(
                            PlannedOrder(
                                ts_code=code,
                                side=wanted_side or "BUY",
                                target_weight=target_weight,
                                quantity=quantity,
                                child_index=index,
                            )
                        )

            projected = current + kept_buy - kept_sell
            if not any(item.ts_code == code for item in skipped):
                projected = desired_qty
            targets.append(
                RebalanceTarget(
                    ts_code=code,
                    target_weight=target_weight,
                    target_quantity=desired_qty,
                    current_quantity=current,
                    projected_quantity=projected,
                    delta_quantity=desired_qty - current,
                    source_score=source_score,
                    reason_codes=target_item.reason_codes if target_item else (),
                )
            )

        return RebalancePlanResult(
            signal_trade_date=target.signal_trade_date,
            scheduled_trade_date=scheduled_trade_date,
            total_assets=account.total_assets,
            targets=tuple(targets),
            pending_actions=tuple(actions),
            new_orders=tuple(new_orders),
            skipped_targets=tuple(skipped),
        )

    @staticmethod
    def _desired_quantity(
        total_assets: Decimal,
        weight: Decimal,
        close_price: Decimal,
        profile: InstrumentExecutionProfile,
    ) -> int:
        raw = int(
            (total_assets * weight / close_price).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        rounded = raw - (raw % profile.buy_step)
        return rounded if rounded >= profile.min_buy_quantity else 0

    @staticmethod
    def _split_quantity(
        quantity: int,
        *,
        side: str,
        profile: InstrumentExecutionProfile,
        full_liquidation: bool,
    ) -> tuple[int, ...]:
        minimum = profile.min_buy_quantity if side == "BUY" else profile.min_sell_quantity
        step = profile.buy_step if side == "BUY" else profile.sell_step
        maximum = profile.max_buy_quantity if side == "BUY" else profile.max_sell_quantity
        if side == "SELL" and full_liquidation and quantity < minimum:
            return (quantity,)
        if quantity < minimum or (quantity - minimum) % step != 0:
            return ()

        children: list[int] = []
        remaining = quantity
        while remaining > maximum:
            child = maximum - ((maximum - minimum) % step)
            remainder = remaining - child
            if remainder < minimum:
                shift = minimum - remainder
                shift += (-shift) % step
                child -= shift
                remainder += shift
            if child < minimum or (child - minimum) % step or remainder < minimum:
                return ()
            children.append(child)
            remaining = remainder
        if remaining < minimum or (remaining - minimum) % step:
            return ()
        children.append(remaining)
        return tuple(children)
