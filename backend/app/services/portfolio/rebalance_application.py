import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.portfolio import (
    DailyPortfolioSnapshot,
    PendingOrderState,
    PortfolioTarget,
)
from app.models.portfolio import PortfolioOrder, PortfolioRebalancePlan
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import PORTFOLIO_VERSION
from app.services.portfolio.rebalance import RebalancePlanner
from app.services.portfolio.rebalance_market_data import RebalanceMarketDataProvider
from app.services.portfolio.run_guard import validate_writable_run


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


class RebalanceApplicationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        repository: PortfolioRepository | None = None,
        provider: RebalanceMarketDataProvider | None = None,
        planner: RebalancePlanner | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.portfolio_config is None:
            raise RuntimeError("portfolio configuration must be loaded")
        self.config = self.settings.portfolio_config
        self.repository = repository or PortfolioRepository(db)
        self.provider = provider or RebalanceMarketDataProvider(db)
        self.planner = planner or RebalancePlanner()

    def plan_and_persist(
        self,
        run_id: uuid.UUID,
        *,
        target: PortfolioTarget,
        account: DailyPortfolioSnapshot,
        scheduled_trade_date: date,
    ) -> PortfolioRebalancePlan:
        try:
            run = validate_writable_run(self.repository.get_run_for_update(run_id))
            if run.portfolio_version != PORTFOLIO_VERSION:
                raise ValueError(
                    "backtest portfolio version mismatch: "
                    f"stored={run.portfolio_version}, current={PORTFOLIO_VERSION}"
                )
            if target.signal_trade_date != account.trade_date:
                raise ValueError("target and close account trade dates must match")
            if scheduled_trade_date <= target.signal_trade_date:
                raise ValueError("scheduled trade date must follow signal trade date")
            existing = self.repository.get_rebalance_plan(
                run_id, target.signal_trade_date
            )
            if existing is not None:
                self.db.commit()
                return existing

            pending_rows = self.repository.list_active_pending_orders(run_id)
            pending = tuple(
                PendingOrderState(
                    order_id=row.id,
                    ts_code=row.ts_code,
                    side=row.side,
                    quantity=row.target_quantity or 0,
                    attempt_count=row.attempt_count,
                )
                for row in pending_rows
            )
            codes = {item.ts_code for item in target.targets}
            codes.update(item.ts_code for item in account.positions)
            codes.update(item.ts_code for item in pending)
            closes, profiles = self.provider.load(
                target.signal_trade_date, tuple(codes)
            )
            result = self.planner.plan(
                target=target,
                account=account,
                pending_orders=pending,
                close_prices=closes,
                instrument_profiles=profiles,
                scheduled_trade_date=scheduled_trade_date,
                config=self.config,
            )
            plan = PortfolioRebalancePlan(
                run_id=run_id,
                signal_trade_date=result.signal_trade_date,
                scheduled_trade_date=result.scheduled_trade_date,
                total_assets=result.total_assets,
                portfolio_version=PORTFOLIO_VERSION,
                target_snapshot=_json_value(asdict(target)),
                account_snapshot=_json_value(asdict(account)),
                plan_snapshot=_json_value(asdict(result)),
            )
            self.repository.insert_rebalance_plan(run_id, plan)
            for action in result.pending_actions:
                if action.action == "CANCEL":
                    self.repository.cancel_order(
                        action.order_id, action.reason_code or "SUPERSEDED_BY_REBALANCE"
                    )
            orders = [
                PortfolioOrder(
                    run_id=run_id,
                    rebalance_plan_id=plan.id,
                    child_index=item.child_index,
                    signal_trade_date=result.signal_trade_date,
                    scheduled_trade_date=result.scheduled_trade_date,
                    ts_code=item.ts_code,
                    side=item.side,
                    order_type="NEXT_OPEN",
                    target_weight=item.target_weight,
                    target_quantity=item.quantity,
                    status="PENDING",
                )
                for item in result.new_orders
            ]
            self.repository.insert_orders(run_id, orders)
            self.db.commit()
            return plan
        except Exception:
            self.db.rollback()
            raise
