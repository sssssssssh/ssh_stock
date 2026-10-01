import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PerformanceSourceRow:
    trade_date: date
    nav: Decimal
    total_assets: Decimal
    cash: Decimal
    market_value: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    position_count: int
    trading_cost: Decimal


@dataclass(frozen=True)
class PerformanceSourceSnapshot:
    run_id: uuid.UUID
    start_date: date
    end_date: date
    initial_cash: Decimal
    backtest_engine_version: str
    portfolio_version: str
    execution_version: str
    accounting_version: str
    performance_version: str
    performance_config_hash: str
    source_hash: str
    rows: tuple[PerformanceSourceRow, ...]


@dataclass(frozen=True)
class PerformanceDailyPoint:
    trade_date: date
    nav: Decimal
    daily_return: Decimal
    cumulative_return: Decimal
    running_peak_nav: Decimal
    drawdown: Decimal
    drawdown_duration_days: int
    cash_ratio: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    position_count: int
    trading_cost: Decimal


@dataclass(frozen=True)
class PerformanceResult:
    start_date: date
    end_date: date
    trade_days: int
    initial_nav: Decimal
    final_nav: Decimal
    cumulative_return: Decimal
    annualized_return: Decimal
    max_drawdown: Decimal
    max_drawdown_peak_date: date | None
    max_drawdown_trough_date: date | None
    max_drawdown_recovery_date: date | None
    max_drawdown_duration_days: int
    positive_days: int
    negative_days: int
    flat_days: int
    warnings: tuple[str, ...]
    daily: tuple[PerformanceDailyPoint, ...]
