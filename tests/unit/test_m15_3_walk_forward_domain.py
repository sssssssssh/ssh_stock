import inspect
from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.core.walk_forward_config import WalkForwardConfig
from app.domain.performance.metrics import annualized_return
from app.domain.performance.statistics import sample_stddev
from app.domain.walk_forward import metrics, stability, windows
from app.domain.walk_forward.contracts import DailyReturnPoint, WindowMetricInput
from app.domain.walk_forward.metrics import calculate_validation_metrics
from app.domain.walk_forward.stability import calculate_parameter_stability
from app.domain.walk_forward.windows import WindowPlanError, plan_windows


def _dates(count: int) -> tuple[date, ...]:
    start = date(2026, 1, 1)
    return tuple(start + timedelta(days=index) for index in range(count))


def _parameters(min_score: str, top_n: int) -> dict[str, object]:
    return {
        "candidate.min_score": min_score,
        "candidate.top_n": top_n,
        "construction.max_positions": 5,
        "construction.max_single_position_weight": "0.2",
        "construction.min_cash_ratio": "0.1",
        "construction.max_new_positions_per_day": 2,
    }


def _metric_input(
    window_no: int,
    dates: tuple[date, ...],
    returns: tuple[str, ...],
    *,
    parameter_hash: str,
    parameters: dict[str, object],
    train_sharpe: Decimal | None = Decimal("1.2"),
    oos_sharpe: Decimal | None = Decimal("0.7"),
) -> WindowMetricInput:
    return WindowMetricInput(
        window_no=window_no,
        selected_parameter_hash=parameter_hash,
        selected_parameter_values=parameters,
        daily_returns=tuple(
            DailyReturnPoint(day, Decimal(value), Decimal("0.01"))
            for day, value in zip(dates, returns, strict=True)
        ),
        train_annualized_return=Decimal("0.30"),
        train_max_drawdown_abs=Decimal("0.08"),
        train_sharpe_ratio=train_sharpe,
        train_annualized_turnover=Decimal("3"),
        oos_cumulative_return=Decimal("0.05"),
        oos_annualized_return=Decimal("0.20"),
        oos_max_drawdown_abs=Decimal("0.12"),
        oos_sharpe_ratio=oos_sharpe,
        oos_annualized_turnover=Decimal("4"),
        oos_total_cost_to_initial_capital=Decimal("0.01"),
        oos_win_rate=Decimal("0.6"),
        oos_profit_factor=Decimal("1.4"),
    )


def test_rolling_and_expanding_windows_use_complete_contiguous_slices() -> None:
    dates = _dates(11)
    rolling = plan_windows(
        dates,
        mode="ROLLING",
        train_trade_days=4,
        test_trade_days=2,
        step_trade_days=2,
        minimum_windows=2,
        max_windows=10,
    )
    expanding = plan_windows(
        dates,
        mode="EXPANDING",
        train_trade_days=4,
        test_trade_days=2,
        step_trade_days=2,
        minimum_windows=2,
        max_windows=10,
    )
    assert rolling.unused_tail_trade_days == 1
    assert [row.train_trade_dates for row in rolling.windows] == [
        dates[0:4],
        dates[2:6],
        dates[4:8],
    ]
    assert [row.test_trade_dates for row in rolling.windows] == [
        dates[4:6],
        dates[6:8],
        dates[8:10],
    ]
    assert [row.train_trade_dates for row in expanding.windows] == [
        dates[0:4],
        dates[0:6],
        dates[0:8],
    ]
    assert rolling.windows[0].test_date_hash == windows.date_set_hash(dates[4:6])


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"step_trade_days": 1}, "WALK_FORWARD_CONFIG_INVALID"),
        ({"minimum_windows": 4}, "WALK_FORWARD_INSUFFICIENT_WINDOWS"),
        ({"max_windows": 2}, "WALK_FORWARD_WINDOW_LIMIT_EXCEEDED"),
    ],
)
def test_window_planner_fails_closed(overrides, code) -> None:
    arguments = {
        "mode": "ROLLING",
        "train_trade_days": 4,
        "test_trade_days": 2,
        "step_trade_days": 2,
        "minimum_windows": 2,
        "max_windows": 10,
    }
    arguments.update(overrides)
    with pytest.raises(WindowPlanError) as raised:
        plan_windows(_dates(10), **arguments)
    assert raised.value.code == code


def test_stitched_metrics_compound_daily_returns_and_degrade_in_fixed_direction() -> None:
    dates = _dates(4)
    rows = (
        _metric_input(
            1,
            dates[:2],
            ("0.10", "-0.10"),
            parameter_hash="b" * 64,
            parameters=_parameters("70", 20),
        ),
        _metric_input(
            2,
            dates[2:],
            ("0.20", "0"),
            parameter_hash="a" * 64,
            parameters=_parameters("75", 30),
            train_sharpe=None,
        ),
    )
    result = calculate_validation_metrics(
        rows,
        annualization_trade_days=252,
        risk_free_rate_annual=Decimal("0"),
        minimum_observations=2,
        short_sample_warning_trade_days=120,
    )
    strategy = tuple(
        point.strategy_return for row in rows for point in row.daily_returns
    )
    assert result.stitched_oos_final_nav == Decimal("1.18800")
    assert result.stitched_oos_cumulative_return == Decimal("0.18800")
    assert result.stitched_oos_annualized_return == annualized_return(
        Decimal("1.18800"), trade_days=4, annualization_trade_days=252
    )
    assert result.stitched_oos_max_drawdown == Decimal("-0.1")
    assert [row.trade_date for row in result.stitched_daily] == list(dates)
    assert result.stitched_daily[-1].strategy_nav == Decimal("1.18800")
    assert result.stitched_daily[-1].benchmark_nav == Decimal("1.04060401")
    assert result.stitched_daily[-1].relative_nav == (
        Decimal("1.18800") / Decimal("1.04060401")
    )
    assert result.stitched_oos_annualized_volatility == sample_stddev(
        strategy
    ) * Decimal(252).sqrt()
    assert result.windows[0].return_degradation == Decimal("0.10")
    assert result.windows[0].sharpe_degradation == Decimal("0.5")
    assert result.windows[0].drawdown_worsening == Decimal("0.04")
    assert result.windows[0].turnover_change == Decimal("1")
    assert result.windows[1].sharpe_degradation is None
    assert result.warnings == (
        "NULL_OOS_OPTIONAL_METRICS_PRESENT",
        "SHORT_STITCHED_OOS_SAMPLE",
        "TRAIN_OOS_OPTIONAL_METRIC_NOT_COMPARABLE",
    )


