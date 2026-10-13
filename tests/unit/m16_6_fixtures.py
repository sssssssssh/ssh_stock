import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.core.config import get_settings
from app.services.agent.contracts.m14 import m14_contract_body
from app.services.calc_metadata import config_hash
from app.services.performance.analytics_bundle import AnalyticsArtifactBundle
from app.services.performance.period_identity import period_identity_hash
from app.services.performance.risk_identity import risk_source_hash


def synthetic_m15():
    from app.domain.experiment import EXPERIMENT_PARAMETER_ORDER
    from app.domain.walk_forward.windows import date_set_hash
    from app.services.agent.contracts.canonical import contract_hash, contract_json
    from app.services.agent.contracts.m15 import BASE_IDENTITY_FIELDS
    from app.services.agent.contracts.semantics import endpoint_metrics
    from app.services.experiment_evaluation.identity import experiment_parameter_hash, stable_hash
    from app.services.walk_forward.source import _bundle_identity

    settings = get_settings()
    train = synthetic_m14(annualized="0.2")
    oos = synthetic_m14(annualized="0.08", dates=("2026-01-06", "2026-01-07"))
    endpoints = {"TRAIN": train, "OOS": oos}
    study_id, validation_id, trial_id, experiment_id, evaluation_id = [
        str(uuid.uuid4()) for _ in range(5)
    ]
    anchor = {"evidence_id": uuid.uuid4().hex, "content_hash": "8" * 64, "report_id": validation_id}
    for endpoint in endpoints.values():
        endpoint["record"] = contract_json({"window_metrics": endpoint_metrics(endpoint)})
        endpoint["evidence"] = [anchor]
    snapshot = settings.portfolio_config.model_dump(mode="json")
    parameters = {
        path: snapshot[path.split(".")[0]][path.split(".")[1]]
        for path in EXPERIMENT_PARAMETER_ORDER
    }
    parameter_hash = experiment_parameter_hash(parameters)
    run = train["bundle_rows"]["run"]
    base = {key: run[key.removeprefix("base_")] for key in BASE_IDENTITY_FIELDS}
    study = {
        **base,
        "id": study_id,
        "walk_forward_version": "walk_forward_v1",
        "definition_hash": "a" * 64,
        "calendar_hash": "b" * 64,
        "parameter_space_hash": "c" * 64,
        "train_policy_hash": "d" * 64,
        "initial_cash": run["initial_cash"],
        "benchmark_code": run["benchmark_code"],
        "base_snapshot_hashes": {
            "execution": run["execution_config_hash"],
            "accounting": run["accounting_config_hash"],
        },
    }
    validation_policy = settings.walk_forward_config.validation_policy.model_dump(mode="json")
    validation = {
        "id": validation_id,
        "study_id": study_id,
        "status": "SUCCESS",
        "walk_forward_version": "walk_forward_v1",
        "policy_identity_version": "policy_v1",
        "validation_policy_snapshot": validation_policy,
        "validation_policy_hash": stable_hash(validation_policy),
        "source_hash": "e" * 64,
    }
    window = {
        "study_id": study_id,
        "window_no": 1,
        "train_experiment_id": experiment_id,
        "train_evaluation_id": evaluation_id,
        "selected_trial_id": trial_id,
        "selected_parameter_hash": parameter_hash,
        "selected_parameter_values": parameters,
        "selected_portfolio_config_hash": run["portfolio_config_hash"],
        "oos_run_id": oos["selected"]["run_id"],
    }
    for prefix, endpoint in (("train", train), ("test", oos)):
        dates = endpoint["comparison_contract"]["trade_dates"]
        window.update(
            {
                prefix + "_start_date": dates[0],
                prefix + "_end_date": dates[-1],
                prefix + "_trade_days": len(dates),
                prefix + "_trade_dates": dates,
                prefix + "_date_hash": date_set_hash(
                    tuple(date.fromisoformat(value) for value in dates)
                ),
            }
        )
    trial = {
        "id": trial_id,
        "experiment_id": experiment_id,
        "run_id": train["selected"]["run_id"],
        "parameter_hash": parameter_hash,
        "parameter_values": parameters,
        "portfolio_config_hash": run["portfolio_config_hash"],
    }
    evaluation = {
        "id": evaluation_id,
        "experiment_id": experiment_id,
        "status": "SUCCESS",
        "policy_hash": study["train_policy_hash"],
        "source_hash": "f" * 64,
        "evaluation_version": "evaluation_v1",
        "selected_trial_id": trial_id,
        "selected_run_id": trial["run_id"],
    }
    experiment = {
        **base,
        "id": experiment_id,
        "definition_hash": "a" * 64,
        "parameter_space_hash": study["parameter_space_hash"],
        "initial_cash": run["initial_cash"],
        "benchmark_code": run["benchmark_code"],
        "start_date": window["train_start_date"],
        "end_date": window["train_end_date"],
        "base_snapshot_hashes": study["base_snapshot_hashes"],
    }
    trial_eval = {
        "evaluation_id": evaluation_id,
        "experiment_id": experiment_id,
        "trial_id": trial_id,
        "run_id": trial["run_id"],
        "parameter_hash": parameter_hash,
        "status": "EVALUATED",
        "feasible": True,
        "shortlisted": True,
        "selection_rank": 1,
        **{key: value for key, value in train["selected"].items() if key != "run_id"},
    }
    identity = {
        "schema_version": "walk_forward_window_validation_identity_v1",
        "window_no": 1,
        "train": {
            "selection": {
                "trial_id": trial_id,
                "run_id": trial["run_id"],
                "parameter_hash": parameter_hash,
                "portfolio_config_hash": trial["portfolio_config_hash"],
            },
            "evaluation": {key: evaluation[key] for key in ("id", "policy_hash", "source_hash")},
            "experiment": {key: experiment[key] for key in ("id", "definition_hash")},
        },
        "oos": {
            "run": {
                key: oos["bundle_rows"]["run"][key]
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
        },
    }
    for role, prefix in (("TRAIN", "train"), ("OOS", "oos")):
        endpoint = endpoints[role]
        identity[prefix]["m14"] = _bundle_identity(
            **{
                key: SimpleNamespace(**endpoint["bundle_rows"][key])
                for key in ("performance", "risk", "trade", "period")
            }
        )
        identity[prefix]["dates"] = {
            "hash": window["train_date_hash" if role == "TRAIN" else "test_date_hash"],
            "count": 2,
        }
    record = {
        "study_id": study_id,
        "validation_id": validation_id,
        "window_no": 1,
        "train_metrics": endpoint_metrics(train),
        "oos_metrics": endpoint_metrics(oos),
        "degradation": {
            "return": Decimal("0.12"),
            "sharpe": Decimal("0"),
            "drawdown": Decimal("0"),
            "turnover": Decimal("0"),
        },
    }
    body = contract_json(
        {
            "status": "COMPLETE",
            "reason_codes": [],
            "study": study,
            "validation": validation,
            "window": window,
            "trial": trial,
            "evaluation": evaluation,
            "experiment": experiment,
            "trial_evaluation": trial_eval,
            "selection_snapshot": snapshot,
            "selection_snapshot_hash": config_hash(snapshot),
            "record": record,
            "identity_snapshot": identity,
            "evidence": [anchor],
            "m14_contract_refs": [
                {
                    "role": role,
                    "subject_id": endpoint["selected"]["run_id"],
                    "contract_hash": contract_hash(endpoint),
                }
                for role, endpoint in endpoints.items()
            ],
        }
    )
    return body, endpoints


def synthetic_m14(*, annualized="0.1", dates=("2026-01-02", "2026-01-05"), execution=None):
    settings = get_settings()
    execution = execution or settings.execution_config.model_dump(mode="json")
    accounting = settings.accounting_config.model_dump(mode="json")
    run = SimpleNamespace(
        id=uuid.uuid4(),
        status="SUCCESS",
        account_mode="BACKTEST",
        start_date=date.fromisoformat(dates[0]),
        end_date=date.fromisoformat(dates[-1]),
        initial_cash=Decimal("1000000"),
        benchmark_code="000300.SH",
        algo_version="v1.1",
        source_strategy_config_hash="a" * 64,
        opportunity_calc_version="opportunity_v1",
        opportunity_config_hash="b" * 64,
        portfolio_version="portfolio_v3",
        portfolio_config_hash=config_hash(settings.portfolio_config.model_dump(mode="json")),
        execution_version="execution_v3",
        execution_config_hash=config_hash(execution),
        accounting_version="accounting_v3",
        accounting_config_hash=config_hash(accounting),
        backtest_engine_version="backtest_v7",
        config_snapshot={"execution": execution, "accounting": accounting},
    )
    common = dict(
        run_id=run.id,
        status="SUCCESS",
        start_date=run.start_date,
        end_date=run.end_date,
        trade_days=len(dates),
    )
    performance = SimpleNamespace(
        id=uuid.uuid4(),
        **common,
        performance_version="performance_v1",
        performance_config_hash="1" * 64,
        source_hash="2" * 64,
        final_nav=Decimal("1.1"),
        cumulative_return=Decimal("0.1"),
        annualized_return=Decimal(annualized),
        max_drawdown=Decimal("-0.05"),
    )
    risk = SimpleNamespace(
        id=uuid.uuid4(),
        **common,
        performance_id=performance.id,
        risk_version="risk_v1",
        risk_config_hash="3" * 64,
        benchmark_code="000300.SH",
        benchmark_source_hash="4" * 64,
        benchmark_cumulative_return=Decimal("0.02"),
        excess_cumulative_return=Decimal("0.08"),
        sharpe_ratio=Decimal("1.2"),
        sortino_ratio=None,
        calmar_ratio=Decimal("2"),
    )
    risk.risk_source_hash = risk_source_hash(
        performance_id=performance.id,
        performance_version=performance.performance_version,
        performance_config_hash=performance.performance_config_hash,
        performance_source_hash=performance.source_hash,
        risk_version=risk.risk_version,
        risk_config_hash=risk.risk_config_hash,
        benchmark_code=risk.benchmark_code,
        benchmark_hash=risk.benchmark_source_hash,
    )
    trade = SimpleNamespace(
        id=uuid.uuid4(),
        **common,
        performance_id=performance.id,
        trade_version="trade_v1",
        trade_config_hash="5" * 64,
        trade_source_hash="6" * 64,
        total_turnover=Decimal("2"),
        annualized_turnover=Decimal("3"),
        total_execution_cost=Decimal("50"),
        closed_episode_count=1,
        open_episode_count=0,
        win_rate=Decimal("1"),
        profit_factor=None,
    )
    period = SimpleNamespace(
        id=uuid.uuid4(),
        **common,
        performance_id=performance.id,
        risk_id=risk.id,
        trade_id=trade.id,
        period_version="period_v1",
        period_config_hash="7" * 64,
        month_count=1,
        year_count=1,
    )
    period.period_source_hash = period_identity_hash(
        run_id=run.id,
        performance_id=performance.id,
        performance_version=performance.performance_version,
        performance_config_hash=performance.performance_config_hash,
        performance_source_hash=performance.source_hash,
        risk_id=risk.id,
        risk_version=risk.risk_version,
        risk_config_hash=risk.risk_config_hash,
        risk_source_hash=risk.risk_source_hash,
        benchmark_source_hash=risk.benchmark_source_hash,
        trade_id=trade.id,
        trade_version=trade.trade_version,
        trade_config_hash=trade.trade_config_hash,
        trade_source_hash=trade.trade_source_hash,
        period_version=period.period_version,
        period_config_hash=period.period_config_hash,
    )
    record = {
        "report_ids": {
            name + "_id": row.id
            for name, row in (
                ("performance", performance),
                ("risk", risk),
                ("trade", trade),
                ("period", period),
            )
        }
    }
    for name, row, keys in (
        (
            "performance",
            performance,
            (
                "start_date",
                "end_date",
                "trade_days",
                "final_nav",
                "cumulative_return",
                "annualized_return",
                "max_drawdown",
            ),
        ),
        (
            "risk",
            risk,
            (
                "benchmark_code",
                "benchmark_cumulative_return",
                "excess_cumulative_return",
                "sharpe_ratio",
                "sortino_ratio",
                "calmar_ratio",
            ),
        ),
        (
            "trade",
            trade,
            (
                "total_turnover",
                "total_execution_cost",
                "closed_episode_count",
                "open_episode_count",
                "win_rate",
                "profit_factor",
            ),
        ),
        ("period", period, ("month_count", "year_count")),
    ):
        record[name] = {key: getattr(row, key) for key in keys}
    evidence = [
        {
            "evidence_id": uuid.uuid4().hex,
            "content_hash": "8" * 64,
            "report_id": str(performance.id),
        }
    ]
    return m14_contract_body(
        AnalyticsArtifactBundle(run, performance, risk, trade, period),
        dates,
        evidence=evidence,
        record=record,
        limitations=["SYNTHETIC_TEST_ONLY"],
    )
