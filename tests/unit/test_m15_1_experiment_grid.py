from decimal import Decimal

import pytest
from app.core.portfolio_config import PortfolioConfig
from app.domain.experiment import (
    EXPERIMENT_PARAMETER_ORDER,
    ExperimentGridError,
    expand_grid,
)


@pytest.fixture
def portfolio_config() -> PortfolioConfig:
    return PortfolioConfig.model_validate(
        {
            "version": "portfolio_v3",
            "account_mode": "BACKTEST",
            "initial_cash_cny": "1000000",
            "benchmark_code": "000300.SH",
            "candidate": {
                "source": "STOCK_OPPORTUNITY_DAILY",
                "allowed_stages": ["RIGHT_SIDE", "TREND"],
                "ranking_field": "opportunity_score",
                "ranking_direction": "DESC",
                "min_score": "70",
                "top_n": 10,
            },
            "construction": {
                "weighting": "EQUAL",
                "max_positions": 10,
                "max_single_position_weight": "0.1",
                "min_cash_ratio": "0.02",
                "max_new_positions_per_day": 3,
                "rebalance_frequency": "DAILY",
                "sizing_basis": "SIGNAL_CLOSE_TOTAL_ASSETS",
                "sizing_price": "RAW_CLOSE",
                "quantity_rounding": "FLOOR_TO_TRADABLE",
                "pending_order_policy": "RECONCILE",
                "order_type": "NEXT_OPEN",
                "small_delta_policy": "SKIP",
            },
        }
    )


def test_unspecified_parameters_inherit_complete_base_values(
    portfolio_config: PortfolioConfig,
) -> None:
    result = expand_grid(
        base_portfolio=portfolio_config,
        grid={},
        max_trials=128,
        max_values_per_parameter=20,
    )

    assert list(result.parameter_space) == list(EXPERIMENT_PARAMETER_ORDER)
    assert len(result.trials) == 1
    assert result.trials[0].trial_no == 1
    assert result.trials[0].parameter_values == {
        "candidate.min_score": "70",
        "candidate.top_n": 10,
        "construction.max_positions": 10,
        "construction.max_single_position_weight": "0.1",
        "construction.min_cash_ratio": "0.02",
        "construction.max_new_positions_per_day": 3,
    }


def test_grid_is_numeric_sorted_deterministic_and_rightmost_changes_fastest(
    portfolio_config: PortfolioConfig,
) -> None:
    first = expand_grid(
        base_portfolio=portfolio_config,
        grid={
            "construction.max_new_positions_per_day": [3, 2],
            "candidate.min_score": [Decimal("75.0"), Decimal("65")],
        },
        max_trials=128,
        max_values_per_parameter=20,
    )
    second = expand_grid(
        base_portfolio=portfolio_config,
        grid={
            "candidate.min_score": [Decimal("65.00"), Decimal("75")],
            "construction.max_new_positions_per_day": [2, 3],
        },
        max_trials=128,
        max_values_per_parameter=20,
    )

    assert first.parameter_space["candidate.min_score"] == ["65", "75"]
    assert [
        (
            trial.parameter_values["candidate.min_score"],
            trial.parameter_values["construction.max_new_positions_per_day"],
        )
        for trial in first.trials
    ] == [("65", 2), ("65", 3), ("75", 2), ("75", 3)]
    assert first == second


@pytest.mark.parametrize(
    "values",
    [[Decimal("0.1"), Decimal("0.10")], []],
)
def test_duplicate_or_empty_value_list_is_rejected(
    portfolio_config: PortfolioConfig, values: list[Decimal]
) -> None:
    with pytest.raises(ExperimentGridError) as caught:
        expand_grid(
            base_portfolio=portfolio_config,
            grid={"construction.max_single_position_weight": values},
            max_trials=128,
            max_values_per_parameter=20,
        )

    assert caught.value.code == "EXPERIMENT_GRID_INVALID"


def test_per_parameter_and_total_trial_limits_fail_closed(
    portfolio_config: PortfolioConfig,
) -> None:
    with pytest.raises(ExperimentGridError, match="maximum is 2") as per_parameter:
        expand_grid(
            base_portfolio=portfolio_config,
            grid={"candidate.top_n": [10, 11, 12]},
            max_trials=128,
            max_values_per_parameter=2,
        )
    assert per_parameter.value.code == "EXPERIMENT_GRID_INVALID"

    with pytest.raises(ExperimentGridError) as total:
        expand_grid(
            base_portfolio=portfolio_config,
            grid={
                "candidate.min_score": [60, 70],
                "candidate.top_n": [10, 11],
            },
            max_trials=3,
            max_values_per_parameter=20,
        )
    assert total.value.code == "EXPERIMENT_TRIAL_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    "grid",
    [
        {"candidate.top_n": [5], "construction.max_positions": [10]},
        {
            "construction.max_positions": [2],
            "construction.max_new_positions_per_day": [3],
        },
    ],
)
def test_cross_field_invalid_trial_rejects_whole_definition(
    portfolio_config: PortfolioConfig, grid: dict[str, list[int]]
) -> None:
    with pytest.raises(ExperimentGridError) as caught:
        expand_grid(
            base_portfolio=portfolio_config,
            grid=grid,
            max_trials=128,
            max_values_per_parameter=20,
        )

    assert caught.value.code == "EXPERIMENT_CONFIG_INVALID"


def test_unknown_parameter_is_rejected(portfolio_config: PortfolioConfig) -> None:
    with pytest.raises(ExperimentGridError) as caught:
        expand_grid(
            base_portfolio=portfolio_config,
            grid={"execution.slippage_bps": [1]},
            max_trials=128,
            max_values_per_parameter=20,
        )

    assert caught.value.code == "EXPERIMENT_GRID_INVALID"
