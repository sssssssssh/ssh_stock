from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.core.accounting_config import AccountingConfig
from app.core.config import Settings, get_settings
from app.core.execution_config import ExecutionConfig
from app.core.portfolio_config import PortfolioConfig
from app.models.portfolio import PortfolioBacktestRun
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    OPPORTUNITY_CALC_VERSION,
    PORTFOLIO_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash


class BacktestContractMismatchError(RuntimeError):
    pass


class RunConfigIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrozenRunConfig:
    run: PortfolioBacktestRun
    portfolio: PortfolioConfig
    execution: ExecutionConfig
    accounting: AccountingConfig
    strategy: dict[str, Any]
    opportunity: dict[str, Any]


def validate_writable_run(run: PortfolioBacktestRun | None) -> PortfolioBacktestRun:
    if run is None:
        raise LookupError("portfolio backtest run not found")
    if run.account_mode != "BACKTEST":
        raise ValueError("portfolio write services support BACKTEST account mode only")
    if run.status != "RUNNING":
        raise ValueError(f"portfolio run must be RUNNING, got {run.status}")
    return run


def validate_current_backtest_contract(
    run: PortfolioBacktestRun | None,
    *,
    settings: Settings | None = None,
) -> FrozenRunConfig:
    try:
        current = validate_writable_run(run)
    except (LookupError, ValueError) as exc:
        raise BacktestContractMismatchError(str(exc)) from exc

    return validate_resumable_backtest_contract(current, settings=settings)


def validate_resumable_backtest_contract(
    run: PortfolioBacktestRun | None,
    *,
    settings: Settings | None = None,
) -> FrozenRunConfig:
    if run is None:
        raise BacktestContractMismatchError("portfolio backtest run not found")
    if run.account_mode != "BACKTEST":
        raise BacktestContractMismatchError(
            "portfolio write services support BACKTEST account mode only"
        )
    expected = {
        "portfolio_version": PORTFOLIO_VERSION,
        "execution_version": EXECUTION_VERSION,
        "accounting_version": ACCOUNTING_VERSION,
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
    }
    mismatches = [
        f"{field}: stored={getattr(run, field)}, current={value}"
        for field, value in expected.items()
        if getattr(run, field) != value
    ]
    if mismatches:
        raise BacktestContractMismatchError(
            "backtest contract mismatch: " + "; ".join(mismatches)
        )
    return validate_frozen_run_snapshot(run, settings=settings)


def validate_frozen_run_snapshot(
    run: PortfolioBacktestRun,
    *,
    settings: Settings | None = None,
) -> FrozenRunConfig:
    runtime = settings or get_settings()
    snapshot = run.config_snapshot
    if not isinstance(snapshot, dict):
        raise RunConfigIntegrityError("run config_snapshot must be a mapping")
    missing = [
        key
        for key in ("strategy", "opportunity", "portfolio", "execution", "accounting")
        if not isinstance(snapshot.get(key), dict)
    ]
    if missing:
        raise RunConfigIntegrityError(
            f"run config_snapshot missing mapping sections: {missing}"
        )

    try:
        portfolio = PortfolioConfig.model_validate(snapshot["portfolio"])
        execution = ExecutionConfig.model_validate(snapshot["execution"])
        accounting = AccountingConfig.model_validate(snapshot["accounting"])
    except ValidationError as exc:
        raise RunConfigIntegrityError(f"invalid frozen run config: {exc}") from exc

    identity_mismatches = []
    for name, actual, expected in (
        ("portfolio.version", portfolio.version, run.portfolio_version),
        ("execution.version", execution.version, run.execution_version),
        ("accounting.version", accounting.version, run.accounting_version),
        ("portfolio.account_mode", portfolio.account_mode, run.account_mode),
    ):
        if actual != expected:
            identity_mismatches.append(f"{name}: snapshot={actual}, run={expected}")
    if identity_mismatches:
        raise RunConfigIntegrityError(
            "frozen run identity mismatch: " + "; ".join(identity_mismatches)
        )

    hash_mismatches = []
    frozen_hashes = {
        "portfolio_config_hash": config_hash(portfolio.model_dump(mode="json")),
        "execution_config_hash": config_hash(execution.model_dump(mode="json")),
        "accounting_config_hash": config_hash(accounting.model_dump(mode="json")),
        "source_strategy_config_hash": analysis_strategy_hash(snapshot["strategy"]),
        "opportunity_config_hash": config_hash(snapshot["opportunity"]),
    }
    for field, actual in frozen_hashes.items():
        expected = getattr(run, field)
        if actual != expected:
            hash_mismatches.append(f"{field}: snapshot={actual}, run={expected}")
    if hash_mismatches:
        raise RunConfigIntegrityError(
            "frozen run hash mismatch: " + "; ".join(hash_mismatches)
        )

    value_mismatches = []
    if Decimal(run.initial_cash) != portfolio.initial_cash_cny:
        value_mismatches.append(
            "initial_cash: "
            f"snapshot={portfolio.initial_cash_cny}, run={run.initial_cash}"
        )
    if run.benchmark_code != portfolio.benchmark_code:
        value_mismatches.append(
            "benchmark_code: "
            f"snapshot={portfolio.benchmark_code}, run={run.benchmark_code}"
        )
    if value_mismatches:
        raise RunConfigIntegrityError(
            "frozen run value mismatch: " + "; ".join(value_mismatches)
        )

    runtime_mismatches = []
    runtime_values = {
        "algo_version": runtime.algo_version,
        "source_strategy_config_hash": analysis_strategy_hash(runtime.strategy),
        "opportunity_calc_version": OPPORTUNITY_CALC_VERSION,
        "opportunity_config_hash": config_hash(runtime.opportunity_config),
    }
    for field, actual in runtime_values.items():
        expected = getattr(run, field)
        if actual != expected:
            runtime_mismatches.append(f"{field}: runtime={actual}, run={expected}")
    if runtime_mismatches:
        raise RunConfigIntegrityError(
            "runtime source identity cannot execute frozen run: "
            + "; ".join(runtime_mismatches)
        )

    return FrozenRunConfig(
        run=run,
        portfolio=portfolio,
        execution=execution,
        accounting=accounting,
        strategy=snapshot["strategy"],
        opportunity=snapshot["opportunity"],
    )
