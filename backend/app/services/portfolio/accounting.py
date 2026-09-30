from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from app.domain.portfolio import AccountState, DailyPortfolioSnapshot, PositionState
from app.services.portfolio.ledger_precision import ratio

ACCOUNTING_SOURCE_INCOMPLETE = "ACCOUNTING_SOURCE_INCOMPLETE"
UNSUPPORTED_CORPORATE_ACTION = "UNSUPPORTED_CORPORATE_ACTION"
UNSUPPORTED_INACTIVE_HELD_POSITION = "UNSUPPORTED_INACTIVE_HELD_POSITION"


class AccountingSourceError(RuntimeError):
    def __init__(self, reason_code: str, details: str = "") -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {details}" if details else reason_code)


@dataclass(frozen=True)
class AccountingFill:
    fill_id: object
    order_id: object
    scheduled_trade_date: date
    ts_code: str
    side: str
    quantity: int
    price: Decimal
    gross_amount: Decimal
    cash_fee_total: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class AccountingMarketSnapshot:
    ts_code: str
    status_present: bool
    is_active: bool | None
    is_suspended: bool | None
    close_price: Decimal | None
    previous_adj_factor: Decimal | None
    current_adj_factor: Decimal | None


@dataclass(frozen=True)
class PositionDailyRecord:
    position: PositionState
    weight: Decimal


@dataclass(frozen=True)
class NavDailyRecord:
    trade_date: date
    cash: Decimal
    market_value: Decimal
    total_assets: Decimal
    nav: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    position_count: int
    trading_cost: Decimal