def test_zero_stitched_volatility_produces_null_sharpe_and_stable_warning() -> None:
    row = _metric_input(
        1,
        _dates(2),
        ("0", "0"),
        parameter_hash="a" * 64,
        parameters=_parameters("70", 20),
    )
    result = calculate_validation_metrics(
        (row,),
        annualization_trade_days=252,
        risk_free_rate_annual=Decimal("0.02"),
        minimum_observations=2,
        short_sample_warning_trade_days=2,
    )
    assert result.stitched_oos_annualized_volatility == 0
    assert result.stitched_oos_sharpe_ratio is None
    assert result.warnings == ("ZERO_STITCHED_OOS_VOLATILITY",)


def test_parameter_stability_uses_lexical_hash_tie_and_canonical_rates() -> None:
    first = _parameters("70", 20)
    first["candidate.min_score"] = Decimal("70.0")
    result = calculate_parameter_stability(
        (
            ("b" * 64, first),
            ("a" * 64, _parameters("75", 30)),
        )
    )
    assert result.unique_selected_parameter_hash_count == 2
    assert result.dominant_parameter_hash == "a" * 64
    assert result.dominant_parameter_hash_count == 1
    assert result.dominant_parameter_hash_rate == Decimal("0.5")
    for parameter_name in _parameters("70", 20):
        selected = [row for row in result.rows if row.parameter_name == parameter_name]
        assert sum(row.selected_window_count for row in selected) == 2
        assert sum((row.selected_rate for row in selected), Decimal(0)) == 1


def test_parameter_rates_sum_exactly_for_repeating_decimal_denominators() -> None:
    result = calculate_parameter_stability(
        tuple(
            (str(index) * 64, _parameters(str(65 + index), 20 + index))
            for index in range(1, 4)
        )
    )
    for parameter_name in _parameters("70", 20):
        selected = [row for row in result.rows if row.parameter_name == parameter_name]
        assert sum((row.selected_rate for row in selected), Decimal(0)) == 1


def test_parameter_stability_tracks_adjacent_hash_and_canonical_value_switches() -> None:
    first = _parameters("70", 20)
    same_value = _parameters("70.0", 20)
    changed = _parameters("70", 30)
    result = calculate_parameter_stability(
        (
            ("a" * 64, first),
            ("a" * 64, same_value),
            ("b" * 64, changed),
            ("a" * 64, first),
        ),
        frequent_switch_rate_threshold=Decimal("0.5"),
        low_dominant_parameter_rate_threshold=Decimal("0.8"),
    )
    assert result.transition_count == 3
    assert result.switch_count == 2
    assert result.switch_rate == Decimal(2) / Decimal(3)
    assert result.dominant_parameter_hash_count == 3
    assert result.dominant_parameter_hash_rate == Decimal("0.75")
    top_n = [
        row for row in result.rows if row.parameter_name == "candidate.top_n"
    ]
    assert {row.adjacent_value_switch_count for row in top_n} == {2}
    min_score = [
        row for row in result.rows if row.parameter_name == "candidate.min_score"
    ]
    assert {row.adjacent_value_switch_count for row in min_score} == {0}
    assert result.warnings == (
        "FREQUENT_PARAMETER_SWITCHING",
        "LOW_DOMINANT_PARAMETER_RATE",
    )


def test_single_window_switch_rates_are_null() -> None:
    result = calculate_parameter_stability(
        (("a" * 64, _parameters("70", 20)),)
    )
    assert result.transition_count == 0
    assert result.switch_count == 0
    assert result.switch_rate is None
    assert all(row.adjacent_value_switch_rate is None for row in result.rows)


def test_walk_forward_config_and_domain_dependency_boundaries() -> None:
    config = WalkForwardConfig.model_validate(
        {
            "version": "walk_forward_v1",
            "exchange": " sse ",
            "minimum_windows": 2,
            "max_windows": 36,
            "max_actions_per_advance": 20,
            "validation_policy": {
                "version": "walk_forward_validation_policy_v1",
                "minimum_stitched_oos_observations": 2,
                "short_oos_warning_trade_days": 120,
                "frequent_parameter_switch_rate_threshold": "0.5",
                "low_dominant_parameter_rate_threshold": "0.5",
            },
        }
    )
    assert config.exchange == "SSE"
    with pytest.raises(ValueError):
        WalkForwardConfig.model_validate(
            {**config.model_dump(), "minimum_windows": 3, "max_windows": 2}
        )
    for module in (metrics, stability, windows):
        source = inspect.getsource(module)
        for forbidden in (
            "sqlalchemy",
            "Session",
            "FastAPI",
            "app.models",
            "JobRun",
            "float(",
            "numpy",
            "pandas",
        ):
            assert forbidden not in source
