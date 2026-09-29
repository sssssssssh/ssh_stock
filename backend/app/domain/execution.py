import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class OrderIntent:
    signal_trade_date: date
    scheduled_trade_date: date
    ts_code: str
    side: str
    order_type: str
    target_weight: Decimal | None = None
    target_quantity: int | None = None
    order_id: uuid.UUID | None = None
    attempt_count: int = 0


@dataclass(frozen=True)
class InstrumentExecutionProfile:
    ts_code: str
    exchange: str
    market: str
    min_buy_quantity: int
    buy_step: int
    min_sell_quantity: int
    sell_step: int
    odd_lot_sell_all_allowed: bool = True


@dataclass(frozen=True)
class MarketExecutionSnapshot:
    trade_date: date
    ts_code: str
    exchange: str | None
    market: str | None
    basic_present: bool
    raw_present: bool
    open_price: Decimal | None
    close_price: Decimal | None
    status_present: bool
    is_active: bool | None
    is_suspended: bool | None
    tradable: bool | None
    limit_present: bool
    up_limit: Decimal | None
    down_limit: Decimal | None


@dataclass(frozen=True)
class ExecutionMarketBatch:
    trade_date: date
    source_status: str
    source_reason: str | None
    snapshots: tuple[MarketExecutionSnapshot, ...]
    missing_by_layer: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def source_ready(self) -> bool:
        return self.source_status == "READY"


@dataclass(frozen=True)
class ExecutionDecision:
    order_id: uuid.UUID | None
    outcome: str
    status_after: str
    retryable: bool
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
    cash_delta: Decimal
    intent: OrderIntent
    market_snapshot: dict[str, object] = field(default_factory=dict)
    account_snapshot: dict[str, object] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.status_after

    @property
    def executable(self) -> bool:
        return self.outcome == "EXECUTED"


@dataclass(frozen=True)
class ExecutionBatchResult:
    trade_date: date
    starting_cash: Decimal
    ending_cash_preview: Decimal
    decisions: tuple[ExecutionDecision, ...]
