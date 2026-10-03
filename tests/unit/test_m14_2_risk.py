import inspect
import math
import uuid
from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest
from app.core.performance_risk_config import PerformanceRiskConfig
from app.domain.performance import risk_engine, statistics
from app.domain.performance.risk_contracts import RiskSourceRow, RiskSourceSnapshot
from app.domain.performance.risk_engine import RiskEngine
from app.services.performance.risk_identity import (
    benchmark_source_hash,
    performance_risk_lock_key,
    risk_source_hash,
)
from app.services.performance.risk_source import (
    PerformanceRiskSourceError,
    PerformanceRiskSourceProvider,
)
from pydantic import ValidationError


def _config(**overrides) -> PerformanceRiskConfig:
    values = {
        "version": "risk_v1",
        "risk_free_rate_annual": Decimal("0"),
        "minimum_observations": 2,
        "short_sample_warning_trade_days": 20,
        "zero_denominator_epsilon": Decimal("0.000000000001"),
    }
    values.update(overrides)
    return PerformanceRiskConfig.model_validate(values)


def _source(
    strategy_returns: list[str],
    benchmark_returns: list[str],
    *,
    annualized_return: str = "0.12",
    max_drawdown: str = "-0.10",
) -> RiskSourceSnapshot:
    assert len(strategy_returns) == len(benchmark_returns)
    start = date(2026, 1, 5)
    strategy_nav = Decimal("1")
    benchmark_close = Decimal("100")
    rows = []
    for index, (strategy_raw, benchmark_raw) in enumerate(
        zip(strategy_returns, benchmark_returns, strict=True)
    ):
        strategy_return = Decimal(strategy_raw)
        benchmark_return = Decimal(benchmark_raw)
        strategy_nav *= Decimal("1") + strategy_return
        pre_close = benchmark_close
        benchmark_close *= Decimal("1") + benchmark_return
        rows.append(
            RiskSourceRow(
                trade_date=start + timedelta(days=index),
                strategy_nav=strategy_nav,
                strategy_daily_return=strategy_return,
                benchmark_pre_close=pre_close,
                benchmark_close=benchmark_close,
            )
        )
    performance_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    return RiskSourceSnapshot(
        run_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        performance_id=performance_id,
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
        performance_source_hash="b" * 64,
        risk_version="risk_v1",
        risk_config_hash="c" * 64,
        benchmark_code="000300.SH",
        benchmark_source_hash="d" * 64,
        risk_source_hash="e" * 64,
        start_date=rows[0].trade_date,
        end_date=rows[-1].trade_date,
        trade_days=len(rows),
        annualization_trade_days=252,
        strategy_annualized_return=Decimal(annualized_return),
        strategy_max_drawdown=Decimal(max_drawdown),
        rows=tuple(rows),
    )


def test_risk_config_is_independent_strict_and_validated() -> None:
    assert _config().version == "risk_v1"
    with pytest.raises(ValidationError):
        PerformanceRiskConfig.model_validate(
            {**_config().model_dump(), "annualization_trade_days": 250}
        )
    with pytest.raises(ValidationError):
        _config(risk_free_rate_annual=Decimal("-1"))
    with pytest.raises(ValidationError):
        _config(minimum_observations=1)


def test_statistics_use_sample_variance_covariance_and_decimal() -> None:
    values = (Decimal("1"), Decimal("2"), Decimal("3"))
    other = (Decimal("2"), Decimal("4"), Decimal("6"))
    assert statistics.mean(values) == Decimal("2")
    assert statistics.sample_variance(values) == Decimal("1")
    assert statistics.sample_stddev(values) == Decimal("1")
    assert statistics.sample_covariance(values, other) == Decimal("2")


def test_day_one_uses_pre_close_and_day_two_uses_previous_close() -> None:
    result = RiskEngine().calculate(
        _source(["0.10", "0.05"], ["0.10", "0.10"]), _config()
    )
    assert result.daily[0].benchmark_reference_close == Decimal("100")
    assert result.daily[0].benchmark_daily_return == Decimal("0.10")
    assert result.daily[1].benchmark_reference_close == Decimal("110.00")
    assert result.daily[1].benchmark_daily_return == Decimal("0.10")


