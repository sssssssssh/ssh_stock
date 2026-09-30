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
from app.services.calc_metadata import config_hash
from app.services.portfolio.account_gateway import (
    canonical_account_snapshot,
    load_persisted_close_snapshot,
)
from app.services.portfolio.accounting import AccountingSourceError
from app.services.portfolio.rebalance import RebalancePlanner
from app.services.portfolio.rebalance_market_data import RebalanceMarketDataProvider
from app.services.portfolio.run_guard import validate_current_backtest_contract


class RebalancePlanConflictError(RuntimeError):
    pass


REBALANCE_CLOSE_SNAPSHOT_MISMATCH = "REBALANCE_CLOSE_SNAPSHOT_MISMATCH"


class RebalanceCloseSnapshotMismatchError(RuntimeError):
    reason_code = REBALANCE_CLOSE_SNAPSHOT_MISMATCH


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, (date, uuid.UUID)):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _canonical_target_snapshot(target: PortfolioTarget) -> dict[str, Any]:
    snapshot = _json_value(asdict(target))
    snapshot["targets"] = sorted(snapshot["targets"], key=lambda item: item["ts_code"])
    for item in snapshot["targets"]:
        item["reason_codes"] = sorted(item["reason_codes"])
    return snapshot


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
            contract = validate_current_backtest_contract(
                self.repository.get_run_for_update(run_id), settings=self.settings
            )
            run = contract.run
            if target.signal_trade_date != account.trade_date:
                raise ValueError("target and close account trade dates must match")
            if scheduled_trade_date <= target.signal_trade_date:
                raise ValueError("scheduled trade date must follow signal trade date")
            try:
                authoritative_account = load_persisted_close_snapshot(
                    self.repository, run, target.signal_trade_date
                )
            except AccountingSourceError as exc:
                raise RebalanceCloseSnapshotMismatchError(
                    f"{REBALANCE_CLOSE_SNAPSHOT_MISMATCH}: {exc}"
                ) from exc
            target_snapshot = _canonical_target_snapshot(target)
            account_snapshot = canonical_account_snapshot(authoritative_account)
            if canonical_account_snapshot(account) != account_snapshot:
                raise RebalanceCloseSnapshotMismatchError(
                    f"{REBALANCE_CLOSE_SNAPSHOT_MISMATCH}: external account does not "
                    f"match persisted close for {target.signal_trade_date}"
                )
            input_hash = config_hash(
                {
                    "hash_version": "rebalance_input_v1",
                    "signal_trade_date": str(target.signal_trade_date),
                    "scheduled_trade_date": str(scheduled_trade_date),
                    "portfolio_version": PORTFOLIO_VERSION,
                    "portfolio_config_hash": run.portfolio_config_hash,
                    "target": target_snapshot,
                    "account": account_snapshot,
                }
            )
            existing = self.repository.get_rebalance_plan(run_id, target.signal_trade_date)
            if existing is not None:
                if existing.account_snapshot != account_snapshot:
                    raise RebalanceCloseSnapshotMismatchError(
                        f"{REBALANCE_CLOSE_SNAPSHOT_MISMATCH}: existing plan account "
                        "snapshot differs from persisted close"
                    )
                if existing.input_hash != input_hash:
                    raise RebalancePlanConflictError(
                        "rebalance input conflicts with the persisted plan: "
                        f"stored={existing.input_hash}, current={input_hash}"
                    )
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
            codes.update(item.ts_code for item in authoritative_account.positions)
            codes.update(item.ts_code for item in pending)
            closes, profiles = self.provider.load(
                target.signal_trade_date, tuple(codes)
            )
            result = self.planner.plan(
                target=target,
                account=authoritative_account,
                pending_orders=pending,
                close_prices=closes,
                instrument_profiles=profiles,
                scheduled_trade_date=scheduled_trade_date,
                config=contract.portfolio,
            )
            plan = PortfolioRebalancePlan(
                run_id=run_id,
                signal_trade_date=result.signal_trade_date,
                scheduled_trade_date=result.scheduled_trade_date,
                total_assets=result.total_assets,
                portfolio_version=PORTFOLIO_VERSION,
                input_hash=input_hash,
                target_snapshot=target_snapshot,
                account_snapshot=account_snapshot,
                plan_snapshot={
                    "pre_plan_pending": _json_value(
                        [asdict(item) for item in pending]
                    ),
                    "close_prices": _json_value(closes),
                    "instrument_profiles": _json_value(
                        {key: asdict(value) for key, value in profiles.items()}
                    ),
                    "result": _json_value(asdict(result)),
                },
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
