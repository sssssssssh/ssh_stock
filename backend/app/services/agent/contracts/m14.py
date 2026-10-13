from dataclasses import asdict
from typing import Any

from app.core.accounting_config import AccountingConfig
from app.core.execution_config import ExecutionConfig
from app.domain.agent.errors import identity_mismatch
from app.services.agent.archive.projectors import check_safe
from app.services.agent.chat.comparison_contract import build_comparison_contract
from app.services.agent.contracts.canonical import contract_hash, contract_json
from app.services.calc_metadata import config_hash
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundle,
    AnalyticsBundleError,
    validate_exact_analytics_bundle,
)

REPORT_FIELDS = {
    "performance": (
        "performance_version",
        "performance_config_hash",
        "source_hash",
        "final_nav",
        "cumulative_return",
        "annualized_return",
        "max_drawdown",
    ),
    "risk": (
        "performance_id",
        "risk_version",
        "risk_config_hash",
        "risk_source_hash",
        "benchmark_code",
        "benchmark_source_hash",
        "benchmark_cumulative_return",
        "excess_cumulative_return",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
    ),
    "trade": (
        "performance_id",
        "trade_version",
        "trade_config_hash",
        "trade_source_hash",
        "total_turnover",
        "annualized_turnover",
        "total_execution_cost",
        "closed_episode_count",
        "open_episode_count",
        "win_rate",
        "profit_factor",
    ),
    "period": (
        "performance_id",
        "risk_id",
        "trade_id",
        "period_version",
        "period_config_hash",
        "period_source_hash",
        "month_count",
        "year_count",
    ),
}
RUN_FIELDS = (
    "id",
    "status",
    "account_mode",
    "start_date",
    "end_date",
    "initial_cash",
    "benchmark_code",
    "algo_version",
    "source_strategy_config_hash",
    "opportunity_calc_version",
    "opportunity_config_hash",
    "portfolio_version",
    "portfolio_config_hash",
    "execution_version",
    "execution_config_hash",
    "accounting_version",
    "accounting_config_hash",
    "backtest_engine_version",
)


def selected_ids(bundle: AnalyticsArtifactBundle) -> dict[str, str | None]:
    return {
        "run_id": str(bundle.run.id),
        **{
            name + "_id": str(getattr(bundle, name).id) if getattr(bundle, name) else None
            for name in ("performance", "risk", "trade", "period")
        },
    }


def m14_contract_body(
    bundle: AnalyticsArtifactBundle,
    dates: tuple[str, ...],
    *,
    evidence: list[dict[str, Any]],
    record: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    common = {"selected": selected_ids(bundle), "evidence": evidence}
    try:
        validate_exact_analytics_bundle(bundle, require_period=bundle.period is not None)
    except AnalyticsBundleError as exc:
        raise identity_mismatch("selected analytics bundle changed") from exc
    if bundle.period is None:
        return {**common, "status": "GAP", "reason_codes": ["PERIOD_REPORT_MISSING"]}
    performance = bundle.performance
    if (
        not dates
        or len(dates) != performance.trade_days
        or tuple(sorted(set(dates))) != dates
        or dates[0] != performance.start_date.isoformat()
        or dates[-1] != performance.end_date.isoformat()
    ):
        return {**common, "status": "GAP", "reason_codes": ["PERFORMANCE_DATE_SERIES_INCOMPLETE"]}
    versions = (
        performance.performance_version,
        bundle.risk.risk_version,
        bundle.trade.trade_version,
        bundle.period.period_version,
    )
    if versions != ("performance_v1", "risk_v1", "trade_v1", "period_v1"):
        return {**common, "status": "GAP", "reason_codes": ["M14_MODEL_VERSION_UNSUPPORTED"]}
    snapshot = bundle.run.config_snapshot
    check_safe(snapshot)
    try:
        ExecutionConfig.model_validate(snapshot["execution"])
        AccountingConfig.model_validate(snapshot["accounting"])
        comparison = build_comparison_contract(bundle, dates)
    except (KeyError, TypeError, ValueError):
        return {
            **common,
            "status": "GAP",
            "reason_codes": ["EXECUTION_ACCOUNTING_SNAPSHOT_INCOMPLETE"],
        }
    if any(
        config_hash(snapshot[name]) != getattr(bundle.run, name + "_config_hash")
        for name in ("execution", "accounting")
    ):
        raise identity_mismatch("run assumptions do not match their frozen hashes")
    rows = {"run": {name: getattr(bundle.run, name) for name in RUN_FIELDS}}
    for name, fields in REPORT_FIELDS.items():
        row = getattr(bundle, name)
        rows[name] = {
            field: getattr(row, field)
            for field in ("id", "run_id", "status", "start_date", "end_date", "trade_days", *fields)
        }
    return contract_json(
        {
            **common,
            "status": "COMPLETE",
            "comparison_contract": asdict(comparison),
            "trade_dates_hash": contract_hash(dates),
            "bundle_rows": rows,
            "execution_snapshot": snapshot["execution"],
            "accounting_snapshot": snapshot["accounting"],
            "record": record,
            "limitations": limitations,
        }
    )