def test_benchmark_pre_close_continuity_is_fail_closed() -> None:
    source = _source(["0.01", "0.02"], ["0.01", "0.02"])
    second = source.rows[1]
    broken = source.__class__(
        **{
            **source.__dict__,
            "rows": (
                source.rows[0],
                second.__class__(
                    **{**second.__dict__, "benchmark_pre_close": Decimal("999")}
                ),
            ),
        }
    )
    with pytest.raises(ValueError, match="BENCHMARK_PRE_CLOSE_MISMATCH"):
        RiskEngine().calculate(broken, _config())


def test_active_return_relative_nav_and_excess_cumulative_use_frozen_formulas() -> None:
    result = RiskEngine().calculate(
        _source(["0.10", "-0.05"], ["0.05", "0.02"]), _config()
    )
    first = result.daily[0]
    assert first.active_return == Decimal("0.05")
    assert first.benchmark_nav == Decimal("1.05")
    with localcontext() as context:
        context.prec = 60
        assert first.relative_nav == Decimal("1.10") / Decimal("1.05")
        assert first.excess_cumulative_return == first.relative_nav - Decimal("1")
        assert (
            result.excess_cumulative_return
            == result.relative_nav_final - Decimal("1")
        )


def test_volatility_sharpe_sortino_tracking_information_beta_alpha_correlation() -> None:
    strategy = (Decimal("0.01"), Decimal("-0.02"), Decimal("0.03"))
    benchmark = (Decimal("0.005"), Decimal("-0.01"), Decimal("0.02"))
    result = RiskEngine().calculate(
        _source([str(value) for value in strategy], [str(value) for value in benchmark]),
        _config(short_sample_warning_trade_days=3),
    )
    with localcontext() as context:
        context.prec = 60
        sqrt_a = Decimal(252).sqrt()
        active = tuple(
            left - right for left, right in zip(strategy, benchmark, strict=True)
        )
        expected_beta = statistics.sample_covariance(
            strategy, benchmark
        ) / statistics.sample_variance(benchmark)
        assert (
            result.strategy_annualized_volatility
            == statistics.sample_stddev(strategy) * sqrt_a
        )
        assert (
            result.benchmark_annualized_volatility
            == statistics.sample_stddev(benchmark) * sqrt_a
        )
        assert result.sharpe_ratio == (
            statistics.mean(strategy) / statistics.sample_stddev(strategy) * sqrt_a
        )
        downside = (
            sum(
                (min(value, Decimal("0")) ** 2 for value in strategy), Decimal("0")
            )
            / Decimal(3)
        ).sqrt()
        assert result.downside_deviation_annualized == downside * sqrt_a
        assert result.sortino_ratio == statistics.mean(strategy) / downside * sqrt_a
        assert result.tracking_error == statistics.sample_stddev(active) * sqrt_a
        assert result.information_ratio == (
            statistics.mean(active) / statistics.sample_stddev(active) * sqrt_a
        )
        assert result.beta == expected_beta
        assert result.alpha_daily == (
            statistics.mean(strategy)
            - expected_beta * statistics.mean(benchmark)
        )
        assert result.alpha_annualized == result.alpha_daily * Decimal(252)
        assert result.correlation == statistics.sample_covariance(
            strategy, benchmark
        ) / (statistics.sample_stddev(strategy) * statistics.sample_stddev(benchmark))


def test_calmar_uses_base_performance_values_without_recomputing_drawdown() -> None:
    result = RiskEngine().calculate(
        _source(
            ["0.01", "0.02"],
            ["0.005", "0.01"],
            annualized_return="0.42",
            max_drawdown="-0.07",
        ),
        _config(),
    )
    assert result.calmar_ratio == Decimal("6")


