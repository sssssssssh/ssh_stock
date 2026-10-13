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
from app.services.agent.contracts.m14 import m14_contract_body
from app.services.performance.analytics_bundle import AnalyticsArtifactBundle


def capture_research_contracts(
    db: Session,
    result: AgentToolResult,
    *,
    tool_call_id: str,
    max_trade_dates: int,
) -> list[FrozenContractDraft]:
    if result.status != "READY":
        return []
    if result.tool_name in {"walk_forward.summary", "walk_forward.window_lineage"}:
        from app.services.agent.contracts.m15 import capture_m15_contracts

        return capture_m15_contracts(
            db, result, tool_call_id=tool_call_id, max_trade_dates=max_trade_dates
        )
    if result.tool_name != "performance.summary":
        return []
    ids = result.identity
    try:
        selected = {
            name: UUID(str(ids[name])) if ids.get(name) else None
            for name in ("run_id", "performance_id", "risk_id", "trade_id", "period_id")
        }
        if any(
            selected[name] is None for name in ("run_id", "performance_id", "risk_id", "trade_id")
        ):
            raise ValueError("missing selection")
    except (KeyError, TypeError, ValueError) as exc:
        raise identity_mismatch("selected analytics identity is incomplete") from exc
    rows = [
        db.scalar(select(model).where(model.id == selected[name])) if selected[name] else None
        for name, model in (
            ("run_id", PortfolioBacktestRun),
            ("performance_id", PortfolioPerformanceReport),
            ("risk_id", PortfolioPerformanceRiskReport),
            ("trade_id", PortfolioPerformanceTradeReport),
            ("period_id", PortfolioPerformancePeriodReport),
        )
    ]
    if any(row is None for row in rows[:4]) or (selected["period_id"] and rows[4] is None):
        raise identity_mismatch("selected analytics bundle disappeared")
    dates = performance_dates(db, [selected["performance_id"]], max_trade_dates)
    body = m14_contract_body(
        AnalyticsArtifactBundle(*rows),
        dates[selected["performance_id"]],
        evidence=evidence_anchors(result),
        record=result.records[0],
        limitations=result.warnings,
    )
    return [
        FrozenContractDraft(
            tool_call_id=tool_call_id,
            contract_kind="M14_EXACT_BUNDLE",
            subject_id=str(selected["run_id"]),
            role="LIVE",
            schema_version=M14_CONTRACT_VERSION,
            verification_scope="FROZEN_CONTRACT_RECHECK",
            contract_json=body,
        )
    ]


def performance_dates(db, ids, max_trade_dates):
    grouped = {row_id: [] for row_id in ids}
    for row_id, value in db.execute(
        select(PortfolioPerformanceDaily.performance_id, PortfolioPerformanceDaily.trade_date)
        .where(PortfolioPerformanceDaily.performance_id.in_(ids))
        .order_by(PortfolioPerformanceDaily.performance_id, PortfolioPerformanceDaily.trade_date)
        .limit(len(ids) * max_trade_dates + 1)
    ):
        grouped[row_id].append(value.isoformat())
        if len(grouped[row_id]) > max_trade_dates:
            raise resource_limit_exceeded("frozen contract trade dates exceed the limit")
    return {row_id: tuple(values) for row_id, values in grouped.items()}


def evidence_anchors(result):
    return [
        {
            "evidence_id": ref.evidence_id,
            "content_hash": ref.content_hash,
            "report_id": ref.report_id,
        }
        for ref in result.evidence
    ]
