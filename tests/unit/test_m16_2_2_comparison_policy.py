import uuid
from dataclasses import replace
from decimal import Decimal

from app.services.agent.chat.comparison_contract import (
    ComparisonContract,
    compare_contracts,
)


def _contract(**changes) -> ComparisonContract:
    base = ComparisonContract(
        run_id=uuid.uuid4(),
        performance_id=uuid.uuid4(),
        start_date="2026-01-01",
        end_date="2026-03-31",
        trade_days=60,
        trade_dates=("2026-01-02", "2026-01-05"),
        frequency="DAILY",
        currency="CNY",
        initial_cash=Decimal("1000000.0000"),
        benchmark_code="000300.SH",
        benchmark_source_hash="b" * 64,
        portfolio_version="portfolio_v3",
        portfolio_config_hash="p" * 64,
        execution_version="execution_v3",
        execution_config_hash="e" * 64,
        accounting_version="accounting_v3",
        accounting_config_hash="a" * 64,
        backtest_engine_version="backtest_v7",
        performance_version="performance_v1",
        performance_config_hash="f" * 64,
        performance_source_hash="1" * 64,
        risk_version="risk_v1",
        risk_config_hash="r" * 64,
        risk_source_hash="2" * 64,
        trade_version="trade_v1",
        trade_config_hash="t" * 64,
        trade_source_hash="3" * 64,
        period_version="period_v1",
        period_config_hash="d" * 64,
        period_source_hash="4" * 64,
        execution_assumptions='{"slippage_bps":"5"}',
        accounting_assumptions='{"cost_basis":"MOVING_AVERAGE"}',
    )
    return replace(base, **changes)


def test_identical_core_contracts_are_comparable() -> None:
    first = _contract()
    second = _contract(
        run_id=uuid.uuid4(),
        performance_id=uuid.uuid4(),
        portfolio_config_hash="q" * 64,
        performance_source_hash="5" * 64,
        risk_source_hash="6" * 64,
        trade_source_hash="7" * 64,
        period_source_hash="8" * 64,
    )
    decision = compare_contracts(
        [first, second],
        metric_paths=[
            "records.0.performance.cumulative_return",
            "records.0.performance.cumulative_return",
        ],
    )
    assert decision.state == "COMPARABLE"
    assert decision.reason_codes == ()


def test_different_dates_costs_and_initial_cash_require_context() -> None:
    first = _contract()
    second = _contract(
        run_id=uuid.uuid4(),
        performance_id=uuid.uuid4(),
        start_date="2026-02-01",
        end_date="2026-04-30",
        trade_days=59,
        trade_dates=("2026-02-02",),
        initial_cash=Decimal("2000000.0000"),
        execution_config_hash="x" * 64,
        execution_assumptions='{"slippage_bps":"10"}',
    )
    decision = compare_contracts(
        [first, second],
        metric_paths=["records.0.performance.cumulative_return"] * 2,
    )
    assert decision.state == "CONTEXT_REQUIRED"
    assert set(decision.reason_codes) >= {
        "DATE_RANGE_MISMATCH",
        "TRADE_DATE_SET_MISMATCH",
        "SAMPLE_SIZE_MISMATCH",
        "INITIAL_CASH_MISMATCH",
        "EXECUTION_CONFIG_MISMATCH",
        "EXECUTION_ASSUMPTION_MISMATCH",
    }


def test_benchmark_difference_blocks_excess_but_contextualizes_raw_return() -> None:
    first = _contract()
    second = _contract(
        run_id=uuid.uuid4(),
        performance_id=uuid.uuid4(),
        benchmark_code="000905.SH",
        benchmark_source_hash="z" * 64,
    )
    raw = compare_contracts(
        [first, second],
        metric_paths=["records.0.performance.cumulative_return"] * 2,
    )
    assert raw.state == "CONTEXT_REQUIRED"
    assert raw.reason_codes == ("BENCHMARK_MISMATCH",)

    excess = compare_contracts(
        [first, second],
        metric_paths=["records.0.risk.excess_cumulative_return"] * 2,
    )
    assert excess.state == "INCOMPATIBLE"
    assert excess.reason_codes == ("BENCHMARK_MISMATCH",)


def test_frequency_or_accounting_version_mismatch_is_incompatible() -> None:
    first = _contract()
    second = _contract(
        run_id=uuid.uuid4(),
        performance_id=uuid.uuid4(),
        frequency="WEEKLY",
        portfolio_version="portfolio_v4",
        accounting_version="accounting_v4",
    )
    decision = compare_contracts(
        [first, second],
        metric_paths=["records.0.performance.annualized_return"] * 2,
    )
    assert decision.state == "INCOMPATIBLE"
    assert set(decision.reason_codes) == {
        "FREQUENCY_MISMATCH",
        "PORTFOLIO_VERSION_MISMATCH",
        "ACCOUNTING_VERSION_MISMATCH",
    }


def test_missing_second_contract_is_not_assumed_comparable() -> None:
    decision = compare_contracts(
        [_contract()],
        metric_paths=["records.0.performance.cumulative_return"],
    )
    assert decision.state == "INCOMPATIBLE"
    assert decision.reason_codes == ("COMPARISON_CONTRACT_MISSING",)
