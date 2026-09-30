from app.models.portfolio import PortfolioBacktestRun
from app.services.analysis_identity import (
    ACCOUNTING_VERSION,
    BACKTEST_ENGINE_VERSION,
    EXECUTION_VERSION,
    PORTFOLIO_VERSION,
)


class BacktestContractMismatchError(RuntimeError):
    pass


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
) -> PortfolioBacktestRun:
    try:
        current = validate_writable_run(run)
    except (LookupError, ValueError) as exc:
        raise BacktestContractMismatchError(str(exc)) from exc

    expected = {
        "portfolio_version": PORTFOLIO_VERSION,
        "execution_version": EXECUTION_VERSION,
        "accounting_version": ACCOUNTING_VERSION,
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
    }
    mismatches = [
        f"{field}: stored={getattr(current, field)}, current={value}"
        for field, value in expected.items()
        if getattr(current, field) != value
    ]
    if mismatches:
        raise BacktestContractMismatchError(
            "backtest contract mismatch: " + "; ".join(mismatches)
        )
    return current