class AccountingEngine:
    """Pure replay engine for cash, holdings, valuation and daily NAV."""

    def open_state(
        self,
        *,
        trade_date: date,
        initial_cash: Decimal,
        previous_snapshot: DailyPortfolioSnapshot | None,
    ) -> AccountState:
        if previous_snapshot is None:
            return AccountState(trade_date=trade_date, cash=initial_cash)
        return AccountState(
            trade_date=trade_date,
            cash=previous_snapshot.cash,
            positions=tuple(
                replace(position, available_quantity=position.quantity)
                for position in previous_snapshot.positions
            ),
        )

    def validate_start_of_day(
        self,
        account: AccountState,
        market: Mapping[str, AccountingMarketSnapshot],
    ) -> None:
        for position in account.positions:
            row = market.get(position.ts_code)
            if row is None or not row.status_present:
                raise AccountingSourceError(
                    ACCOUNTING_SOURCE_INCOMPLETE, position.ts_code
                )
            if row.is_active is not True:
                raise AccountingSourceError(
                    UNSUPPORTED_INACTIVE_HELD_POSITION, position.ts_code
                )
            if row.current_adj_factor is None:
                raise AccountingSourceError(
                    ACCOUNTING_SOURCE_INCOMPLETE,
                    f"missing current adj factor for {position.ts_code}",
                )
            if row.previous_adj_factor is None or row.current_adj_factor is None:
                raise AccountingSourceError(
                    ACCOUNTING_SOURCE_INCOMPLETE,
                    f"missing adj factor for {position.ts_code}",
                )
            if row.previous_adj_factor != row.current_adj_factor:
                raise AccountingSourceError(
                    UNSUPPORTED_CORPORATE_ACTION, position.ts_code
                )

    def apply_fills(
        self,
        account: AccountState,
        fills: Sequence[AccountingFill],
    ) -> tuple[AccountState, Decimal]:
        cash = account.cash
        positions = {position.ts_code: position for position in account.positions}
        ordered = sorted(
            fills,
            key=lambda fill: (
                0 if fill.side == "SELL" else 1,
                fill.scheduled_trade_date,
                str(fill.order_id),
                str(fill.fill_id),
            ),
        )
        for fill in ordered:
            position = positions.get(fill.ts_code)
            if fill.side == "SELL":
                if (
                    position is None
                    or fill.quantity > position.quantity
                    or fill.quantity > position.available_quantity
                ):
                    raise ValueError(f"invalid sell fill for {fill.ts_code}")
                net_proceeds = fill.gross_amount - fill.cash_fee_total
                realized = (
                    position.realized_pnl
                    + net_proceeds
                    - position.avg_cost * fill.quantity
                )
                cash += net_proceeds
                remaining = position.quantity - fill.quantity
                if remaining == 0:
                    del positions[fill.ts_code]
                else:
                    positions[fill.ts_code] = replace(
                        position,
                        quantity=remaining,
                        available_quantity=position.available_quantity - fill.quantity,
                        realized_pnl=realized,
                    )
            elif fill.side == "BUY":
                buy_cash_cost = fill.gross_amount + fill.cash_fee_total
                if buy_cash_cost > cash:
                    raise ValueError(f"insufficient cash for fill {fill.fill_id}")
                old_quantity = position.quantity if position else 0
                old_basis = position.avg_cost * old_quantity if position else Decimal("0")
                new_quantity = old_quantity + fill.quantity
                new_avg = (old_basis + buy_cash_cost) / new_quantity
                cash -= buy_cash_cost
                positions[fill.ts_code] = PositionState(
                    ts_code=fill.ts_code,
                    quantity=new_quantity,
                    available_quantity=(position.available_quantity if position else 0),
                    avg_cost=new_avg,
                    market_value=position.market_value if position else Decimal("0"),
                    close_price=position.close_price if position else None,
                    unrealized_pnl=position.unrealized_pnl if position else Decimal("0"),
                    realized_pnl=position.realized_pnl if position else Decimal("0"),
                    valuation_source=position.valuation_source if position else None,
                    adj_factor=position.adj_factor if position else None,
                )
            else:
                raise ValueError(f"unsupported fill side: {fill.side}")
        return (
            AccountState(
                trade_date=account.trade_date,
                cash=cash,
                positions=tuple(positions[code] for code in sorted(positions)),
            ),
            sum((fill.total_cost for fill in fills), Decimal("0")),
        )

    def mark_to_market(
        self,
        *,
        account: AccountState,
        market: Mapping[str, AccountingMarketSnapshot],
        initial_cash: Decimal,
        trading_cost: Decimal,
    ) -> DailyPortfolioSnapshot:
        valued: list[PositionState] = []
        for position in account.positions:
            row = market.get(position.ts_code)
            if row is None or not row.status_present:
                raise AccountingSourceError(
                    ACCOUNTING_SOURCE_INCOMPLETE, position.ts_code
                )
            if row.is_active is not True:
                raise AccountingSourceError(
                    UNSUPPORTED_INACTIVE_HELD_POSITION, position.ts_code
                )
            if row.current_adj_factor is None:
                raise AccountingSourceError(
                    ACCOUNTING_SOURCE_INCOMPLETE,
                    f"missing current adj factor for {position.ts_code}",
                )
            if row.close_price is not None and row.close_price > 0:
                close = row.close_price
                source = "RAW_CLOSE"
            elif row.is_suspended is True and position.close_price is not None:
                close = position.close_price
                source = "CARRY_FORWARD"
            else:
                raise AccountingSourceError(
                    ACCOUNTING_SOURCE_INCOMPLETE,
                    f"missing close for {position.ts_code}",
                )
            market_value = close * position.quantity
            valued.append(
                replace(
                    position,
                    close_price=close,
                    market_value=market_value,
                    unrealized_pnl=(close - position.avg_cost) * position.quantity,
                    valuation_source=source,
                    adj_factor=row.current_adj_factor,
                )
            )
        market_value = sum((item.market_value for item in valued), Decimal("0"))
        total_assets = account.cash + market_value
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        return DailyPortfolioSnapshot(
            trade_date=account.trade_date,
            cash=account.cash,
            total_assets=total_assets,
            nav=total_assets / initial_cash,
            positions=tuple(valued),
            market_value=market_value,
            trading_cost=trading_cost,
        )

    @staticmethod
    def build_position_rows(
        snapshot: DailyPortfolioSnapshot,
    ) -> tuple[PositionDailyRecord, ...]:
        return tuple(
            PositionDailyRecord(
                position=item,
                weight=(
                    ratio(item.market_value / snapshot.total_assets)
                    if snapshot.total_assets
                    else Decimal("0")
                ),
            )
            for item in snapshot.positions
        )

    @staticmethod
    def build_nav_row(snapshot: DailyPortfolioSnapshot) -> NavDailyRecord:
        exposure = (
            ratio(snapshot.market_value / snapshot.total_assets)
            if snapshot.total_assets
            else Decimal("0")
        )
        return NavDailyRecord(
            trade_date=snapshot.trade_date,
            cash=snapshot.cash,
            market_value=snapshot.market_value,
            total_assets=snapshot.total_assets,
            nav=snapshot.nav,
            gross_exposure=exposure,
            net_exposure=exposure,
            position_count=len(snapshot.positions),
            trading_cost=snapshot.trading_cost,
        )
