from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.core.execution_config import ExecutionConfig
from app.core.portfolio_config import PortfolioConfig
from app.domain.portfolio import (
    AccountState,
    DailyPortfolioSnapshot,
    ExecutionDecision,
    MarketExecutionSnapshot,
    OrderIntent,
    PortfolioTarget,
)
from app.services.portfolio.contracts import CandidateProvider
from app.services.portfolio.execution import ExecutionResolver
from app.services.portfolio.policy import PortfolioPolicy


class TradingCalendarGateway(Protocol):
    def trade_dates(self, start: date, end: date) -> Sequence[date]: ...


class AccountingLedger(Protocol):
    def account_state(self, trade_date: date) -> AccountState: ...

    def order_intents(
        self, target: PortfolioTarget, account: AccountState
    ) -> Sequence[OrderIntent]: ...

    def market_snapshot(
        self, trade_date: date, intents: Sequence[OrderIntent]
    ) -> Sequence[MarketExecutionSnapshot]: ...

    def apply(
        self, trade_date: date, decisions: Sequence[ExecutionDecision]
    ) -> DailyPortfolioSnapshot: ...


class BacktestEngine:
    """Dependency-injected orchestration skeleton; it contains no ORM or broker logic."""

    def __init__(
        self,
        *,
        calendar: TradingCalendarGateway,
        candidates: CandidateProvider,
        policy: PortfolioPolicy,
        execution: ExecutionResolver,
        ledger: AccountingLedger,
        portfolio_config: PortfolioConfig,
        execution_config: ExecutionConfig,
    ) -> None:
        self.calendar = calendar
        self.candidates = candidates
        self.policy = policy
        self.execution = execution
        self.ledger = ledger
        self.portfolio_config = portfolio_config
        self.execution_config = execution_config

    def run(self, start: date, end: date) -> tuple[DailyPortfolioSnapshot, ...]:
        snapshots: list[DailyPortfolioSnapshot] = []
        for trade_date in self.calendar.trade_dates(start, end):
            account = self.ledger.account_state(trade_date)
            batch = self.candidates.list_candidates(trade_date, self.portfolio_config)
            target = self.policy.build_target(
                batch.candidates,
                account,
                self.portfolio_config,
                source_available=batch.source_available,
            )
            intents = self.ledger.order_intents(target, account)
            market = self.ledger.market_snapshot(trade_date, intents)
            decisions = self.execution.resolve(
                intents, market, account, self.execution_config
            )
            snapshots.append(self.ledger.apply(trade_date, decisions))
        return tuple(snapshots)
