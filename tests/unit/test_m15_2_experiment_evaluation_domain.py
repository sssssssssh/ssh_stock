import inspect
import uuid
from dataclasses import replace
from decimal import Decimal, localcontext

import pytest
from app.core.experiment_evaluation_config import (
    EvaluationPolicyConfig,
    ExperimentEvaluationConfig,
)
from app.domain.experiment_evaluation import (
    EvaluatedTrial,
    EvaluationMetricSnapshot,
    EvaluationPolicy,
    EvaluationTrialInput,
    assign_pareto_fronts,
    calculate_sensitivity,
    constraints,
    evaluate_constraints,
    metrics,
    monthly_robustness,
    pareto,
    rank_trials,
    ranking,
    sensitivity,
)
from app.services.experiment_evaluation.identity import effective_policy

PARAMETERS = {
    "candidate.min_score": "70",
    "candidate.top_n": 20,
    "construction.max_positions": 5,
    "construction.max_single_position_weight": "0.2",
    "construction.min_cash_ratio": "0.1",
    "construction.max_new_positions_per_day": 2,
}


def _policy(**overrides) -> EvaluationPolicy:
    values = {
        "primary_objective": "annualized_return",
        "shortlist_size": 2,
        "constraints": {},
        "pareto_metrics": ("annualized_return", "max_drawdown_abs"),
        "tie_breakers": ("sharpe_ratio",),
    }
    values.update(overrides)
    return EvaluationPolicy(**values)


def _metrics(**overrides) -> EvaluationMetricSnapshot:
    values = {
        "trade_days": Decimal("20"),
        "cumulative_return": Decimal("0.12"),
        "annualized_return": Decimal("0.20"),
        "max_drawdown_abs": Decimal("0.10"),
        "strategy_annualized_volatility": Decimal("0.15"),
        "excess_cumulative_return": Decimal("0.03"),
        "sharpe_ratio": Decimal("1.2"),
        "sortino_ratio": Decimal("1.3"),
        "calmar_ratio": Decimal("2"),
        "information_ratio": Decimal("0.5"),
        "alpha_annualized": Decimal("0.02"),
        "annualized_turnover": Decimal("4"),
        "total_cost_to_initial_capital": Decimal("0.01"),
        "closed_episode_count": Decimal("8"),
        "win_rate": Decimal("0.6"),
        "profit_factor": Decimal("1.5"),
        "payoff_ratio": Decimal("1.2"),
        "closed_realized_pnl": Decimal("100"),
        "positive_month_rate": Decimal("0.5"),
        "worst_month_return": Decimal("-0.1"),
        "monthly_return_volatility": Decimal("0.03"),
    }
    values.update(overrides)
    return EvaluationMetricSnapshot(**values)


def _trial(number: int, metrics_snapshot: EvaluationMetricSnapshot) -> EvaluatedTrial:
    source = EvaluationTrialInput(
        trial_id=uuid.UUID(int=number),
        trial_no=number,
        parameter_hash=str(number) * 64,
        parameter_values=dict(PARAMETERS),
        run_id=uuid.UUID(int=100 + number),
        run_status="SUCCESS",
        metrics=metrics_snapshot,
    )
    return EvaluatedTrial(
        source=source,
        status="EVALUATED",
        exclusion_reason=None,
        feasible=True,
        constraint_violations=(),
        primary_objective_value=metrics_snapshot.annualized_return,
    )


def test_monthly_robustness_uses_decimal_sample_standard_deviation() -> None:
    positive, worst, volatility, warnings = monthly_robustness(
        (Decimal("0.1"), Decimal("0"), Decimal("-0.1")),
        minimum_observations=2,
    )
    with localcontext() as context:
        context.prec = 60
        assert positive == Decimal(1) / Decimal(3)
    assert worst == Decimal("-0.1")
    assert volatility == Decimal("0.1")
    assert warnings == ()
    assert monthly_robustness(
        (Decimal("0.1"),), minimum_observations=2
    )[2:] == (None, ("INSUFFICIENT_MONTH_OBSERVATIONS",))


@pytest.mark.parametrize(
    ("constraint", "metric", "threshold", "failing", "code"),
    [
        ("min_trade_days", "trade_days", 20, "19", "MIN_TRADE_DAYS"),
        (
            "min_annualized_return",
            "annualized_return",
            Decimal("0.2"),
            "0.19",
            "MIN_ANNUALIZED_RETURN",
        ),
        (
            "max_drawdown_abs",
            "max_drawdown_abs",
            Decimal("0.1"),
            "0.11",
            "MAX_DRAWDOWN_ABS",
        ),
        ("min_sharpe_ratio", "sharpe_ratio", Decimal("1.2"), "1.1", "MIN_SHARPE_RATIO"),
        ("min_calmar_ratio", "calmar_ratio", Decimal("2"), "1.9", "MIN_CALMAR_RATIO"),
        (
            "max_annualized_turnover",
            "annualized_turnover",
            Decimal("4"),
            "4.1",
            "MAX_ANNUALIZED_TURNOVER",
        ),
        (
            "max_total_cost_to_initial_capital",
            "total_cost_to_initial_capital",
            Decimal("0.01"),
            "0.02",
            "MAX_TOTAL_COST_TO_INITIAL_CAPITAL",
        ),
        (
            "min_closed_episode_count",
            "closed_episode_count",
            8,
            "7",
            "MIN_CLOSED_EPISODE_COUNT",
        ),
        ("min_win_rate", "win_rate", Decimal("0.6"), "0.59", "MIN_WIN_RATE"),
        (
            "min_profit_factor",
            "profit_factor",
            Decimal("1.5"),
            "1.4",
            "MIN_PROFIT_FACTOR",
        ),
    ],
)
def test_all_constraint_boundaries_are_inclusive_and_fail_in_direction(
    constraint, metric, threshold, failing, code
) -> None:
    policy = _policy(constraints={constraint: threshold})
    assert evaluate_constraints(_metrics(), policy).feasible
    result = evaluate_constraints(_metrics(**{metric: Decimal(failing)}), policy)
    assert not result.feasible
    assert result.violations == (code,)


