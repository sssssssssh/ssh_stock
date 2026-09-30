from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from app.domain.portfolio import DailyPortfolioSnapshot, PositionState

MONEY_QUANTUM = Decimal("0.0001")
COST_QUANTUM = Decimal("0.00000001")
RATIO_QUANTUM = Decimal("0.00000001")
PRICE_QUANTUM = Decimal("0.0001")
ADJ_FACTOR_QUANTUM = Decimal("0.0000000001")


def quantize_decimal(value: Decimal, quantum: Decimal) -> Decimal:
    return Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)


def money(value: Decimal) -> Decimal:
    return quantize_decimal(value, MONEY_QUANTUM)


def cost(value: Decimal) -> Decimal:
    return quantize_decimal(value, COST_QUANTUM)


def ratio(value: Decimal) -> Decimal:
    return quantize_decimal(value, RATIO_QUANTUM)


def price(value: Decimal) -> Decimal:
    return quantize_decimal(value, PRICE_QUANTUM)


def adj_factor(value: Decimal) -> Decimal:
    return quantize_decimal(value, ADJ_FACTOR_QUANTUM)


def normalize_snapshot_for_persistence(
    snapshot: DailyPortfolioSnapshot,
    *,
    initial_cash: Decimal,
) -> DailyPortfolioSnapshot:
    """Apply PostgreSQL ledger-column semantics once, after full-precision calculation."""
    positions = tuple(
        _normalize_accounting_position(position)
        for position in sorted(snapshot.positions, key=lambda item: item.ts_code)
    )
    normalized_cash = money(snapshot.cash)
    market_value = money(
        sum((position.market_value for position in positions), Decimal("0"))
    )
    total_assets = money(normalized_cash + market_value)
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    return replace(
        snapshot,
        cash=normalized_cash,
        total_assets=total_assets,
        nav=ratio(total_assets / Decimal(initial_cash)),
        positions=positions,
        market_value=market_value,
        trading_cost=money(snapshot.trading_cost),
    )


def quantize_snapshot_fields(
    snapshot: DailyPortfolioSnapshot,
) -> DailyPortfolioSnapshot:
    """Quantize supplied fields without repairing inconsistent external snapshots."""
    positions = tuple(
        _quantize_position_fields(position)
        for position in sorted(snapshot.positions, key=lambda item: item.ts_code)
    )
    return replace(
        snapshot,
        cash=money(snapshot.cash),
        total_assets=money(snapshot.total_assets),
        nav=ratio(snapshot.nav),
        positions=positions,
        market_value=money(snapshot.market_value),
        trading_cost=money(snapshot.trading_cost),
    )


def _normalize_accounting_position(position_state: PositionState) -> PositionState:
    normalized = _quantize_position_fields(position_state)
    if normalized.close_price is None:
        return normalized
    market_value = money(normalized.close_price * normalized.quantity)
    unrealized_pnl = money(
        (normalized.close_price - normalized.avg_cost) * normalized.quantity
    )
    return replace(
        normalized,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
    )


def _quantize_position_fields(position_state: PositionState) -> PositionState:
    return replace(
        position_state,
        avg_cost=cost(position_state.avg_cost),
        market_value=money(position_state.market_value),
        close_price=(
            price(position_state.close_price)
            if position_state.close_price is not None
            else None
        ),
        unrealized_pnl=money(position_state.unrealized_pnl),
        realized_pnl=money(position_state.realized_pnl),
        adj_factor=(
            adj_factor(position_state.adj_factor)
            if position_state.adj_factor is not None
            else None
        ),
    )
