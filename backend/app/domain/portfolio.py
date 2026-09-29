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