def test_enabled_null_constraint_and_primary_fail_closed_with_stable_codes() -> None:
    policy = _policy(
        constraints={"min_sharpe_ratio": Decimal("1")},
        pareto_metrics=("annualized_return", "profit_factor"),
    )
    result = evaluate_constraints(
        _metrics(annualized_return=None, sharpe_ratio=None, profit_factor=None), policy
    )
    assert result.violations == (
        "MISSING_METRIC:annualized_return",
        "MISSING_METRIC:profit_factor",
        "MISSING_METRIC:sharpe_ratio",
        "MISSING_PRIMARY_OBJECTIVE",
    )


def test_pareto_strict_dominance_equal_points_and_order_independence() -> None:
    policy = _policy()
    a = _trial(1, _metrics(annualized_return=Decimal("0.3"), max_drawdown_abs=Decimal("0.2")))
    b = _trial(2, _metrics(annualized_return=Decimal("0.2"), max_drawdown_abs=Decimal("0.1")))
    c = _trial(3, _metrics(annualized_return=Decimal("0.1"), max_drawdown_abs=Decimal("0.3")))
    d = _trial(4, _metrics(annualized_return=Decimal("0.3"), max_drawdown_abs=Decimal("0.2")))
    first = assign_pareto_fronts((a, b, c, d), policy)
    second = assign_pareto_fronts((d, c, b, a), policy)
    assert {row.source.trial_no: row.pareto_front for row in first} == {
        1: 1,
        2: 1,
        3: 2,
        4: 1,
    }
    assert {row.source.trial_no: row.pareto_front for row in first} == {
        row.source.trial_no: row.pareto_front for row in second
    }


def test_ranking_uses_front_primary_tie_breaker_and_trial_number() -> None:
    policy = _policy(shortlist_size=2)
    rows = (
        replace(_trial(4, _metrics(annualized_return=Decimal("0.2"))), pareto_front=1),
        replace(_trial(3, _metrics(annualized_return=Decimal("0.2"))), pareto_front=1),
        replace(_trial(2, _metrics(annualized_return=Decimal("0.5"))), pareto_front=2),
    )
    ranked = rank_trials(rows, policy)
    assert {
        row.source.trial_no: (row.selection_rank, row.shortlisted) for row in ranked
    } == {4: (2, True), 3: (1, True), 2: (3, False)}


def test_sensitivity_counts_all_trials_but_metrics_only_evaluated() -> None:
    policy = _policy()
    first = replace(_trial(1, _metrics(annualized_return=Decimal("0.1"))), pareto_front=1)
    second = replace(_trial(2, _metrics(annualized_return=Decimal("0.3"))), pareto_front=2)
    excluded = replace(
        _trial(3, _metrics(annualized_return=Decimal("9"))),
        status="EXCLUDED",
        exclusion_reason="RUN_FAILED",
        feasible=False,
        pareto_front=None,
        primary_objective_value=None,
    )
    rows = calculate_sensitivity((first, second, excluded), policy)
    sample = next(
        row
        for row in rows
        if row.parameter_name == "candidate.min_score" and row.parameter_value == "70"
    )
    assert (sample.trial_count, sample.evaluated_count, sample.feasible_count) == (3, 2, 2)
    assert sample.mean_primary_objective == Decimal("0.2")
    assert sample.median_primary_objective == Decimal("0.2")
    assert sample.pareto_front1_rate == Decimal("0.5")


def test_policy_canonical_hash_normalizes_decimal_and_rejects_invalid_catalog() -> None:
    config = ExperimentEvaluationConfig.model_validate(
        {
            "version": "experiment_eval_v1",
            "max_shortlist_size": 20,
            "max_pareto_metrics": 4,
            "minimum_month_observations": 2,
            "default_policy": {
                "primary_objective": "annualized_return",
                "shortlist_size": 10,
                "constraints": {},
                "pareto_metrics": ["annualized_return", "max_drawdown_abs"],
                "tie_breakers": ["sharpe_ratio"],
            },
        }
    )
    one = EvaluationPolicyConfig.model_validate(
        {
            **config.default_policy.model_dump(),
            "constraints": {"max_drawdown_abs": "0.2500"},
        }
    )
    two = EvaluationPolicyConfig.model_validate(
        {
            **config.default_policy.model_dump(),
            "constraints": {"max_drawdown_abs": "2.5E-1"},
        }
    )
    assert effective_policy(one, config)[2] == effective_policy(two, config)[2]
    invalid = one.model_copy(update={"primary_objective": "made_up"})
    with pytest.raises(ValueError, match="unsupported evaluation metrics"):
        effective_policy(invalid, config)


def test_domain_modules_have_no_infrastructure_or_float_dependencies() -> None:
    for module in (constraints, metrics, pareto, ranking, sensitivity):
        source = inspect.getsource(module)
        for forbidden in (
            "sqlalchemy",
            "Session",
            "FastAPI",
            "app.models",
            "JobRun",
            "numpy",
            "pandas",
        ):
            assert forbidden not in source
