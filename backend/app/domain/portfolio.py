from dataclasses import dataclass
from datetime import date
from decimal import Decimal


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
class OrderIntent:
    signal_trade_date: date
    scheduled_trade_date: date
    ts_code: str
    side: str
    order_type: str
    target_weight: Decimal | None = None
    target_quantity: int | None = None


@dataclass(frozen=True)
class MarketExecutionSnapshot:
    trade_date: date
    ts_code: str
    open_price: Decimal | None
    close_price: Decimal | None
    up_limit: Decimal | None
    down_limit: Decimal | None
    suspended: bool


@dataclass(frozen=True)
class ExecutionDecision:
    status: str
    executable: bool
    fill_quantity: int
    fill_price: Decimal | None
    reason_code: str | None
    intent: OrderIntent | None = None


@dataclass(frozen=True)
class DailyPortfolioSnapshot:
    trade_date: date
    cash: Decimal
    total_assets: Decimal
    nav: Decimal
    positions: tuple[PositionState, ...]
    market_value: Decimal = Decimal("0")
    trading_cost: Decimal = Decimal("0")
