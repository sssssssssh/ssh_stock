from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Protocol

from app.core.portfolio_config import PortfolioConfig
from app.domain.portfolio import SignalCandidate


class SourceReadinessStatus(StrEnum):
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPLETE = "INCOMPLETE"


class PortfolioSourceNotReadyError(RuntimeError):
    def __init__(self, batch: "CandidateBatch") -> None:
        self.batch = batch
        super().__init__(
            f"portfolio source is {batch.source_status.value}: "
            f"{batch.source_reason or 'unspecified'}"
        )


@dataclass(frozen=True)
class CandidateBatch:
    trade_date: date
    candidates: tuple[SignalCandidate, ...]
    source_status: SourceReadinessStatus
    source_reason: str | None
    expected_count: int
    stock_daily_count: int
    factor_count: int
    state_count: int
    opportunity_count: int
    mismatch_layers: tuple[str, ...] = ()
    missing_code_samples: dict[str, tuple[str, ...]] = field(default_factory=dict)
    extra_code_samples: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def source_available(self) -> bool:
        return self.source_status != SourceReadinessStatus.UNAVAILABLE

    @property
    def source_ready(self) -> bool:
        return self.source_status == SourceReadinessStatus.READY


class CandidateProvider(Protocol):
    def list_candidates(
        self, trade_date: date, config: PortfolioConfig
    ) -> CandidateBatch: ...