def test_one_observation_keeps_daily_benchmark_but_nulls_statistical_metrics() -> None:
    result = RiskEngine().calculate(_source(["0.01"], ["0.02"]), _config())
    assert len(result.daily) == 1
    assert result.benchmark_annualized_return is not None
    for value in (
        result.strategy_annualized_volatility,
        result.benchmark_annualized_volatility,
        result.downside_deviation_annualized,
        result.sharpe_ratio,
        result.sortino_ratio,
        result.tracking_error,
        result.information_ratio,
        result.alpha_daily,
        result.alpha_annualized,
        result.beta,
        result.correlation,
    ):
        assert value is None
    assert "INSUFFICIENT_RISK_OBSERVATIONS" in result.warnings


@pytest.mark.parametrize(
    ("strategy", "benchmark", "expected_warning", "null_field"),
    [
        (["0.01", "0.01"], ["0.00", "0.02"], "ZERO_STRATEGY_VOLATILITY", "sharpe_ratio"),
        (["0.01", "0.02"], ["0.00", "0.01"], "ZERO_DOWNSIDE_DEVIATION", "sortino_ratio"),
        (["0.01", "0.02"], ["0.01", "0.02"], "ZERO_TRACKING_ERROR", "information_ratio"),
        (["0.01", "0.02"], ["0.01", "0.01"], "ZERO_BENCHMARK_VARIANCE", "beta"),
    ],
)
def test_zero_denominator_metrics_return_null_with_warning(
    strategy, benchmark, expected_warning, null_field
) -> None:
    result = RiskEngine().calculate(_source(strategy, benchmark), _config())
    assert getattr(result, null_field) is None
    assert expected_warning in result.warnings


def test_zero_drawdown_and_undefined_correlation_are_explicit() -> None:
    result = RiskEngine().calculate(
        _source(["0.01", "0.01"], ["0.02", "0.02"], max_drawdown="0"),
        _config(),
    )
    assert result.calmar_ratio is None
    assert result.correlation is None
    assert "ZERO_MAX_DRAWDOWN" in result.warnings
    assert "CORRELATION_UNDEFINED" in result.warnings
    assert result.warnings == tuple(sorted(set(result.warnings)))


@pytest.mark.parametrize("value", [None, 0.0, -1.0, float("nan"), float("inf")])
def test_benchmark_nonpositive_nonfinite_or_missing_prices_fail_closed(value) -> None:
    with pytest.raises(PerformanceRiskSourceError) as exc_info:
        PerformanceRiskSourceProvider._benchmark_price(value)
    assert exc_info.value.code == "BENCHMARK_SOURCE_INVALID"


def test_benchmark_and_risk_source_hashes_are_stable_and_sensitive() -> None:
    source = _source(["0.01", "0.02"], ["0.005", "0.01"])
    first = benchmark_source_hash(benchmark_code="000300.SH", rows=source.rows)
    second = benchmark_source_hash(benchmark_code="000300.SH", rows=source.rows)
    reordered = benchmark_source_hash(
        benchmark_code="000300.SH", rows=tuple(reversed(source.rows))
    )
    revised_rows = list(source.rows)
    revised_rows[-1] = revised_rows[-1].__class__(
        **{**revised_rows[-1].__dict__, "benchmark_close": Decimal("999")}
    )
    assert first == second == reordered
    assert first != benchmark_source_hash(
        benchmark_code="000300.SH", rows=tuple(revised_rows)
    )
    risk_hash = risk_source_hash(
        performance_id=source.performance_id,
        performance_version=source.performance_version,
        performance_config_hash=source.performance_config_hash,
        performance_source_hash=source.performance_source_hash,
        risk_version="risk_v1",
        risk_config_hash=source.risk_config_hash,
        benchmark_code="000300.SH",
        benchmark_hash=first,
    )
    assert len(first) == len(risk_hash) == 64
    assert performance_risk_lock_key(source.performance_id) == performance_risk_lock_key(
        source.performance_id
    )


def test_risk_domain_has_no_orm_sqlalchemy_numpy_or_pandas_imports() -> None:
    source = inspect.getsource(risk_engine) + inspect.getsource(statistics)
    for forbidden in ("sqlalchemy", "Session", "app.models", "numpy", "pandas"):
        assert forbidden not in source


def test_float_nan_fixture_is_actually_nonfinite() -> None:
    assert not math.isfinite(float("nan"))
