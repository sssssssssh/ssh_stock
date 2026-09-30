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
from app.services.portfolio.contracts import (
    CandidateProvider,
    PortfolioSourceNotReadyError,
)
from app.services.portfolio.execution import ExecutionResolver
from app.services.portfolio.policy import PortfolioPolicy


class TradingCalendarGateway(Protocol):
    def trade_dates(self, start: date, end: date) -> Sequence[date]: ...

    def next_trade_date(self, day: date) -> date | None: ...


class AccountingLedger(Protocol):
    def start_of_day(self, trade_date: date) -> AccountState: ...

    def pending_order_intents(self, trade_date: date) -> Sequence[OrderIntent]: ...

    def market_snapshot(
        self, trade_date: date, intents: Sequence[OrderIntent]
    ) -> Sequence[MarketExecutionSnapshot]: ...

    def apply_execution(
        self, trade_date: date, decisions: Sequence[ExecutionDecision]
    ) -> None: ...

    def close_account(self, trade_date: date) -> DailyPortfolioSnapshot: ...

    def create_rebalance_plan(
        self,
        target: PortfolioTarget,
        account: DailyPortfolioSnapshot,
        scheduled_trade_date: date,
    ) -> None: ...


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
            # START_OF_DAY: exact previous snapshot, T+1 and corporate-action gates.
            account_open = self.ledger.start_of_day(trade_date)

            # OPEN: only orders created from information available before this day.
            pending = self.ledger.pending_order_intents(trade_date)
            market = self.ledger.market_snapshot(trade_date, pending)
            decisions = self.execution.resolve(
                pending, market, account_open, self.execution_config
            )
            self.ledger.apply_execution(trade_date, decisions)

            # CLOSE: value the account after today's executions.
            snapshot = self.ledger.close_account(trade_date)
            snapshots.append(snapshot)

            # AFTER_CLOSE: today's signal can only create an intent for a later open.
            batch = self.candidates.list_candidates(trade_date, self.portfolio_config)
            if not batch.source_ready:
                raise PortfolioSourceNotReadyError(batch)
            account_close = AccountState(
                trade_date=snapshot.trade_date,
                cash=snapshot.cash,
                positions=snapshot.positions,
            )
            target = self.policy.build_target(
                batch.candidates,
                account_close,
                self.portfolio_config,
                source_available=True,
            )
            next_trade_date = self.calendar.next_trade_date(trade_date)
            if next_trade_date is not None:
                self.ledger.create_rebalance_plan(
                    target,
                    snapshot,
                    scheduled_trade_date=next_trade_date,
                )
        return tuple(snapshots)
