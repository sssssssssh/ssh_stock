import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.portfolio import AccountState, DailyPortfolioSnapshot, PositionState
from app.models.market_data import TradeCalendar
from app.models.portfolio import (
    PortfolioBacktestRun,
    PortfolioNavDaily,
    PortfolioPositionDaily,
)
from app.repositories.portfolio import PortfolioRepository
from app.services.portfolio.accounting import (
    ACCOUNTING_SOURCE_INCOMPLETE,
    AccountingEngine,
    AccountingSourceError,
)
from app.services.portfolio.accounting_market_data import AccountingMarketDataProvider
from app.services.portfolio.ledger_precision import (
    adj_factor,
    cost,
    money,
    quantize_snapshot_fields,
    ratio,
)
from app.services.portfolio.run_guard import validate_current_backtest_contract


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, (date, uuid.UUID)):
        return str(value)
    if isinstance(value, dict):
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_account_snapshot(snapshot: DailyPortfolioSnapshot) -> dict[str, Any]:
    payload = _canonical_value(asdict(quantize_snapshot_fields(snapshot)))
    payload["positions"] = sorted(
        payload["positions"], key=lambda item: item["ts_code"]
    )
    return payload


def _finite_decimal(value: Any) -> bool:
    try:
        return Decimal(value).is_finite()
    except (TypeError, ValueError):
        return False


def validate_previous_snapshot_integrity(
    nav: PortfolioNavDaily,
    positions: list[PortfolioPositionDaily],
    initial_cash: Decimal,
) -> None:
    day = nav.trade_date
    nav_values = {
        "cash": nav.cash,
        "market_value": nav.market_value,
        "total_assets": nav.total_assets,
        "nav": nav.nav,
        "gross_exposure": nav.gross_exposure,
        "net_exposure": nav.net_exposure,
        "trading_cost": nav.trading_cost,
    }
    invalid_nav_values = [
        name for name, value in nav_values.items() if not _finite_decimal(value)
    ]
    if invalid_nav_values:
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"{day} invalid NAV numeric fields: {invalid_nav_values}",
        )
    if any(
        Decimal(value) < 0
        for value in (
            nav.cash,
            nav.market_value,
            nav.total_assets,
            nav.nav,
            nav.gross_exposure,
            nav.net_exposure,
            nav.trading_cost,
        )
    ):
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"{day} NAV fields must be non-negative",
        )
    expected_count = nav.position_count
    actual_count = len(positions)
    if expected_count != actual_count:
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"{day} position_count mismatch: nav={expected_count}, rows={actual_count}",
        )

    for row in positions:
        if row.trade_date != day:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} position date mismatch: {row.trade_date}",
            )
        if row.quantity <= 0:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} quantity must be positive: {row.quantity}",
            )
        if row.available_quantity < 0 or row.available_quantity > row.quantity:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} invalid available quantity: "
                f"available={row.available_quantity}, quantity={row.quantity}",
            )
        if (
            not _finite_decimal(row.close_price)
            or Decimal(row.close_price) <= 0
        ):
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} invalid close price: {row.close_price}",
            )
        numeric_fields = {
            "avg_cost": row.avg_cost,
            "market_value": row.market_value,
            "weight": row.weight,
            "unrealized_pnl": row.unrealized_pnl,
            "realized_pnl": row.realized_pnl,
            "adj_factor": row.adj_factor,
        }
        invalid_fields = [
            name for name, value in numeric_fields.items() if not _finite_decimal(value)
        ]
        if invalid_fields:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} invalid numeric fields: {invalid_fields}",
            )
        if row.market_value < 0:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} negative market value: {row.market_value}",
            )
        if row.avg_cost < 0:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} negative average cost: {row.avg_cost}",
            )
        if row.weight < 0 or row.weight > 1:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} invalid weight: {row.weight}",
            )
        if row.valuation_source not in {"RAW_CLOSE", "CARRY_FORWARD"}:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} invalid valuation source: "
                f"{row.valuation_source}",
            )
        if row.adj_factor is None or adj_factor(row.adj_factor) <= 0:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} invalid adjustment factor: {row.adj_factor}",
            )
        expected_market_value = money(row.close_price * row.quantity)
        actual_market_value = money(row.market_value)
        if actual_market_value != expected_market_value:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} market value mismatch: "
                f"stored={actual_market_value}, expected={expected_market_value}, "
                f"delta={actual_market_value - expected_market_value}",
            )
        expected_unrealized = money(
            (row.close_price - cost(row.avg_cost)) * row.quantity
        )
        actual_unrealized = money(row.unrealized_pnl)
        if actual_unrealized != expected_unrealized:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} unrealized PnL mismatch: "
                f"stored={actual_unrealized}, expected={expected_unrealized}, "
                f"delta={actual_unrealized - expected_unrealized}",
            )

    actual_market_value = money(
        sum((Decimal(row.market_value) for row in positions), Decimal("0"))
    )
    nav_market_value = money(nav.market_value)
    if actual_market_value != nav_market_value:
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"{day} position market value mismatch: rows={actual_market_value}, "
            f"nav={nav_market_value}, delta={actual_market_value - nav_market_value}",
        )
    expected_total_assets = money(nav.cash + nav.market_value)
    total_assets = money(nav.total_assets)
    if expected_total_assets != total_assets:
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"{day} total assets mismatch: cash_plus_market={expected_total_assets}, "
            f"stored={total_assets}, delta={expected_total_assets - total_assets}",
        )
    expected_exposure = (
        ratio(nav_market_value / total_assets) if total_assets else Decimal("0")
    )
    for name, value in (
        ("gross_exposure", nav.gross_exposure),
        ("net_exposure", nav.net_exposure),
    ):
        stored_exposure = ratio(value)
        if stored_exposure != expected_exposure:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {name} mismatch: stored={stored_exposure}, "
                f"expected={expected_exposure}",
            )
    for row in positions:
        expected_weight = (
            ratio(Decimal(row.market_value) / total_assets)
            if total_assets
            else Decimal("0")
        )
        stored_weight = ratio(row.weight)
        if stored_weight != expected_weight:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"{day} {row.ts_code} weight mismatch: stored={stored_weight}, "
                f"expected={expected_weight}",
            )
    if initial_cash <= 0:
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"{day} initial cash must be positive: {initial_cash}",
        )
    expected_nav = ratio(total_assets / Decimal(initial_cash))
    stored_nav = ratio(nav.nav)
    if stored_nav != expected_nav:
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"{day} NAV ratio mismatch: stored={stored_nav}, expected={expected_nav}, "
            f"delta={stored_nav - expected_nav}",
        )


