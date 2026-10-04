import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class PeriodSourceDaily:
    trade_date: date
    strategy_daily_return: Decimal
    benchmark_daily_return: Decimal
    daily_turnover: Decimal
    traded_gross_amount: Decimal
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    cash_fee_total: Decimal
    slippage_cost: Decimal
    total_execution_cost: Decimal


@dataclass(frozen=True)
class PeriodSourceEpisode:
    exit_date: date
    classification: str
    realized_pnl: Decimal


@dataclass(frozen=True)
class PeriodSourceSnapshot:
    run_id: uuid.UUID
    performance_id: uuid.UUID
    risk_id: uuid.UUID
    trade_id: uuid.UUID
    performance_version: str
    performance_config_hash: str
    performance_source_hash: str
    risk_version: str
    risk_config_hash: str
    risk_source_hash: str
    benchmark_source_hash: str
    trade_version: str
    trade_config_hash: str
    trade_source_hash: str
    period_version: str
    period_config_hash: str
    period_source_hash: str
    start_date: date
    end_date: date
    trade_days: int
    daily: tuple[PeriodSourceDaily, ...]
    closed_episodes: tuple[PeriodSourceEpisode, ...]


@dataclass(frozen=True)
class PeriodPoint:
    period_type: str
    period_key: str
    period_start_date: date
    period_end_date: date
    trade_days: int
    strategy_return: Decimal
    benchmark_return: Decimal
    relative_return: Decimal
    return_spread: Decimal
    period_turnover: Decimal
    traded_gross_amount: Decimal
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    cash_fee_total: Decimal
    slippage_cost: Decimal
    total_execution_cost: Decimal
    closed_episode_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: Decimal | None
    closed_realized_pnl: Decimal


@dataclass(frozen=True)
class PeriodResult:
    start_date: date
    end_date: date
    trade_days: int
    month_count: int
    year_count: int
    warnings: tuple[str, ...]
    periods: tuple[PeriodPoint, ...]
