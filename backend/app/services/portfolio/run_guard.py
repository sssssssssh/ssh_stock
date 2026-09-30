from app.models.portfolio import PortfolioBacktestRun


def validate_writable_run(run: PortfolioBacktestRun | None) -> PortfolioBacktestRun:
    if run is None:
        raise LookupError("portfolio backtest run not found")
    if run.account_mode != "BACKTEST":
        raise ValueError("portfolio write services support BACKTEST account mode only")
    if run.status != "RUNNING":
        raise ValueError(f"portfolio run must be RUNNING, got {run.status}")
    return run