def load_persisted_close_snapshot(
    repository: PortfolioRepository,
    run: PortfolioBacktestRun,
    trade_date: date,
) -> DailyPortfolioSnapshot:
    nav = repository.get_nav(run.id, trade_date)
    if nav is None:
        raise AccountingSourceError(
            ACCOUNTING_SOURCE_INCOMPLETE,
            f"missing exact NAV for {trade_date}",
        )
    position_rows = repository.list_position_snapshot(run.id, trade_date)
    validate_previous_snapshot_integrity(nav, position_rows, run.initial_cash)
    positions = tuple(
        PositionState(
            ts_code=row.ts_code,
            quantity=row.quantity,
            available_quantity=row.available_quantity,
            avg_cost=row.avg_cost,
            market_value=row.market_value,
            close_price=row.close_price,
            unrealized_pnl=row.unrealized_pnl,
            realized_pnl=row.realized_pnl,
            valuation_source=row.valuation_source,
            adj_factor=row.adj_factor,
        )
        for row in position_rows
    )
    return DailyPortfolioSnapshot(
        trade_date=trade_date,
        cash=nav.cash,
        total_assets=nav.total_assets,
        nav=nav.nav,
        positions=positions,
        market_value=nav.market_value,
        trading_cost=nav.trading_cost,
    )


class PortfolioAccountingAccountGateway:
    """Build the only supported pre-open account state for current backtests."""

    def __init__(
        self,
        db: Session,
        *,
        repository: PortfolioRepository | None = None,
        provider: AccountingMarketDataProvider | None = None,
        engine: AccountingEngine | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repository = repository or PortfolioRepository(db)
        self.provider = provider or AccountingMarketDataProvider(db, self.settings)
        self.engine = engine or AccountingEngine()

    def account_state(self, run_id: uuid.UUID, trade_date: date) -> AccountState:
        contract = validate_current_backtest_contract(
            self.repository.get_run(run_id), settings=self.settings
        )
        run = contract.run
        calendar = self.db.get(TradeCalendar, trade_date)
        if calendar is None or not calendar.is_open:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"missing open trade calendar row for {trade_date}",
            )
        first_open_date = self.db.scalar(
            select(func.min(TradeCalendar.cal_date)).where(
                TradeCalendar.cal_date >= run.start_date,
                TradeCalendar.cal_date <= run.end_date,
                TradeCalendar.is_open.is_(True),
            )
        )
        if (
            first_open_date is None
            or trade_date < first_open_date
            or trade_date > run.end_date
        ):
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"trade date {trade_date} is outside the run's open calendar",
            )

        previous_trade_date = None if trade_date == first_open_date else calendar.pretrade_date
        if trade_date != first_open_date and previous_trade_date is None:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"missing pretrade_date for {trade_date}",
            )
        previous = self._previous_snapshot(run, previous_trade_date)
        account = self.engine.open_state(
            trade_date=trade_date,
            initial_cash=run.initial_cash,
            previous_snapshot=previous,
        )
        market = self.provider.load_start_of_day(
            previous_trade_date=previous_trade_date,
            trade_date=trade_date,
            held_codes=tuple(item.ts_code for item in account.positions),
        )
        self.engine.validate_start_of_day(account, market)
        return account

    def _previous_snapshot(
        self, run: PortfolioBacktestRun, previous_trade_date: date | None
    ) -> DailyPortfolioSnapshot | None:
        if previous_trade_date is None:
            return None
        return load_persisted_close_snapshot(self.repository, run, previous_trade_date)
