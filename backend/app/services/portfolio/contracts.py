from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.portfolio_config import PortfolioConfig
from app.domain.portfolio import SignalCandidate


@dataclass(frozen=True)
class CandidateBatch:
    trade_date: date
    candidates: tuple[SignalCandidate, ...]
    source_available: bool


class CandidateProvider(Protocol):
    def list_candidates(
        self, trade_date: date, config: PortfolioConfig
    ) -> CandidateBatch: ...
