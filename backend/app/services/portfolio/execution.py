from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from app.core.execution_config import ExecutionConfig
from app.domain.portfolio import (
    AccountState,
    ExecutionDecision,
    MarketExecutionSnapshot,
    OrderIntent,
)


class ExecutionReason(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    SUSPENDED = "SUSPENDED"
    LIMIT_UP = "LIMIT_UP"
    LIMIT_DOWN = "LIMIT_DOWN"
    NO_MARKET_DATA = "NO_MARKET_DATA"
    T_PLUS_ONE = "T_PLUS_ONE"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INVALID_LOT = "INVALID_LOT"
    EXPIRED = "EXPIRED"


class ExecutionResolver(Protocol):
    def resolve(
        self,
        intents: Sequence[OrderIntent],
        market: Sequence[MarketExecutionSnapshot],
        account: AccountState,
        config: ExecutionConfig,
    ) -> tuple[ExecutionDecision, ...]: ...
