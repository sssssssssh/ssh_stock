import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class TradeSourceOrder:
    order_id: uuid.UUID
    signal_trade_date: date
    scheduled_trade_date: date
    ts_code: str
    side: str
    status: str
    attempt_count: int


@dataclass(frozen=True)
class TradeSourceAttempt:
    attempt_id: uuid.UUID
    order_id: uuid.UUID
    attempt_trade_date: date
    attempt_no: int
    outcome: str
    reason_code: str | None
    requested_quantity: int
    fill_quantity: int
    reference_price: Decimal | None
    fill_price: Decimal | None
    gross_amount: Decimal
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    cash_fee_total: Decimal
    slippage_cost: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class TradeSourceFill:
    fill_id: uuid.UUID
    order_id: uuid.UUID
    attempt_id: uuid.UUID
    scheduled_trade_date: date
    trade_date: date
    ts_code: str
    side: str
    quantity: int
    price: Decimal
    reference_price: Decimal
    gross_amount: Decimal
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    cash_fee_total: Decimal
    slippage_cost: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class TradeSourceNav:
    trade_date: date
    total_assets: Decimal
    trading_cost: Decimal


@dataclass(frozen=True)
class TradeSourcePosition:
    trade_date: date
    ts_code: str
    quantity: int
    avg_cost: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True)
class TradeSourceSnapshot:
    run_id: uuid.UUID
    performance_id: uuid.UUID
    performance_version: str
    performance_config_hash: str
    performance_source_hash: str
    trade_version: str
    trade_config_hash: str
    trade_source_hash: str
    backtest_engine_version: str
    portfolio_version: str
    execution_version: str
    accounting_version: str
    start_date: date
    end_date: date
    trade_days: int
    annualization_trade_days: int
    initial_cash: Decimal
    dates: tuple[date, ...]
    orders: tuple[TradeSourceOrder, ...]
    attempts: tuple[TradeSourceAttempt, ...]
    fills: tuple[TradeSourceFill, ...]
    nav: tuple[TradeSourceNav, ...]
    positions: tuple[TradeSourcePosition, ...]


@dataclass(frozen=True)
class TradeDailyPoint:
    trade_date: date
    buy_fill_count: int
    sell_fill_count: int
    fill_count: int
    buy_gross_amount: Decimal
    sell_gross_amount: Decimal
    traded_gross_amount: Decimal
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    cash_fee_total: Decimal
    slippage_cost: Decimal
    total_execution_cost: Decimal
    turnover_denominator: Decimal
    daily_turnover: Decimal


@dataclass(frozen=True)
class TradeEpisodeResult:
    ts_code: str
    episode_no: int
    status: str
    classification: str | None
    entry_date: date
    exit_date: date | None
    holding_trade_days: int
    buy_fill_count: int
    sell_fill_count: int
    fill_count: int
    total_buy_quantity: int
    total_sell_quantity: int
    ending_quantity: int
    buy_gross_amount: Decimal
    sell_gross_amount: Decimal
    buy_cash_fee_total: Decimal
    sell_cash_fee_total: Decimal
    commission: Decimal
    stamp_tax: Decimal
    transfer_fee: Decimal
    cash_fee_total: Decimal
    slippage_cost: Decimal
    total_execution_cost: Decimal
    realized_pnl: Decimal
    unrealized_pnl_end: Decimal
    mark_to_market_pnl_end: Decimal
    total_buy_cash_cost: Decimal
    sell_net_proceeds: Decimal
    episode_return: Decimal | None
    first_fill_id: uuid.UUID
    last_fill_id: uuid.UUID


@dataclass(frozen=True)
class TradeResult:
    start_date: date
    end_date: date
    trade_days: int
    order_count: int
    attempt_count: int
    fill_count: int
    buy_fill_count: int
    sell_fill_count: int
    buy_gross_amount: Decimal
    sell_gross_amount: Decimal
    traded_gross_amount: Decimal
    commission_total: Decimal
    stamp_tax_total: Decimal
    transfer_fee_total: Decimal
    cash_fee_total: Decimal
    slippage_cost_total: Decimal
    total_execution_cost: Decimal
    cash_fee_to_initial_capital: Decimal
    total_cost_to_initial_capital: Decimal
    total_cost_to_traded_amount: Decimal | None
    total_turnover: Decimal
    average_daily_turnover: Decimal
    annualized_turnover: Decimal
    closed_episode_count: int
    open_episode_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: Decimal | None
    gross_profit: Decimal
    gross_loss_abs: Decimal
    profit_factor: Decimal | None
    average_win: Decimal | None
    average_loss_abs: Decimal | None
    payoff_ratio: Decimal | None
    best_episode_pnl: Decimal | None
    worst_episode_pnl: Decimal | None
    average_holding_trade_days: Decimal | None
    median_holding_trade_days: Decimal | None
    closed_realized_pnl: Decimal
    open_realized_pnl_end: Decimal
    open_unrealized_pnl_end: Decimal
    open_mark_to_market_pnl_end: Decimal
    warnings: tuple[str, ...]
    daily: tuple[TradeDailyPoint, ...]
    episodes: tuple[TradeEpisodeResult, ...]
