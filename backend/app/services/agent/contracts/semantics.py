import re
from dataclasses import asdict, fields
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from pydantic import TypeAdapter

from app.core.accounting_config import AccountingConfig
from app.core.execution_config import ExecutionConfig
from app.domain.experiment import EXPERIMENT_PARAMETER_ORDER
from app.domain.walk_forward.metrics import window_degradation
from app.domain.walk_forward.windows import date_set_hash
from app.services.agent.archive.projectors import check_safe
from app.services.agent.chat.comparison_contract import (
    ComparisonContract,
    build_comparison_contract,
)
from app.services.agent.contracts.canonical import contract_hash, contract_json
from app.services.agent.contracts.m14 import REPORT_FIELDS, RUN_FIELDS
from app.services.agent.contracts.m15 import BASE_IDENTITY_FIELDS
from app.services.calc_metadata import config_hash
from app.services.experiment_evaluation.identity import experiment_parameter_hash, stable_hash
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundle,
    validate_exact_analytics_bundle,
)
from app.services.walk_forward.source import _bundle_identity


class ContractSemanticError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code="CONTRACT_SEMANTIC_MISMATCH"):
    if not condition:
        raise ContractSemanticError(code)


def number(value):
    require(not isinstance(value, (bool, float)) and value is not None, "CONTRACT_NUMERIC_INVALID")
    result = Decimal(str(value))
    require(
        result.is_finite()
        and len(result.as_tuple().digits) <= 128
        and abs(result.as_tuple().exponent) <= 128,
        "CONTRACT_NUMERIC_INVALID",
    )
    return result


def _keys(value, expected):
    require(isinstance(value, dict) and set(value) == set(expected), "CONTRACT_SCHEMA_MISMATCH")


def _uuid(value):
    result = UUID(str(value))
    require(str(result) == value, "CONTRACT_IDENTIFIER_INVALID")
    return result


def _dates(values, start, end, count):
    require(isinstance(values, (list, tuple)) and bool(values), "CONTRACT_DATES_MISSING")
    parsed = tuple(date.fromisoformat(value) for value in values)
    require(
        [value.isoformat() for value in parsed] == list(values)
        and tuple(sorted(set(parsed))) == parsed
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count == len(parsed)
        and values[0] == start
        and values[-1] == end,
        "CONTRACT_DATES_MISMATCH",
    )
    return parsed


def _decode(values):
    decoded = {}
    for key, value in values.items():
        if key == "id" or key.endswith("_id"):
            decoded[key] = _uuid(value)
        elif key in {"start_date", "end_date"}:
            decoded[key] = date.fromisoformat(value)
        elif key in {
            "initial_cash",
            "max_drawdown",
            "annualized_return",
            "cumulative_return",
            "final_nav",
            "sharpe_ratio",
            "annualized_turnover",
        }:
            decoded[key] = number(value) if value is not None else None
        else:
            decoded[key] = value
    return SimpleNamespace(**decoded)


def _hash_fields(values):
    for key, value in values.items():
        if key.endswith("_hash"):
            require(
                isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
                "CONTRACT_SOURCE_HASH_INVALID",
            )


