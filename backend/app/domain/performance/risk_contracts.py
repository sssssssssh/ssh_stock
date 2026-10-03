import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class RiskSourceRow:
    trade_date: date
    strategy_nav: Decimal
    strategy_daily_return: Decimal
    benchmark_pre_close: Decimal
    benchmark_close: Decimal


@dataclass(frozen=True)
class RiskSourceSnapshot:
    run_id: uuid.UUID
    performance_id: uuid.UUID
    performance_version: str
    performance_config_hash: str
    performance_source_hash: str
    risk_version: str
    risk_config_hash: str
    benchmark_code: str
    benchmark_source_hash: str
    risk_source_hash: str
    start_date: date
    end_date: date
    trade_days: int
    annualization_trade_days: int
    strategy_annualized_return: Decimal
    strategy_max_drawdown: Decimal
    rows: tuple[RiskSourceRow, ...]


@dataclass(frozen=True)
class RiskDailyPoint:
    trade_date: date
    benchmark_reference_close: Decimal
    benchmark_close: Decimal
    benchmark_daily_return: Decimal
    benchmark_nav: Decimal
    active_return: Decimal
    relative_nav: Decimal
    excess_cumulative_return: Decimal


@dataclass(frozen=True)
class RiskResult:
    start_date: date
    end_date: date
    trade_days: int
    risk_free_rate_annual: Decimal
    benchmark_initial_nav: Decimal
    benchmark_final_nav: Decimal
    benchmark_cumulative_return: Decimal
    benchmark_annualized_return: Decimal
    excess_cumulative_return: Decimal
    relative_nav_final: Decimal
    strategy_annualized_volatility: Decimal | None
    benchmark_annualized_volatility: Decimal | None
    downside_deviation_annualized: Decimal | None
    sharpe_ratio: Decimal | None
    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None
    tracking_error: Decimal | None
    information_ratio: Decimal | None
    alpha_daily: Decimal | None
    alpha_annualized: Decimal | None
    beta: Decimal | None
    correlation: Decimal | None
    warnings: tuple[str, ...]
    daily: tuple[RiskDailyPoint, ...]
