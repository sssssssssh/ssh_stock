import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.portfolio import AccountState, PortfolioTarget
from app.models.portfolio import PortfolioBacktestRun
from app.repositories.portfolio import PortfolioRepository
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.portfolio.candidates import OpportunityCandidateProvider
from app.services.portfolio.contracts import (
    CandidateBatch,
    PortfolioSourceNotReadyError,
)
from app.services.portfolio.policy import TopNEqualWeightPolicy
from app.services.portfolio.run_factory import BacktestRunFactory


class PortfolioApplicationService:
    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()
        if self.settings.portfolio_config is None or self.settings.execution_config is None:
            raise RuntimeError("portfolio and execution configuration must be loaded")
        if self.settings.accounting_config is None:
            raise RuntimeError("accounting configuration must be loaded")
        if self.settings.portfolio_config.account_mode != "BACKTEST":
            raise ValueError("M13.1 application service only supports BACKTEST account mode")
        self.portfolio_config = self.settings.portfolio_config
        self.execution_config = self.settings.execution_config
        self.accounting_config = self.settings.accounting_config
        self.repository = PortfolioRepository(db)
        self.candidate_provider = OpportunityCandidateProvider(db, self.settings)
        self.policy = TopNEqualWeightPolicy()

    def get_config_status(self) -> dict[str, Any]:
        portfolio = self.portfolio_config.model_dump(mode="json")
        execution = self.execution_config.model_dump(mode="json")
        accounting = self.accounting_config.model_dump(mode="json")
        return {
            "account_mode": self.portfolio_config.account_mode,
            "portfolio": portfolio,
            "execution": execution,
            "accounting": accounting,
            **self.identity_meta(),
        }

    def list_candidates(self, trade_date: date) -> CandidateBatch:
        return self.candidate_provider.list_candidates(trade_date, self.portfolio_config)

    def preview_target(self, trade_date: date) -> PortfolioTarget:
        batch = self.list_candidates(trade_date)
        if not batch.source_ready:
            raise PortfolioSourceNotReadyError(batch)
        account = AccountState(
            trade_date=trade_date,
            cash=self.portfolio_config.initial_cash_cny,
        )
        return self.policy.build_target(
            batch.candidates,
            account,
            self.portfolio_config,
            source_available=True,
        )

    def create_backtest_definition(
        self,
        *,
        start_date: date,
        end_date: date,
        name: str | None = None,
        initial_cash: Decimal | None = None,
        benchmark_code: str | None = None,
    ) -> PortfolioBacktestRun:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        effective_portfolio = self.portfolio_config.model_copy(
            update={
                "initial_cash_cny": (
                    initial_cash
                    if initial_cash is not None
                    else self.portfolio_config.initial_cash_cny
                ),
                "benchmark_code": (
                    benchmark_code
                    if benchmark_code is not None
                    else self.portfolio_config.benchmark_code
                ),
            }
        )
        if effective_portfolio.initial_cash_cny <= 0:
            raise ValueError("initial_cash must be positive")
        if not effective_portfolio.benchmark_code.strip():
            raise ValueError("benchmark_code must be nonempty")
        run = BacktestRunFactory.build(
            name=name,
            start_date=start_date,
            end_date=end_date,
            strategy_snapshot=self.settings.strategy,
            opportunity_snapshot=self.settings.opportunity_config,
            portfolio_snapshot=effective_portfolio.model_dump(mode="json"),
            execution_snapshot=self.execution_config.model_dump(mode="json"),
            accounting_snapshot=self.accounting_config.model_dump(mode="json"),
            algo_version=self.settings.algo_version,
            opportunity_calc_version=OPPORTUNITY_CALC_VERSION,
            portfolio_version=PORTFOLIO_VERSION,
            execution_version=EXECUTION_VERSION,
            accounting_version=ACCOUNTING_VERSION,
            backtest_engine_version=BACKTEST_ENGINE_VERSION,
        )
        try:
            self.repository.create_run(run)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return run

    def list_backtests(self, *, limit: int = 50, offset: int = 0) -> list[PortfolioBacktestRun]:
        return self.repository.list_runs(limit=limit, offset=offset)

    def get_backtest(self, run_id: uuid.UUID) -> PortfolioBacktestRun | None:
        return self.repository.get_run(run_id)

    def identity_meta(self) -> dict[str, str]:
        portfolio = self.portfolio_config.model_dump(mode="json")
        execution = self.execution_config.model_dump(mode="json")
        accounting = self.accounting_config.model_dump(mode="json")
        return {
            "algo_version": self.settings.algo_version,
            "source_strategy_config_hash": analysis_strategy_hash(self.settings.strategy),
            "opportunity_calc_version": OPPORTUNITY_CALC_VERSION,
            "opportunity_config_hash": config_hash(self.settings.opportunity_config),
            "portfolio_version": PORTFOLIO_VERSION,
            "portfolio_config_hash": config_hash(portfolio),
            "execution_version": EXECUTION_VERSION,
            "execution_config_hash": config_hash(execution),
            "accounting_version": ACCOUNTING_VERSION,
            "accounting_config_hash": config_hash(accounting),
            "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        }
