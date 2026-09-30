from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.config import Settings, get_settings
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
from app.services.portfolio.account_gateway import (
    validate_previous_snapshot_integrity,
)
from app.services.portfolio.accounting import (
    ACCOUNTING_SOURCE_INCOMPLETE,
    AccountingSourceError,
)
from app.services.portfolio.run_guard import (
    RunConfigIntegrityError,
    validate_current_backtest_contract,
)

DAY = date(2026, 9, 30)


def _run(
    settings: Settings | None = None,
    *,
    initial_cash: Decimal = Decimal("1000000"),
    benchmark_code: str = "000300.SH",
) -> PortfolioBacktestRun:
    runtime = settings or get_settings()
    portfolio = runtime.portfolio_config.model_copy(
        update={
            "initial_cash_cny": initial_cash,
            "benchmark_code": benchmark_code,
        }
    ).model_dump(mode="json")
    execution = runtime.execution_config.model_dump(mode="json")
    accounting = runtime.accounting_config.model_dump(mode="json")
    return PortfolioBacktestRun(
        account_mode="BACKTEST",
        status="RUNNING",
        start_date=DAY,
        end_date=DAY,
        initial_cash=initial_cash,
        benchmark_code=benchmark_code,
        algo_version=runtime.algo_version,
        source_strategy_config_hash=analysis_strategy_hash(runtime.strategy),
        opportunity_calc_version=OPPORTUNITY_CALC_VERSION,
        opportunity_config_hash=config_hash(runtime.opportunity_config),
        portfolio_version=PORTFOLIO_VERSION,
        portfolio_config_hash=config_hash(portfolio),
        execution_version=EXECUTION_VERSION,
        execution_config_hash=config_hash(execution),
        accounting_version=ACCOUNTING_VERSION,
        accounting_config_hash=config_hash(accounting),
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        config_snapshot={
            "strategy": deepcopy(runtime.strategy),
            "opportunity": deepcopy(runtime.opportunity_config),
            "portfolio": portfolio,
            "execution": execution,
            "accounting": accounting,
        },
    )


