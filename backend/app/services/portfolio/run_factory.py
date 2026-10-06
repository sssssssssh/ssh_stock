from datetime import date
from decimal import Decimal
from typing import Any

from app.core.accounting_config import AccountingConfig
from app.core.execution_config import ExecutionConfig
from app.core.portfolio_config import PortfolioConfig
from app.models.portfolio import PortfolioBacktestRun
from app.services.analysis_identity import analysis_strategy_hash
from app.services.calc_metadata import config_hash


class BacktestRunFactory:
    """Build an unsaved Child/standalone Run from explicit frozen inputs."""

    @staticmethod
    def build(
        *,
        name: str | None,
        start_date: date,
        end_date: date,
        strategy_snapshot: dict[str, Any],
        opportunity_snapshot: dict[str, Any],
        portfolio_snapshot: dict[str, Any],
        execution_snapshot: dict[str, Any],
        accounting_snapshot: dict[str, Any],
        algo_version: str,
        opportunity_calc_version: str,
        portfolio_version: str,
        execution_version: str,
        accounting_version: str,
        backtest_engine_version: str,
    ) -> PortfolioBacktestRun:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        portfolio = PortfolioConfig.model_validate(portfolio_snapshot)
        execution = ExecutionConfig.model_validate(execution_snapshot)
        accounting = AccountingConfig.model_validate(accounting_snapshot)
        if portfolio.account_mode != "BACKTEST":
            raise ValueError("backtest run requires BACKTEST account mode")
        _require_identity("portfolio", portfolio.version, portfolio_version)
        _require_identity("execution", execution.version, execution_version)
        _require_identity("accounting", accounting.version, accounting_version)
        if not algo_version.strip() or not opportunity_calc_version.strip():
            raise ValueError("source identities must be nonempty")
        if not backtest_engine_version.strip():
            raise ValueError("backtest_engine_version must be nonempty")

        frozen_portfolio = portfolio.model_dump(mode="json")
        frozen_execution = execution.model_dump(mode="json")
        frozen_accounting = accounting.model_dump(mode="json")
        return PortfolioBacktestRun(
            name=name,
            account_mode="BACKTEST",
            status="CREATED",
            start_date=start_date,
            end_date=end_date,
            initial_cash=Decimal(portfolio.initial_cash_cny),
            benchmark_code=portfolio.benchmark_code,
            algo_version=algo_version,
            source_strategy_config_hash=analysis_strategy_hash(strategy_snapshot),
            opportunity_calc_version=opportunity_calc_version,
            opportunity_config_hash=config_hash(opportunity_snapshot),
            portfolio_version=portfolio_version,
            portfolio_config_hash=config_hash(frozen_portfolio),
            execution_version=execution_version,
            execution_config_hash=config_hash(frozen_execution),
            accounting_version=accounting_version,
            accounting_config_hash=config_hash(frozen_accounting),
            backtest_engine_version=backtest_engine_version,
            config_snapshot={
                "strategy": strategy_snapshot,
                "opportunity": opportunity_snapshot,
                "portfolio": frozen_portfolio,
                "execution": frozen_execution,
                "accounting": frozen_accounting,
            },
        )


def _require_identity(name: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise ValueError(
            f"{name} snapshot identity mismatch: snapshot={actual}, expected={expected}"
        )
