import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.portfolio import DailyPortfolioSnapshot
from app.models.portfolio import PortfolioNavDaily, PortfolioPositionDaily
from app.repositories.portfolio import PortfolioRepository
from app.services.portfolio.account_gateway import (
    PortfolioAccountingAccountGateway,
    canonical_account_snapshot,
    load_persisted_close_snapshot,
)
from app.services.portfolio.accounting import (
    AccountingEngine,
    AccountingFill,
)
from app.services.portfolio.accounting_market_data import AccountingMarketDataProvider
from app.services.portfolio.run_guard import validate_current_backtest_contract


class CloseSnapshotSealedError(RuntimeError):
    pass


class AccountingApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        repository: PortfolioRepository | None = None,
        provider: AccountingMarketDataProvider | None = None,
        engine: AccountingEngine | None = None,
        account_gateway: PortfolioAccountingAccountGateway | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repository = repository or PortfolioRepository(db)
        self.provider = provider or AccountingMarketDataProvider(db, self.settings)
        self.engine = engine or AccountingEngine()
        self.account_gateway = account_gateway or PortfolioAccountingAccountGateway(
            db,
            repository=self.repository,
            provider=self.provider,
            engine=self.engine,
            settings=self.settings,
        )

    def rebuild_close_snapshot(
        self,
        run_id: uuid.UUID,
        trade_date: date,
    ) -> DailyPortfolioSnapshot:
        try:
            contract = validate_current_backtest_contract(
                self.repository.get_run_for_update(run_id), settings=self.settings
            )
            run = contract.run
            sealed_plan = self.repository.get_rebalance_plan(run_id, trade_date)
            open_account = self.account_gateway.account_state(run_id, trade_date)
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
            post_fill, trading_cost = self.engine.apply_fills(open_account, fills)
            market = self.provider.load_close(
                trade_date=trade_date,
                held_codes=tuple(item.ts_code for item in post_fill.positions),
            )
            snapshot = self.engine.mark_to_market(
                account=post_fill,
                market=market,
                initial_cash=run.initial_cash,
                trading_cost=trading_cost,
            )
            if sealed_plan is not None:
                persisted = load_persisted_close_snapshot(
                    self.repository, run, trade_date
                )
                persisted_payload = canonical_account_snapshot(persisted)
                proposed_payload = canonical_account_snapshot(snapshot)
                if sealed_plan.account_snapshot != persisted_payload:
                    raise CloseSnapshotSealedError(
                        "sealed plan account snapshot differs from persisted close: "
                        f"run={run_id}, date={trade_date}"
                    )
                if proposed_payload != persisted_payload:
                    raise CloseSnapshotSealedError(
                        "recalculated close differs from sealed close: "
                        f"run={run_id}, date={trade_date}"
                    )
                self.db.commit()
                return persisted
            self._persist(run_id, snapshot)
            self.db.commit()
            return snapshot
        except Exception:
            self.db.rollback()
            raise

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
