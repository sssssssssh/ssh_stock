from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain import execution as execution_domain

ExecutionDecision = execution_domain.ExecutionDecision
MarketExecutionSnapshot = execution_domain.MarketExecutionSnapshot
OrderIntent = execution_domain.OrderIntent


@dataclass(frozen=True)
class CandidateSourceIdentity:
    algo_version: str
    opportunity_calc_version: str
    opportunity_config_hash: str
    source_strategy_config_hash: str


@dataclass(frozen=True)
class SignalCandidate:
    trade_date: date
    ts_code: str
    stage: str
    state: str
    score: Decimal
    rank_score: Decimal
    extension_risk: str | None
    industry_sector_id: int | None
    primary_theme_code: str | None
    source_identity: CandidateSourceIdentity
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PositionState:
    ts_code: str
    quantity: int
    available_quantity: int
    avg_cost: Decimal
    market_value: Decimal
    close_price: Decimal | None = None
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    valuation_source: str | None = None
    adj_factor: Decimal | None = None


@dataclass(frozen=True)
class AccountState:
    trade_date: date
    cash: Decimal
    positions: tuple[PositionState, ...] = ()


@dataclass(frozen=True)
class TargetPosition:
    ts_code: str
    target_weight: Decimal
    source_score: Decimal
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortfolioTarget:
    signal_trade_date: date
    targets: tuple[TargetPosition, ...]
    target_cash_ratio: Decimal
    source_available: bool


@dataclass(frozen=True)
class DailyPortfolioSnapshot:
    trade_date: date
    cash: Decimal
    total_assets: Decimal
    nav: Decimal
    positions: tuple[PositionState, ...]
    market_value: Decimal = Decimal("0")
    trading_cost: Decimal = Decimal("0")


@dataclass(frozen=True)
class RebalanceTarget:
    ts_code: str
    target_weight: Decimal
    target_quantity: int
    current_quantity: int
    projected_quantity: int
    delta_quantity: int
    source_score: Decimal
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PendingOrderState:
    order_id: object
    ts_code: str
    side: str
    quantity: int
    attempt_count: int = 0


@dataclass(frozen=True)
class PendingOrderAction:
    order_id: object
    action: str
    reason_code: str | None = None


@dataclass(frozen=True)
class PlannedOrder:
    ts_code: str
    side: str
    target_weight: Decimal
    quantity: int
    child_index: int
    order_type: str = "NEXT_OPEN"
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkippedTarget:
    ts_code: str
    reason_code: str


@dataclass(frozen=True)
class RebalancePlanResult:
    signal_trade_date: date
    scheduled_trade_date: date
    total_assets: Decimal
    targets: tuple[RebalanceTarget, ...]
    pending_actions: tuple[PendingOrderAction, ...]
    new_orders: tuple[PlannedOrder, ...]
    skipped_targets: tuple[SkippedTarget, ...]
