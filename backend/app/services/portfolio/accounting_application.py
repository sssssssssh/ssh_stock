import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.domain.portfolio import DailyPortfolioSnapshot, PositionState
from app.models.portfolio import PortfolioNavDaily, PortfolioPositionDaily
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import ACCOUNTING_VERSION
from app.services.portfolio.accounting import (
    ACCOUNTING_SOURCE_INCOMPLETE,
    AccountingEngine,
    AccountingFill,
    AccountingSourceError,
)
from app.services.portfolio.accounting_market_data import AccountingMarketDataProvider
from app.services.portfolio.run_guard import validate_writable_run


class AccountingVersionMismatchError(RuntimeError):
    pass


class AccountingApplicationService:
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

    def rebuild_close_snapshot(
        self,
        run_id: uuid.UUID,
        trade_date: date,
        *,
        previous_trade_date: date | None,
    ) -> DailyPortfolioSnapshot:
        try:
            run = validate_writable_run(self.repository.get_run_for_update(run_id))
            if run.accounting_version != ACCOUNTING_VERSION:
                raise AccountingVersionMismatchError(
                    "backtest accounting version mismatch: "
                    f"stored={run.accounting_version}, current={ACCOUNTING_VERSION}"
                )
            if previous_trade_date is None and self.repository.get_latest_nav_before(
                run_id, trade_date
            ) is not None:
                raise AccountingSourceError(
                    ACCOUNTING_SOURCE_INCOMPLETE,
                    "non-first run date requires previous_trade_date",
                )
            if previous_trade_date is not None and previous_trade_date >= trade_date:
                raise ValueError("previous_trade_date must be before trade_date")

            previous = self._previous_snapshot(run_id, previous_trade_date)
            open_account = self.engine.open_state(
                trade_date=trade_date,
                initial_cash=run.initial_cash,
                previous_snapshot=previous,
            )
            fill_rows = self.repository.list_fills_for_date(run_id, trade_date)
            fills = tuple(
                AccountingFill(
                    fill_id=fill.id,
                    order_id=fill.order_id,
                    scheduled_trade_date=order.scheduled_trade_date,
                    ts_code=fill.ts_code,
                    side=fill.side,
                    quantity=fill.quantity,
                    price=fill.price,
                    gross_amount=fill.gross_amount,
                    cash_fee_total=fill.cash_fee_total,
                    total_cost=fill.total_cost,
                )
                for fill, order in fill_rows
            )
            codes = [item.ts_code for item in open_account.positions]
            codes.extend(fill.ts_code for fill in fills)
            market = self.provider.load(
                trade_date=trade_date,
                previous_trade_date=previous_trade_date,
                ts_codes=codes,
            )
            self.engine.validate_start_of_day(open_account, market)
            post_fill, trading_cost = self.engine.apply_fills(open_account, fills)
            snapshot = self.engine.mark_to_market(
                account=post_fill,
                market=market,
                initial_cash=run.initial_cash,
                trading_cost=trading_cost,
            )
            self._persist(run_id, snapshot)
            self.db.commit()
            return snapshot
        except Exception:
            self.db.rollback()
            raise

    def _previous_snapshot(
        self, run_id: uuid.UUID, previous_trade_date: date | None
    ) -> DailyPortfolioSnapshot | None:
        if previous_trade_date is None:
            return None
        nav = self.repository.get_nav(run_id, previous_trade_date)
        if nav is None:
            raise AccountingSourceError(
                ACCOUNTING_SOURCE_INCOMPLETE,
                f"missing previous NAV for {previous_trade_date}",
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

    def _persist(
        self, run_id: uuid.UUID, snapshot: DailyPortfolioSnapshot
    ) -> None:
        position_records = self.engine.build_position_rows(snapshot)
        rows = [
            PortfolioPositionDaily(
                run_id=run_id,
                trade_date=snapshot.trade_date,
                ts_code=record.position.ts_code,
                quantity=record.position.quantity,
                available_quantity=record.position.available_quantity,
                avg_cost=record.position.avg_cost,
                close_price=record.position.close_price,
                market_value=record.position.market_value,
                weight=record.weight,
                unrealized_pnl=record.position.unrealized_pnl,
                realized_pnl=record.position.realized_pnl,
                valuation_source=record.position.valuation_source,
                adj_factor=record.position.adj_factor,
            )
            for record in position_records
        ]
        self.repository.replace_position_snapshot(
            run_id, snapshot.trade_date, rows
        )
        nav = self.engine.build_nav_row(snapshot)
        self.repository.upsert_nav(
            run_id,
            PortfolioNavDaily(
                run_id=run_id,
                trade_date=snapshot.trade_date,
                cash=nav.cash,
                market_value=nav.market_value,
                total_assets=nav.total_assets,
                nav=nav.nav,
                daily_return=None,
                benchmark_nav=None,
                benchmark_daily_return=None,
                gross_exposure=nav.gross_exposure,
                net_exposure=nav.net_exposure,
                position_count=nav.position_count,
                turnover=None,
                trading_cost=nav.trading_cost,
            ),
        )
