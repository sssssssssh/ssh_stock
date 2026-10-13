from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.domain.agent.errors import identity_mismatch
from app.domain.agent.frozen_contracts import (
    M14_CONTRACT_VERSION,
    M15_AGGREGATE_CONTRACT_VERSION,
    M15_WINDOW_CONTRACT_VERSION,
    FrozenContractDraft,
)
from app.domain.walk_forward.metrics import window_degradation
from app.domain.walk_forward.windows import date_set_hash
from app.models.experiment import PortfolioExperiment, PortfolioExperimentTrial
from app.models.experiment_evaluation import (
    PortfolioExperimentEvaluationReport,
    PortfolioExperimentTrialEvaluation,
)
from app.models.performance import PortfolioPerformanceReport
from app.models.performance_period import PortfolioPerformancePeriodReport
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import (
    PortfolioWalkForwardStudy,
    PortfolioWalkForwardValidationReport,
    PortfolioWalkForwardWindow,
    PortfolioWalkForwardWindowValidation,
)
from app.services.agent.archive.projectors import check_safe
from app.services.agent.contracts.canonical import contract_hash, contract_json
from app.services.agent.contracts.capture import evidence_anchors, performance_dates
from app.services.agent.contracts.m14 import m14_contract_body
from app.services.calc_metadata import config_hash
from app.services.performance.analytics_bundle import AnalyticsArtifactBundle
from app.services.walk_forward.source import (
    WalkForwardSourceError,
    WalkForwardValidationSourceProvider,
    _bundle_identity,
)

BASE_IDENTITY_FIELDS = (
    "base_algo_version",
    "base_source_strategy_config_hash",
    "base_opportunity_calc_version",
    "base_opportunity_config_hash",
    "base_portfolio_version",
    "base_portfolio_config_hash",
    "base_execution_version",
    "base_execution_config_hash",
    "base_accounting_version",
    "base_accounting_config_hash",
    "base_backtest_engine_version",
)


def _project(row, fields):
    return contract_json({name: getattr(row, name) for name in fields})


def _rows(db, model, ids):
    return {row.id: row for row in db.scalars(select(model).where(model.id.in_(ids)))}