def verify_m14(body):
    check_safe(body)
    _keys(
        body,
        (
            "selected",
            "evidence",
            "status",
            "comparison_contract",
            "trade_dates_hash",
            "bundle_rows",
            "execution_snapshot",
            "accounting_snapshot",
            "record",
            "limitations",
        ),
    )
    require(body["status"] == "COMPLETE")
    _keys(body["selected"], ("run_id", "performance_id", "risk_id", "trade_id", "period_id"))
    _keys(body["comparison_contract"], [field.name for field in fields(ComparisonContract)])
    comparison = TypeAdapter(ComparisonContract).validate_python(body["comparison_contract"])
    _hash_fields(body["comparison_contract"])
    require(
        comparison.currency == "CNY" and comparison.frequency == "DAILY",
        "CONTRACT_CONVENTION_UNSUPPORTED",
    )
    parsed_dates = _dates(
        comparison.trade_dates, comparison.start_date, comparison.end_date, comparison.trade_days
    )
    require(body["trade_dates_hash"] == contract_hash(comparison.trade_dates))
    _keys(body["bundle_rows"], ("run", *REPORT_FIELDS))
    _keys(body["bundle_rows"]["run"], RUN_FIELDS)
    rows = {"run": _decode(body["bundle_rows"]["run"])}
    for name, extra in REPORT_FIELDS.items():
        values = body["bundle_rows"][name]
        _keys(values, ("id", "run_id", "status", "start_date", "end_date", "trade_days", *extra))
        _hash_fields(values)
        rows[name] = _decode(values)
    _hash_fields(body["bundle_rows"]["run"])
    require(all(str(row.id) == body["selected"][name + "_id"] for name, row in rows.items()))
    require(rows["run"].initial_cash > 0)
    require(rows["performance"].max_drawdown <= 0, "CONTRACT_DRAWDOWN_SIGN_INVALID")
    require((rows["run"].start_date, rows["run"].end_date) == (parsed_dates[0], parsed_dates[-1]))
    ExecutionConfig.model_validate(body["execution_snapshot"])
    AccountingConfig.model_validate(body["accounting_snapshot"])
    for name in ("execution", "accounting"):
        require(
            config_hash(body[name + "_snapshot"]) == getattr(rows["run"], name + "_config_hash"),
            "CONTRACT_ASSUMPTION_HASH_MISMATCH",
        )
    rows["run"].config_snapshot = {
        "execution": body["execution_snapshot"],
        "accounting": body["accounting_snapshot"],
    }
    bundle = AnalyticsArtifactBundle(**rows)
    validate_exact_analytics_bundle(bundle, require_period=True)
    rebuilt = build_comparison_contract(bundle, tuple(value.isoformat() for value in parsed_dates))
    require(
        contract_hash(asdict(rebuilt)) == contract_hash(body["comparison_contract"]),
        "CONTRACT_COMPARISON_PROJECTION_MISMATCH",
    )
    require(
        (
            rebuilt.performance_version,
            rebuilt.risk_version,
            rebuilt.trade_version,
            rebuilt.period_version,
        )
        == ("performance_v1", "risk_v1", "trade_v1", "period_v1"),
        "CONTRACT_MODEL_VERSION_UNSUPPORTED",
    )
    if "window_metrics" in body["record"]:
        expected = {"window_metrics": endpoint_metrics(body)}
    else:
        expected = {
            "report_ids": {key: value for key, value in body["selected"].items() if key != "run_id"}
        }
        for name, names in {
            "performance": (
                "start_date",
                "end_date",
                "trade_days",
                "final_nav",
                "cumulative_return",
                "annualized_return",
                "max_drawdown",
            ),
            "risk": (
                "benchmark_code",
                "benchmark_cumulative_return",
                "excess_cumulative_return",
                "sharpe_ratio",
                "sortino_ratio",
                "calmar_ratio",
            ),
            "trade": (
                "total_turnover",
                "total_execution_cost",
                "closed_episode_count",
                "open_episode_count",
                "win_rate",
                "profit_factor",
            ),
            "period": ("month_count", "year_count"),
        }.items():
            expected[name] = {key: body["bundle_rows"][name][key] for key in names}
    require(
        contract_hash(expected) == contract_hash(body["record"]), "CONTRACT_FACT_ANCHOR_MISMATCH"
    )
    return comparison


def endpoint_metrics(body):
    rows = body["bundle_rows"]
    drawdown = number(rows["performance"]["max_drawdown"])
    require(drawdown <= 0, "CONTRACT_DRAWDOWN_SIGN_INVALID")
    return {
        "annualized_return": number(rows["performance"]["annualized_return"]),
        "max_drawdown_abs": -drawdown,
        "sharpe_ratio": number(rows["risk"]["sharpe_ratio"])
        if rows["risk"]["sharpe_ratio"] is not None
        else None,
        "annualized_turnover": number(rows["trade"]["annualized_turnover"]),
    }


