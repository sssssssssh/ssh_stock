import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.portfolio import AccountState, DailyPortfolioSnapshot, PositionState
from app.models.market_data import TradeCalendar
from app.repositories.portfolio import PortfolioRepository
from app.services.portfolio.accounting import (
    ACCOUNTING_SOURCE_INCOMPLETE,
    AccountingEngine,
    AccountingSourceError,
)
from app.services.portfolio.accounting_market_data import AccountingMarketDataProvider
from app.services.portfolio.run_guard import validate_current_backtest_contract


class PortfolioAccountingAccountGateway:
    """Build the only supported pre-open account state for current backtests."""

    def __init__(
        self,
        db: Session,
        *,
        repository: PortfolioRepository | None = None,
        provider: AccountingMarketDataProvider | None = None,
        engine: AccountingEngine | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or PortfolioRepository(db)
        self.provider = provider or AccountingMarketDataProvider(db)
        self.engine = engine or AccountingEngine()

    def account_state(self, run_id: uuid.UUID, trade_date: date) -> AccountState:
        run = validate_current_backtest_contract(self.repository.get_run(run_id))
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
        previous = self._previous_snapshot(run_id, previous_trade_date)
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
        self, run_id: uuid.UUID, previous_trade_date: date | None
    ) -> DailyPortfolioSnapshot | None:
        if previous_trade_date is None:
            return None
        nav = self.repository.get_nav(run_id, previous_trade_date)
        if nav is None:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"missing exact previous NAV for {previous_trade_date}",
            )
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
            for row in self.repository.list_position_snapshot(
                run_id, previous_trade_date
            )
        )
        return DailyPortfolioSnapshot(
            trade_date=previous_trade_date,
            cash=nav.cash,
            total_assets=nav.total_assets,
            nav=nav.nav,
            positions=positions,
            market_value=nav.market_value,
            trading_cost=nav.trading_cost,
        )