def capture_m15_contracts(db, result, *, tool_call_id, max_trade_dates):
    study_id = UUID(str(result.identity["study_id"]))
    validation_id = UUID(str(result.identity["validation_id"]))
    study = db.get(PortfolioWalkForwardStudy, study_id)
    report = db.get(PortfolioWalkForwardValidationReport, validation_id)
    if study is None or report is None or report.study_id != study.id or report.status != "SUCCESS":
        raise identity_mismatch("selected validation changed")
    validation = _project(
        report,
        (
            "id",
            "study_id",
            "status",
            "walk_forward_version",
            "policy_identity_version",
            "validation_policy_hash",
            "validation_policy_snapshot",
            "source_hash",
        ),
    )
    check_safe(validation)
    if result.tool_name == "walk_forward.summary":
        return [
            FrozenContractDraft(
                tool_call_id=tool_call_id,
                contract_kind="M15_STUDY_AGGREGATE",
                subject_id=f"{study_id}:{validation_id}",
                role="STUDY",
                schema_version=M15_AGGREGATE_CONTRACT_VERSION,
                verification_scope="STUDY_AGGREGATE_ONLY",
                contract_json={
                    "status": "GAP",
                    "reason_codes": ["STUDY_AGGREGATE_ONLY"],
                    "validation": validation,
                    "record": contract_json(result.records[0]),
                    "evidence": evidence_anchors(result),
                },
            )
        ]
    numbers = [int(record["window_no"]) for record in result.records]
    if len(set(numbers)) != len(numbers):
        raise identity_mismatch("duplicate window selection")
    links = {
        row.window_no: row
        for row in db.scalars(
            select(PortfolioWalkForwardWindowValidation).where(
                PortfolioWalkForwardWindowValidation.validation_id == validation_id,
                PortfolioWalkForwardWindowValidation.study_id == study_id,
                PortfolioWalkForwardWindowValidation.window_no.in_(numbers),
            )
        )
    }
    windows = {
        row.window_no: row
        for row in db.scalars(
            select(PortfolioWalkForwardWindow).where(
                PortfolioWalkForwardWindow.study_id == study_id,
                PortfolioWalkForwardWindow.window_no.in_(numbers),
            )
        )
    }
    if set(links) != set(numbers) or set(windows) != set(numbers):
        raise identity_mismatch("selected window disappeared")
    trials = _rows(db, PortfolioExperimentTrial, [row.selected_trial_id for row in links.values()])
    evaluations = _rows(
        db, PortfolioExperimentEvaluationReport, [row.train_evaluation_id for row in links.values()]
    )
    experiments = _rows(
        db, PortfolioExperiment, [row.train_experiment_id for row in links.values()]
    )
    trial_evaluations = {
        (row.evaluation_id, row.trial_id): row
        for row in db.scalars(
            select(PortfolioExperimentTrialEvaluation).where(
                PortfolioExperimentTrialEvaluation.evaluation_id.in_(evaluations),
                PortfolioExperimentTrialEvaluation.trial_id.in_(trials),
            )
        )
    }
    selected = {}
    for name, model in (
        ("run", PortfolioBacktestRun),
        ("performance", PortfolioPerformanceReport),
        ("risk", PortfolioPerformanceRiskReport),
        ("trade", PortfolioPerformanceTradeReport),
        ("period", PortfolioPerformancePeriodReport),
    ):
        ids = []
        for link in links.values():
            ids.extend(
                [
                    getattr(link, "selected_train_run_id" if name == "run" else f"train_{name}_id"),
                    getattr(link, f"oos_{name}_id"),
                ]
            )
        selected[name] = _rows(db, model, ids)
        if set(selected[name]) != set(ids):
            raise identity_mismatch("selected window analytics disappeared")
    dates = performance_dates(db, list(selected["performance"]), max_trade_dates)
    drafts = []
    study_projection = _project(
        study,
        (
            "id",
            "walk_forward_version",
            "definition_hash",
            "calendar_hash",
            "parameter_space_hash",
            "train_policy_hash",
            "initial_cash",
            "benchmark_code",
            *BASE_IDENTITY_FIELDS,
        ),
    )
    for record in result.records:
        number = int(record["window_no"])
        link, window = links[number], windows[number]
        try:
            trial = trials[link.selected_trial_id]
            evaluation = evaluations[link.train_evaluation_id]
            experiment = experiments[link.train_experiment_id]
            trial_evaluation = trial_evaluations[(evaluation.id, trial.id)]
            train_run = selected["run"][link.selected_train_run_id]
            oos_run = selected["run"][link.oos_run_id]
            WalkForwardValidationSourceProvider._validate_selection(
                study, window, experiment, evaluation, trial, train_run, trial_evaluation
            )
            WalkForwardValidationSourceProvider._validate_oos(
                study, window, experiment, trial, oos_run
            )
        except (KeyError, TypeError, ValueError, WalkForwardSourceError) as exc:
            raise identity_mismatch("selected window lineage changed") from exc
        if (
            window.train_evaluation_id != link.train_evaluation_id
            or window.selected_trial_id != link.selected_trial_id
            or window.oos_run_id != link.oos_run_id
            or link.selected_parameter_hash != trial.parameter_hash
            or link.selected_parameter_values != trial.parameter_values
            or str(record["study_id"]) != str(study_id)
            or str(record["validation_id"]) != str(validation_id)
            or any(
                getattr(window, f"oos_{name}_id") != getattr(link, f"oos_{name}_id")
                for name in ("performance", "risk", "trade", "period")
            )
            or any(
                getattr(trial_evaluation, name + "_id") != getattr(link, "train_" + name + "_id")
                for name in ("performance", "risk", "trade", "period")
            )
        ):
            raise identity_mismatch("selected window source identity changed")
        refs = [
            ref
            for ref in result.evidence
            if (
                ref.entity_id == f"{study_id}:window:{number}"
                and ref.source_record_id == f"{validation_id}:{number}"
                and ref.report_id == str(validation_id)
            )
        ]
        if len(refs) != 1:
            raise identity_mismatch("window evidence mapping is ambiguous")
        anchors = [
            {
                "evidence_id": refs[0].evidence_id,
                "content_hash": refs[0].content_hash,
                "report_id": refs[0].report_id,
            }
        ]
        endpoint_refs = []
        gaps = []
        for role, prefix, expected_dates in (
            ("TRAIN", "train", window.train_trade_dates),
            ("OOS", "oos", window.test_trade_dates),
        ):
            run_id = link.selected_train_run_id if role == "TRAIN" else link.oos_run_id
            bundle = AnalyticsArtifactBundle(
                selected["run"][run_id],
                *[
                    selected[name][getattr(link, f"{prefix}_{name}_id")]
                    for name in ("performance", "risk", "trade", "period")
                ],
            )
            date_hash = date_set_hash(tuple(date.fromisoformat(value) for value in expected_dates))
            date_hash_field = "train_date_hash" if role == "TRAIN" else "test_date_hash"
            if (
                list(dates[bundle.performance.id]) != expected_dates
                or date_hash != getattr(window, date_hash_field)
                or date_hash != getattr(link, date_hash_field)
            ):
                raise identity_mismatch("window trade dates do not match the exact M14 bundle")
            expected_metrics = {
                "annualized_return": bundle.performance.annualized_return,
                "max_drawdown_abs": -bundle.performance.max_drawdown,
                "sharpe_ratio": bundle.risk.sharpe_ratio,
                "annualized_turnover": bundle.trade.annualized_turnover,
            }
            if (
                bundle.performance.max_drawdown > 0
                or str(record[f"{prefix}_run_id"]) != str(run_id)
                or str(record[f"{prefix}_performance_id"]) != str(bundle.performance.id)
                or any(
                    getattr(link, f"{prefix}_{key}") != value
                    or contract_json(record[f"{prefix}_metrics"][key]) != contract_json(value)
                    for key, value in expected_metrics.items()
                )
                or link.identity_snapshot[prefix]["m14"]
                != _bundle_identity(bundle.performance, bundle.risk, bundle.trade, bundle.period)
                or link.identity_snapshot[prefix]["dates"]
                != {"hash": date_hash, "count": len(expected_dates)}
            ):
                raise identity_mismatch("window metrics do not match the exact M14 reports")
            body = m14_contract_body(
                bundle,
                dates[bundle.performance.id],
                evidence=anchors,
                record={"window_metrics": expected_metrics},
                limitations=[],
            )
            if body["status"] != "COMPLETE":
                gaps.extend(body["reason_codes"])
            drafts.append(
                FrozenContractDraft(
                    tool_call_id=tool_call_id,
                    contract_kind="M14_EXACT_BUNDLE",
                    subject_id=str(run_id),
                    role=role,
                    schema_version=M14_CONTRACT_VERSION,
                    verification_scope="FROZEN_CONTRACT_RECHECK",
                    contract_json=body,
                )
            )
            endpoint_refs.append(
                {"role": role, "subject_id": str(run_id), "contract_hash": contract_hash(body)}
            )
        if any(getattr(link, key) != value for key, value in window_degradation(link).items()):
            raise identity_mismatch("window degradation does not match the M15 formula")
        window_projection = _project(
            window,
            (
                "study_id",
                "window_no",
                "train_start_date",
                "train_end_date",
                "test_start_date",
                "test_end_date",
                "train_trade_days",
                "test_trade_days",
                "train_trade_dates",
                "test_trade_dates",
                "train_date_hash",
                "test_date_hash",
                "train_experiment_id",
                "train_evaluation_id",
                "selected_trial_id",
                "selected_parameter_hash",
                "selected_parameter_values",
                "selected_portfolio_config_hash",
                "oos_run_id",
            ),
        )
        body = contract_json(
            {
                "status": "GAP" if gaps else "COMPLETE",
                "reason_codes": sorted(set(gaps)),
                "study": study_projection,
                "validation": validation,
                "window": window_projection,
                "trial": _project(
                    trial,
                    (
                        "id",
                        "experiment_id",
                        "run_id",
                        "parameter_hash",
                        "parameter_values",
                        "portfolio_config_hash",
                    ),
                ),
                "evaluation": _project(
                    evaluation,
                    (
                        "id",
                        "experiment_id",
                        "status",
                        "policy_hash",
                        "source_hash",
                        "evaluation_version",
                        "selected_trial_id",
                        "selected_run_id",
                    ),
                ),
                "trial_evaluation": _project(
                    trial_evaluation,
                    (
                        "evaluation_id",
                        "experiment_id",
                        "trial_id",
                        "run_id",
                        "parameter_hash",
                        "performance_id",
                        "risk_id",
                        "trade_id",
                        "period_id",
                        "status",
                        "feasible",
                        "shortlisted",
                        "selection_rank",
                    ),
                ),
                "selection_snapshot_hash": config_hash(window.selected_portfolio_config_snapshot),
                "m14_contract_refs": endpoint_refs,
                "identity_snapshot": link.identity_snapshot,
                "record": record,
                "evidence": anchors,
            }
        )
        check_safe(body)
        drafts.append(
            FrozenContractDraft(
                tool_call_id=tool_call_id,
                contract_kind="M15_WINDOW_LINEAGE",
                subject_id=f"{study_id}:{validation_id}:{number}",
                role="STUDY",
                schema_version=M15_WINDOW_CONTRACT_VERSION,
                verification_scope="FROZEN_CONTRACT_RECHECK",
                contract_json=body,
            )
        )
    return drafts
