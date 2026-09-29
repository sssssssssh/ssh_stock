import uuid
from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import Protocol

from app.core.execution_config import ExecutionConfig
from app.domain.execution import (
    ExecutionBatchResult,
    ExecutionDecision,
    ExecutionMarketBatch,
    MarketExecutionSnapshot,
    OrderIntent,
)
from app.domain.portfolio import AccountState


class ExecutionSourceStatus(StrEnum):
    READY = "READY"
    INCOMPLETE = "INCOMPLETE"


class ExecutionOutcome(StrEnum):
    RETRY = "RETRY"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExecutionOrderStatus(StrEnum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ExecutionReason(StrEnum):
    NOT_ACTIVE = "NOT_ACTIVE"
    SUSPENDED = "SUSPENDED"
    LIMIT_UP = "LIMIT_UP"
    LIMIT_DOWN = "LIMIT_DOWN"
    T_PLUS_ONE = "T_PLUS_ONE"
    INVALID_ORDER_ID = "INVALID_ORDER_ID"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_LOT = "INVALID_LOT"
    INVALID_PRICE = "INVALID_PRICE"
    INSUFFICIENT_POSITION = "INSUFFICIENT_POSITION"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    EXPIRED = "EXPIRED"


class ExecutionSourceNotReadyError(RuntimeError):
    def __init__(self, batch: ExecutionMarketBatch) -> None:
        self.batch = batch
        super().__init__(
            f"execution source is {batch.source_status}: "
            f"{batch.source_reason or 'unspecified'}"
        )


class ExecutionVersionMismatchError(RuntimeError):
    pass


class AccountGateway(Protocol):
    def account_state(self, run_id: uuid.UUID, trade_date: date) -> AccountState: ...


class ExecutionResolver(Protocol):
    def resolve(
        self,
        intents: Sequence[OrderIntent],
        market: Sequence[MarketExecutionSnapshot],
        account: AccountState,
        config: ExecutionConfig,
    ) -> tuple[ExecutionDecision, ...]: ...

    def resolve_batch(
        self,
        intents: Sequence[OrderIntent],
        market: ExecutionMarketBatch,
        account: AccountState,
        config: ExecutionConfig,
    ) -> ExecutionBatchResult: ...