def _nav(**changes):
    values = {
        "trade_date": DAY,
        "position_count": 1,
        "cash": Decimal("9000"),
        "market_value": Decimal("1000"),
        "total_assets": Decimal("10000"),
        "nav": Decimal("1"),
        "gross_exposure": Decimal("0.1"),
        "net_exposure": Decimal("0.1"),
        "trading_cost": Decimal("0"),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _position(**changes):
    values = {
        "ts_code": "000001.SZ",
        "trade_date": DAY,
        "quantity": 100,
        "available_quantity": 50,
        "avg_cost": Decimal("9"),
        "close_price": Decimal("10"),
        "market_value": Decimal("1000"),
        "weight": Decimal("0.1"),
        "unrealized_pnl": Decimal("100"),
        "realized_pnl": Decimal("0"),
        "valuation_source": "RAW_CLOSE",
        "adj_factor": Decimal("1"),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_frozen_run_config_accepts_effective_cash_and_benchmark_override() -> None:
    run = _run(
        initial_cash=Decimal("2500000"), benchmark_code="000905.SH"
    )
    contract = validate_current_backtest_contract(run)
    assert contract.portfolio.initial_cash_cny == Decimal("2500000")
    assert contract.portfolio.benchmark_code == "000905.SH"
    assert contract.execution.version == "execution_v3"
    assert contract.accounting.version == "accounting_v3"


@pytest.mark.parametrize("mutation", ["missing", "hash", "cash", "version"])
def test_frozen_run_config_rejects_corruption(mutation) -> None:
    run = _run()
    if mutation == "missing":
        del run.config_snapshot["accounting"]
    elif mutation == "hash":
        run.execution_config_hash = "0" * 64
    elif mutation == "cash":
        run.initial_cash = Decimal("999999")
    else:
        run.config_snapshot["accounting"]["version"] = "accounting_v2"
    with pytest.raises(RunConfigIntegrityError):
        validate_current_backtest_contract(run)


@pytest.mark.parametrize("source", ["algo", "strategy", "opportunity"])
def test_frozen_run_rejects_runtime_source_identity_change(source) -> None:
    run = _run()
    runtime = get_settings().model_copy(deep=True)
    if source == "algo":
        runtime.algo_version = "changed"
    elif source == "strategy":
        strategy = deepcopy(runtime.strategy)
        strategy["factor"] = {**strategy["factor"], "m1332_probe": 1}
        runtime.strategy = strategy
    else:
        opportunity = deepcopy(runtime.opportunity_config)
        opportunity["m1332_probe"] = True
        runtime.opportunity_config = opportunity
    with pytest.raises(RunConfigIntegrityError, match="runtime source identity"):
        validate_current_backtest_contract(run, settings=runtime)


def test_previous_snapshot_integrity_accepts_valid_position_and_empty_account() -> None:
    validate_previous_snapshot_integrity(
        _nav(), [_position()], Decimal("10000")
    )
    validate_previous_snapshot_integrity(
        _nav(
            position_count=0,
            cash=Decimal("10000"),
            market_value=Decimal("0"),
            total_assets=Decimal("10000"),
            gross_exposure=Decimal("0"),
            net_exposure=Decimal("0"),
        ),
        [],
        Decimal("10000"),
    )


@pytest.mark.parametrize(
    ("nav", "positions", "message"),
    [
        (_nav(position_count=1), [], "position_count mismatch"),
        (_nav(position_count=0), [_position()], "position_count mismatch"),
        (_nav(market_value=Decimal("999")), [_position()], "market value mismatch"),
        (_nav(total_assets=Decimal("9999")), [_position()], "total assets mismatch"),
        (_nav(nav=Decimal("1.01")), [_position()], "NAV ratio mismatch"),
        (_nav(), [_position(quantity=0, market_value=Decimal("0"))], "quantity"),
        (_nav(), [_position(available_quantity=101)], "available quantity"),
        (_nav(), [_position(close_price=None)], "close price"),
        (_nav(), [_position(avg_cost=Decimal("-1"))], "average cost"),
    ],
)
def test_previous_snapshot_integrity_fails_closed(nav, positions, message) -> None:
    with pytest.raises(AccountingSourceError, match=message) as exc:
        validate_previous_snapshot_integrity(nav, positions, Decimal("10000"))
    assert exc.value.reason_code == ACCOUNTING_SOURCE_INCOMPLETE


def test_previous_snapshot_nav_allows_only_numeric_scale_rounding() -> None:
    validate_previous_snapshot_integrity(
        _nav(nav=Decimal("1.000000004")), [_position()], Decimal("10000")
    )


@pytest.mark.parametrize(
    ("nav_changes", "position_changes", "message"),
    [
        ({"gross_exposure": Decimal("0.2")}, {}, "gross_exposure mismatch"),
        ({}, {"weight": Decimal("0.2")}, "weight mismatch"),
        ({}, {"unrealized_pnl": Decimal("99")}, "unrealized PnL mismatch"),
        ({}, {"valuation_source": None}, "valuation source"),
        ({}, {"adj_factor": None}, "numeric fields"),
        ({}, {"adj_factor": Decimal("-1")}, "adjustment factor"),
        ({}, {"realized_pnl": Decimal("NaN")}, "numeric fields"),
        ({"trading_cost": Decimal("-1")}, {}, "non-negative"),
    ],
)
def test_previous_snapshot_integrity_rejects_extended_ledger_corruption(
    nav_changes, position_changes, message
) -> None:
    with pytest.raises(AccountingSourceError, match=message):
        validate_previous_snapshot_integrity(
            _nav(**nav_changes),
            [_position(**position_changes)],
            Decimal("10000"),
        )


def test_previous_snapshot_accepts_suspended_carry_forward_valuation() -> None:
    validate_previous_snapshot_integrity(
        _nav(),
        [_position(valuation_source="CARRY_FORWARD")],
        Decimal("10000"),
    )
