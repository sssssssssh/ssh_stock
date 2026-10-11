from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.performance import PortfolioPerformanceDaily
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundleResolver,
    AnalyticsBundleError,
    validate_exact_analytics_bundle,
)

if TYPE_CHECKING:
    from app.services.agent.chat.comparison_policy import ComparisonFactContext


COMPARISON_CONTRACT_POLICY_VERSION = "m16.2.2-comparison-v1"


@dataclass(frozen=True)
class ComparisonContract:
    run_id: uuid.UUID
    performance_id: uuid.UUID
    start_date: str
    end_date: str
    trade_days: int
    trade_dates: tuple[str, ...]
    frequency: str
    currency: str
    initial_cash: Decimal
    benchmark_code: str
    benchmark_source_hash: str
    portfolio_version: str
    portfolio_config_hash: str
    execution_version: str
    execution_config_hash: str
    accounting_version: str
    accounting_config_hash: str
    backtest_engine_version: str
    performance_version: str
    performance_config_hash: str
    performance_source_hash: str
    risk_version: str
    risk_config_hash: str
    risk_source_hash: str
    trade_version: str
    trade_config_hash: str
    trade_source_hash: str
    period_version: str
    period_config_hash: str
    period_source_hash: str
    execution_assumptions: str
    accounting_assumptions: str


@dataclass(frozen=True)
class ContractDecision:
    state: str
    reason_codes: tuple[str, ...]
    contracts: tuple[ComparisonContract, ...] = ()
    policy_version: str = COMPARISON_CONTRACT_POLICY_VERSION


def compare_contracts(
    contracts: list[ComparisonContract],
    *,
    metric_paths: list[str],
) -> ContractDecision:
    if len(contracts) < 2:
        return ContractDecision("INCOMPATIBLE", ("COMPARISON_CONTRACT_MISSING",))
    incompatible: list[str] = []
    context: list[str] = []
    first = contracts[0]
    hard_fields = {
        "FREQUENCY_MISMATCH": lambda row: row.frequency,
        "CURRENCY_MISMATCH": lambda row: row.currency,
        "PORTFOLIO_VERSION_MISMATCH": lambda row: row.portfolio_version,
        "PERFORMANCE_VERSION_MISMATCH": lambda row: row.performance_version,
        "PERFORMANCE_CONFIG_MISMATCH": lambda row: row.performance_config_hash,
        "RISK_VERSION_MISMATCH": lambda row: row.risk_version,
        "RISK_CONFIG_MISMATCH": lambda row: row.risk_config_hash,
        "TRADE_VERSION_MISMATCH": lambda row: row.trade_version,
        "TRADE_CONFIG_MISMATCH": lambda row: row.trade_config_hash,
        "PERIOD_VERSION_MISMATCH": lambda row: row.period_version,
        "PERIOD_CONFIG_MISMATCH": lambda row: row.period_config_hash,
        "EXECUTION_VERSION_MISMATCH": lambda row: row.execution_version,
        "ACCOUNTING_VERSION_MISMATCH": lambda row: row.accounting_version,
        "BACKTEST_ENGINE_VERSION_MISMATCH": lambda row: row.backtest_engine_version,
    }
    for code, getter in hard_fields.items():
        if any(getter(item) != getter(first) for item in contracts[1:]):
            incompatible.append(code)
    benchmark_differs = any(
        (item.benchmark_code, item.benchmark_source_hash)
        != (first.benchmark_code, first.benchmark_source_hash)
        for item in contracts[1:]
    )
    benchmark_metric = any(
        ".risk." in path or "benchmark_" in path or "excess_" in path
        for path in metric_paths
    )
    if benchmark_differs:
        (incompatible if benchmark_metric else context).append("BENCHMARK_MISMATCH")
    contextual_fields = {
        "DATE_RANGE_MISMATCH": lambda row: (row.start_date, row.end_date),
        "TRADE_DATE_SET_MISMATCH": lambda row: row.trade_dates,
        "SAMPLE_SIZE_MISMATCH": lambda row: row.trade_days,
        "INITIAL_CASH_MISMATCH": lambda row: row.initial_cash,
        "EXECUTION_CONFIG_MISMATCH": lambda row: row.execution_config_hash,
        "ACCOUNTING_CONFIG_MISMATCH": lambda row: row.accounting_config_hash,
        "EXECUTION_ASSUMPTION_MISMATCH": lambda row: row.execution_assumptions,
        "ACCOUNTING_ASSUMPTION_MISMATCH": lambda row: row.accounting_assumptions,
    }
    for code, getter in contextual_fields.items():
        if any(getter(item) != getter(first) for item in contracts[1:]):
            context.append(code)
    if incompatible:
        return ContractDecision(
            "INCOMPATIBLE",
            tuple(dict.fromkeys(incompatible)),
            tuple(contracts),
        )
    if context:
        return ContractDecision(
            "CONTEXT_REQUIRED",
            tuple(dict.fromkeys(context)),
            tuple(contracts),
        )
    return ContractDecision("COMPARABLE", (), tuple(contracts))