def verify_m15(body, endpoints):
    check_safe(body)
    _keys(
        body,
        (
            "status",
            "reason_codes",
            "study",
            "validation",
            "window",
            "trial",
            "evaluation",
            "experiment",
            "trial_evaluation",
            "selection_snapshot_hash",
            "selection_snapshot",
            "m14_contract_refs",
            "identity_snapshot",
            "record",
            "evidence",
        ),
    )
    require(body["status"] == "COMPLETE" and set(endpoints) == {"TRAIN", "OOS"})
    require(
        len(body["m14_contract_refs"]) == 2
        and {ref["role"] for ref in body["m14_contract_refs"]} == {"TRAIN", "OOS"}
    )
    for ref in body["m14_contract_refs"]:
        require(
            ref["contract_hash"] == contract_hash(endpoints[ref["role"]])
            and ref["subject_id"] == endpoints[ref["role"]]["selected"]["run_id"]
        )
    study, validation, window = (body[key] for key in ("study", "validation", "window"))
    trial, evaluation, experiment, trial_eval = (
        body[key] for key in ("trial", "evaluation", "experiment", "trial_evaluation")
    )
    require(study["id"] == validation["study_id"] == window["study_id"])
    require(
        validation["status"] == "SUCCESS"
        and validation["policy_identity_version"] == "policy_v1"
        and validation["walk_forward_version"]
        == study["walk_forward_version"]
        == "walk_forward_v1",
        "CONTRACT_VALIDATION_VERSION_UNSUPPORTED",
    )
    for projection in (study, validation, window, trial, evaluation, experiment, trial_eval):
        _hash_fields(projection)
    require(
        stable_hash(validation["validation_policy_snapshot"])
        == validation["validation_policy_hash"]
    )
    require(
        all(
            experiment[key] == study[key]
            for key in (
                *BASE_IDENTITY_FIELDS,
                "parameter_space_hash",
                "initial_cash",
                "benchmark_code",
                "base_snapshot_hashes",
            )
        )
    )
    require(
        window["train_experiment_id"]
        == trial["experiment_id"]
        == evaluation["experiment_id"]
        == experiment["id"]
        == trial_eval["experiment_id"]
    )
    require(window["train_evaluation_id"] == evaluation["id"] == trial_eval["evaluation_id"])
    require(
        window["selected_trial_id"]
        == trial["id"]
        == evaluation["selected_trial_id"]
        == trial_eval["trial_id"]
    )
    require(trial["run_id"] == evaluation["selected_run_id"] == trial_eval["run_id"])
    require(
        evaluation["status"] == "SUCCESS"
        and trial_eval["status"] == "EVALUATED"
        and trial_eval["feasible"] is True
        and trial_eval["shortlisted"] is True
        and trial_eval["selection_rank"] == 1
        and evaluation["policy_hash"] == study["train_policy_hash"],
        "CONTRACT_SELECTION_MISMATCH",
    )
    require(
        experiment_parameter_hash(trial["parameter_values"])
        == trial["parameter_hash"]
        == window["selected_parameter_hash"]
        == trial_eval["parameter_hash"]
    )
    require(trial["parameter_values"] == window["selected_parameter_values"])
    require(set(trial["parameter_values"]) == set(EXPERIMENT_PARAMETER_ORDER))
    for path, value in trial["parameter_values"].items():
        section, key = path.split(".")
        require(number(body["selection_snapshot"][section][key]) == number(value))
    require(
        config_hash(body["selection_snapshot"])
        == body["selection_snapshot_hash"]
        == trial["portfolio_config_hash"]
        == window["selected_portfolio_config_hash"]
    )
    require(
        experiment["start_date"] == window["train_start_date"]
        and experiment["end_date"] == window["train_end_date"]
    )
    date_sets = {}
    for role, prefix in (("TRAIN", "train"), ("OOS", "test")):
        endpoint = endpoints[role]
        c = endpoint["comparison_contract"]
        dates = _dates(
            window[prefix + "_trade_dates"],
            window[prefix + "_start_date"],
            window[prefix + "_end_date"],
            window[prefix + "_trade_days"],
        )
        date_sets[role] = dates
        require(
            list(c["trade_dates"]) == window[prefix + "_trade_dates"]
            and window[prefix + "_date_hash"] == date_set_hash(dates),
            "CONTRACT_WINDOW_DATES_MISMATCH",
        )
        run = endpoint["bundle_rows"]["run"]
        require(run["id"] == (trial["run_id"] if role == "TRAIN" else window["oos_run_id"]))
        require(
            run["initial_cash"] == study["initial_cash"]
            and run["benchmark_code"] == study["benchmark_code"]
            and run["portfolio_config_hash"] == trial["portfolio_config_hash"]
        )
        for key in BASE_IDENTITY_FIELDS:
            if key == "base_portfolio_config_hash":
                continue
            require(
                run[key.removeprefix("base_")] == study[key], "CONTRACT_WINDOW_ASSUMPTIONS_MISMATCH"
            )
        require(
            run["start_date"] == window[prefix + "_start_date"]
            and run["end_date"] == window[prefix + "_end_date"]
        )
        for kind in ("execution", "accounting"):
            require(
                config_hash(endpoint[kind + "_snapshot"]) == study["base_snapshot_hashes"][kind]
            )
        if role == "TRAIN":
            require(
                all(
                    endpoint["selected"][key + "_id"] == trial_eval[key + "_id"]
                    for key in ("performance", "risk", "trade", "period")
                )
            )
        identity = body["identity_snapshot"]["train" if role == "TRAIN" else "oos"]
        rows = {key: _decode(endpoint["bundle_rows"][key]) for key in REPORT_FIELDS}
        require(identity["m14"] == _bundle_identity(**rows))
        require(identity["dates"] == {"hash": date_set_hash(dates), "count": len(dates)})
    require(date_sets["TRAIN"][-1] < date_sets["OOS"][0], "CONTRACT_SAMPLE_OVERLAP")
    identity = body["identity_snapshot"]
    require(
        identity["schema_version"] == "walk_forward_window_validation_identity_v1"
        and identity["window_no"] == window["window_no"]
    )
    require(
        identity["train"]["selection"]
        == {
            "trial_id": trial["id"],
            "run_id": trial["run_id"],
            "parameter_hash": trial["parameter_hash"],
            "portfolio_config_hash": trial["portfolio_config_hash"],
        }
    )
    require(
        identity["train"]["evaluation"]
        == {
            "id": evaluation["id"],
            "policy_hash": evaluation["policy_hash"],
            "source_hash": evaluation["source_hash"],
        }
    )
    require(
        identity["train"]["experiment"]
        == {
            "id": experiment["id"],
            "definition_hash": experiment["definition_hash"],
        }
    )
    oos_run = endpoints["OOS"]["bundle_rows"]["run"]
    require(
        identity["oos"]["run"]
        == {
            key: oos_run[key]
            for key in (
                "id",
                "start_date",
                "end_date",
                "portfolio_config_hash",
                "source_strategy_config_hash",
                "opportunity_config_hash",
                "execution_config_hash",
                "accounting_config_hash",
            )
        }
    )
    metrics = {}
    for role, prefix in (("TRAIN", "train"), ("OOS", "oos")):
        values = endpoint_metrics(endpoints[role])
        for key, value in values.items():
            require(
                contract_json(body["record"][prefix + "_metrics"][key]) == contract_json(value),
                "CONTRACT_WINDOW_METRIC_MISMATCH",
            )
            metrics[prefix + "_" + key] = value
    degradation = window_degradation(SimpleNamespace(**metrics))
    for output, key in (
        ("return", "return_degradation"),
        ("sharpe", "sharpe_degradation"),
        ("drawdown", "drawdown_worsening"),
        ("turnover", "turnover_change"),
    ):
        require(
            contract_json(body["record"]["degradation"][output]) == contract_json(degradation[key]),
            "CONTRACT_DEGRADATION_MISMATCH",
        )
    require(
        str(body["record"]["study_id"]) == study["id"]
        and str(body["record"]["validation_id"]) == validation["id"]
        and body["record"]["window_no"] == window["window_no"]
    )
    return degradation
