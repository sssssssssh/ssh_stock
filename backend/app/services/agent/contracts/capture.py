from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.agent.contracts import AgentToolResult
from app.domain.agent.errors import identity_mismatch, resource_limit_exceeded
from app.domain.agent.frozen_contracts import M14_CONTRACT_VERSION, FrozenContractDraft
from app.models.performance import PortfolioPerformanceDaily, PortfolioPerformanceReport
from app.models.performance_period import PortfolioPerformancePeriodReport
from app.models.performance_risk import PortfolioPerformanceRiskReport
from app.models.performance_trade import PortfolioPerformanceTradeReport
from app.models.portfolio import PortfolioBacktestRun
from app.services.agent.chat.comparison_contract import build_comparison_contract
from app.services.agent.contracts.canonical import contract_json
from app.services.performance.analytics_bundle import (
    AnalyticsArtifactBundle,
    AnalyticsBundleError,
    validate_exact_analytics_bundle,
)


def capture_research_contracts(
    db: Session,
    result: AgentToolResult,
    *,
    tool_call_id: str,
    max_trade_dates: int,
) -> list[FrozenContractDraft]:
    if result.status != "READY" or result.tool_name != "performance.summary":
        return []
    ids = result.identity
    try:
        run_id = UUID(str(ids["run_id"]))
        performance_id = UUID(str(ids["performance_id"]))
        risk_id = UUID(str(ids["risk_id"]))
        trade_id = UUID(str(ids["trade_id"]))
        period_id = UUID(str(ids["period_id"])) if ids.get("period_id") else None
    except (KeyError, TypeError, ValueError) as exc:
        raise identity_mismatch("selected analytics identity is incomplete") from exc

    selected = {
        "run_id": str(run_id),
        "performance_id": str(performance_id),
        "risk_id": str(risk_id),
        "trade_id": str(trade_id),
        "period_id": str(period_id) if period_id else None,
    }
    evidence = [
        {
            "evidence_id": item.evidence_id,
            "content_hash": item.content_hash,
            "report_id": item.report_id,
        }
        for item in result.evidence
    ]
    if period_id is None:
        body: dict[str, Any] = {
            "status": "GAP",
            "reason_codes": ["PERIOD_REPORT_MISSING"],
            "selected": selected,
            "evidence": evidence,
        }
    else:
        bundle = AnalyticsArtifactBundle(
            _selected(db, PortfolioBacktestRun, run_id),
            _selected(db, PortfolioPerformanceReport, performance_id),
            _selected(db, PortfolioPerformanceRiskReport, risk_id),
            _selected(db, PortfolioPerformanceTradeReport, trade_id),
            _selected(db, PortfolioPerformancePeriodReport, period_id),
        )
        if any(item is None for item in asdict_bundle(bundle)):
            raise identity_mismatch("selected analytics bundle disappeared")
        try:
            validate_exact_analytics_bundle(bundle, require_period=True)
        except AnalyticsBundleError as exc:
            raise identity_mismatch("selected analytics bundle changed") from exc
        dates = tuple(
            value.isoformat()
            for value in db.scalars(
                select(PortfolioPerformanceDaily.trade_date)
                .where(PortfolioPerformanceDaily.performance_id == performance_id)
                .order_by(PortfolioPerformanceDaily.trade_date)
                .limit(max_trade_dates + 1)
            ).all()
        )
        if len(dates) > max_trade_dates:
            raise resource_limit_exceeded("frozen contract trade dates exceed the limit")
        if (
            len(dates) != bundle.performance.trade_days
            or not dates
            or dates[0] != bundle.performance.start_date.isoformat()
            or dates[-1] != bundle.performance.end_date.isoformat()
            or len(set(dates)) != len(dates)
        ):
            body = {
                "status": "GAP",
                "reason_codes": ["PERFORMANCE_DATE_SERIES_INCOMPLETE"],
                "selected": selected,
                "evidence": evidence,
            }
        else:
            try:
                comparison = build_comparison_contract(bundle, dates)
            except (KeyError, TypeError, ValueError):
                body = {
                    "status": "GAP",
                    "reason_codes": ["EXECUTION_ACCOUNTING_SNAPSHOT_INCOMPLETE"],
                    "selected": selected,
                    "evidence": evidence,
                }
            else:
                body = {
                    "status": "COMPLETE",
                    "selected": selected,
                    "comparison_contract": contract_json(asdict(comparison)),
                    "record": contract_json(result.records[0]),
                    "evidence": evidence,
                    "limitations": list(result.warnings),
                }
    return [
        FrozenContractDraft(
            tool_call_id=tool_call_id,
            contract_kind="M14_EXACT_BUNDLE",
            subject_id=str(run_id),
            role="LIVE",
            schema_version=M14_CONTRACT_VERSION,
            verification_scope="FROZEN_CONTRACT_RECHECK",
            contract_json=body,
        )
    ]


def asdict_bundle(bundle: AnalyticsArtifactBundle) -> tuple[Any, ...]:
    return (bundle.run, bundle.performance, bundle.risk, bundle.trade, bundle.period)


def _selected(db: Session, model: Any, row_id: UUID):
    return db.scalar(
        select(model).where(model.id == row_id).execution_options(populate_existing=True)
    )