class BacktestComparisonContractResolver:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.bundle_resolver = AnalyticsArtifactBundleResolver(db)

    def resolve(self, facts: list[ComparisonFactContext]) -> ContractDecision:
        run_groups: dict[uuid.UUID, list[ComparisonFactContext]] = {}
        for fact in facts:
            if fact.tool_name != "performance.summary":
                return ContractDecision(
                    "INCOMPATIBLE", ("EXACT_M14_BUNDLE_REQUIRED",)
                )
            run_id = _uuid_or_none(fact.evidence.get("calc_run_id"))
            if run_id is None:
                return ContractDecision("INCOMPATIBLE", ("RUN_ID_MISSING",))
            run_groups.setdefault(run_id, []).append(fact)
        if len(run_groups) < 2:
            return ContractDecision("INCOMPATIBLE", ("DISTINCT_RUNS_REQUIRED",))
        contracts: list[ComparisonContract] = []
        try:
            for run_id, grouped in run_groups.items():
                identity = grouped[0].identity
                ids = {
                    name: _uuid_or_none(identity.get(name))
                    for name in ("performance_id", "risk_id", "trade_id", "period_id")
                }
                if any(value is None for value in ids.values()):
                    return ContractDecision(
                        "INCOMPATIBLE", ("COMPLETE_M14_IDENTITY_REQUIRED",)
                    )
                bundle = self.bundle_resolver.resolve(
                    run_id,
                    performance_id=ids["performance_id"],
                    risk_id=ids["risk_id"],
                    trade_id=ids["trade_id"],
                    period_id=ids["period_id"],
                    require_period=True,
                )
                validate_exact_analytics_bundle(bundle, require_period=True)
                dates = tuple(
                    value.isoformat()
                    for value in self.db.scalars(
                        select(PortfolioPerformanceDaily.trade_date)
                        .where(
                            PortfolioPerformanceDaily.performance_id
                            == bundle.performance.id
                        )
                        .order_by(PortfolioPerformanceDaily.trade_date)
                    ).all()
                )
                if len(dates) != bundle.performance.trade_days:
                    return ContractDecision(
                        "INCOMPATIBLE", ("PERFORMANCE_DATE_SERIES_INCOMPLETE",)
                    )
                contracts.append(_contract(bundle, dates))
        except (AnalyticsBundleError, ValueError, TypeError, KeyError):
            return ContractDecision(
                "INCOMPATIBLE", ("COMPARISON_CONTRACT_UNVERIFIABLE",)
            )
        return compare_contracts(
            contracts,
            metric_paths=[fact.path for fact in facts],
        )


def _contract(bundle: Any, dates: tuple[str, ...]) -> ComparisonContract:
    run = bundle.run
    performance = bundle.performance
    risk = bundle.risk
    trade = bundle.trade
    period = bundle.period
    if period is None:
        raise ValueError("period report is required")
    snapshot = run.config_snapshot
    if not isinstance(snapshot, dict):
        raise ValueError("run snapshot is invalid")
    execution = snapshot.get("execution")
    accounting = snapshot.get("accounting")
    if not isinstance(execution, dict) or not isinstance(accounting, dict):
        raise ValueError("run execution/accounting snapshot is incomplete")
    return ComparisonContract(
        run_id=run.id,
        performance_id=performance.id,
        start_date=performance.start_date.isoformat(),
        end_date=performance.end_date.isoformat(),
        trade_days=performance.trade_days,
        trade_dates=dates,
        frequency="DAILY",
        currency="CNY",
        initial_cash=run.initial_cash,
        benchmark_code=risk.benchmark_code,
        benchmark_source_hash=risk.benchmark_source_hash,
        portfolio_version=run.portfolio_version,
        portfolio_config_hash=run.portfolio_config_hash,
        execution_version=run.execution_version,
        execution_config_hash=run.execution_config_hash,
        accounting_version=run.accounting_version,
        accounting_config_hash=run.accounting_config_hash,
        backtest_engine_version=run.backtest_engine_version,
        performance_version=performance.performance_version,
        performance_config_hash=performance.performance_config_hash,
        performance_source_hash=performance.source_hash,
        risk_version=risk.risk_version,
        risk_config_hash=risk.risk_config_hash,
        risk_source_hash=risk.risk_source_hash,
        trade_version=trade.trade_version,
        trade_config_hash=trade.trade_config_hash,
        trade_source_hash=trade.trade_source_hash,
        period_version=period.period_version,
        period_config_hash=period.period_config_hash,
        period_source_hash=period.period_source_hash,
        execution_assumptions=_canonical(execution),
        accounting_assumptions=_canonical(accounting),
    )


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value is not None else None
    except (TypeError, ValueError, AttributeError):
        return None
