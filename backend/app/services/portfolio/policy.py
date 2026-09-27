from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from app.core.portfolio_config import PortfolioConfig
from app.domain.portfolio import (
    AccountState,
    PortfolioTarget,
    SignalCandidate,
    TargetPosition,
)


class PortfolioPolicy(Protocol):
    def build_target(
        self,
        candidates: Sequence[SignalCandidate],
        account: AccountState,
        config: PortfolioConfig,
        *,
        source_available: bool = True,
    ) -> PortfolioTarget: ...


class TopNEqualWeightPolicy:
    def build_target(
        self,
        candidates: Sequence[SignalCandidate],
        account: AccountState,
        config: PortfolioConfig,
        *,
        source_available: bool = True,
    ) -> PortfolioTarget:
        ordered = sorted(candidates, key=lambda item: (-item.score, item.ts_code))
        count = min(
            len(ordered),
            config.candidate.top_n,
            config.construction.max_positions,
        )
        selected = ordered[:count]
        if not selected:
            return PortfolioTarget(
                signal_trade_date=account.trade_date,
                targets=(),
                target_cash_ratio=Decimal("1"),
                source_available=source_available,
            )
        investable = 1 - config.construction.min_cash_ratio
        equal_weight = min(
            config.construction.max_single_position_weight,
            investable / len(selected),
        )
        positions = tuple(
            TargetPosition(
                ts_code=candidate.ts_code,
                target_weight=equal_weight,
                source_score=candidate.score,
                reason_codes=candidate.reason_codes,
            )
            for candidate in selected
        )
        return PortfolioTarget(
            signal_trade_date=account.trade_date,
            targets=positions,
            target_cash_ratio=1 - equal_weight * len(positions),
            source_available=source_available,
        )
