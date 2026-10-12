from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from app.core.agent_report_config import AgentReportConfig
from app.domain.agent.chat import ChatCitation, RejectedClaim, StructuredClaim
from app.domain.agent.report import (
    ReportChart,
    ReportEvidenceIdentity,
    ReportSection,
    ReportSourceContract,
    ReportType,
    ResearchReportSnapshot,
)
from app.domain.agent.report_errors import invalid_source
from app.services.agent.chat.comparison_policy import COMPARISON_POLICY_VERSION
from app.services.agent.chat.metadata import normalized_answer_metadata

REPORT_VERSION = "m16.4-v1"


def build_report_snapshot(
    *,
    report_type: ReportType,
    title: str | None,
    source_chat_id: Any,
    source_message_id: Any,
    source_turn_id: Any,
    source_metadata: dict[str, Any],
    config: AgentReportConfig,
) -> tuple[ResearchReportSnapshot, ReportSourceContract]:
    normalized = normalized_answer_metadata(source_metadata)
    if normalized["answer_status"] == "INSUFFICIENT_EVIDENCE":
        raise invalid_source(
            "INSUFFICIENT_VERIFIED_FACTS",
            "source answer has no verified reportable claims",
        )

    citations: dict[str, ChatCitation] = {}
    raw_citations = normalized.get("citations", [])
    if isinstance(raw_citations, list):
        for raw in raw_citations:
            try:
                citation = ChatCitation.model_validate(raw)
            except ValueError:
                continue
            citations[citation.evidence_id] = citation

    verified: list[StructuredClaim] = []
    rejected = [
        RejectedClaim.model_validate(item) for item in normalized["rejected_claims"]
    ]
    used_evidence: set[str] = set()
    for raw in normalized["verified_claims"]:
        claim = StructuredClaim.model_validate(raw)
        missing = [item for item in claim.evidence_ids if item not in citations]
        if not claim.evidence_ids or missing:
            rejected.append(
                RejectedClaim(
                    claim_id=claim.claim_id,
                    claim_type=claim.claim_type,
                    reason_codes=["EVIDENCE_NOT_ARCHIVED"],
                    comparison_state=claim.comparison_state,
                    policy_version=claim.policy_version,
                )
            )
            continue
        verified.append(claim)
        used_evidence.update(claim.evidence_ids)

    if not verified:
        raise invalid_source(
            "INSUFFICIENT_VERIFIED_FACTS",
            "source answer has no fully cited verified claims",
        )
    selected_citations = [citations[key] for key in sorted(used_evidence)]
    if len(verified) + len(rejected) > config.max_claims:
        raise invalid_source("REPORT_LIMIT_EXCEEDED", "claim limit exceeded")
    if len(selected_citations) > config.max_citations:
        raise invalid_source("REPORT_LIMIT_EXCEEDED", "citation limit exceeded")

    all_dates = [
        fact.trade_date for claim in verified for fact in claim.structured_facts
    ] + [citation.as_of_date for citation in selected_citations if citation.as_of_date]
    as_of_date = max(all_dates) if all_dates else None
    warnings = list(
        dict.fromkeys(
            [
                *normalized["warnings"],
                "SOURCE_PAYLOAD_NOT_ARCHIVED",
                "REPLAY_UNAVAILABLE",
            ]
        )
    )
    charts, chart_warnings = _build_charts(verified, config)
    warnings.extend(item for item in chart_warnings if item not in warnings)
    if len(warnings) > 128:
        raise invalid_source("REPORT_LIMIT_EXCEEDED", "warning limit exceeded")
    sections = _build_sections(verified, selected_citations)
    if len(sections) > config.max_sections:
        raise invalid_source("REPORT_LIMIT_EXCEEDED", "section limit exceeded")
    resolved_title = title if title else _default_title(report_type, as_of_date)
    snapshot = ResearchReportSnapshot(
        report_type=report_type,
        title=resolved_title,
        as_of_date=as_of_date,
        source_answer_status=normalized["answer_status"],
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        source_turn_id=source_turn_id,
        claims=verified,
        rejected_claims=rejected,
        citations=selected_citations,
        sections=sections,
        charts=charts,
        warnings=warnings,
    )
    limitations = ["SOURCE_PAYLOAD_NOT_ARCHIVED", "REPLAY_UNAVAILABLE"]
    if any(item.tool_name == "performance.summary" for item in selected_citations):
        limitations.append("EXACT_M14_BUNDLE_NOT_ARCHIVED")
    contract = ReportSourceContract(
        comparison_policy_version=COMPARISON_POLICY_VERSION,
        tool_names=sorted({item.tool_name for item in selected_citations}),
        evidence_versions=sorted({item.evidence_version for item in selected_citations}),
        evidence_identities=[
            ReportEvidenceIdentity(
                **citation.model_dump(
                    mode="python", exclude={"marker", "observed_at", "navigation"}
                )
            )
            for citation in selected_citations
        ],
        limitations=limitations,
    )
    return snapshot, contract


def _build_sections(
    claims: list[StructuredClaim], citations: list[ChatCitation]
) -> list[ReportSection]:
    sections = [
        ReportSection(
            section_id="research-scope",
            title="研究范围与口径",
            items=["仅固化来源消息中已验证且有归档引用的结论"],
        ),
        ReportSection(
            section_id="verified-facts",
            title="已验证事实",
            claim_ids=[
                claim.claim_id for claim in claims if claim.claim_type != "INFERENCE"
            ],
        ),
    ]
    inference_ids = [
        claim.claim_id for claim in claims if claim.claim_type == "INFERENCE"
    ]
    sections.append(
        ReportSection(
            section_id="bounded-inference",
            title="有限推断",
            claim_ids=inference_ids,
            items=[] if inference_ids else ["无已验证支持的有限推断"],
        )
    )
    sections.extend(
        [
            ReportSection(
                section_id="methodology-limitations",
                title="统计口径与限制",
                items=["SOURCE_PAYLOAD_NOT_ARCHIVED", "REPLAY_UNAVAILABLE"],
            ),
            ReportSection(
                section_id="evidence-appendix",
                title="Evidence 附录",
                items=[citation.evidence_id for citation in citations],
            ),
            ReportSection(
                section_id="generation-notes",
                title="生成说明",
                items=["m16.4-v1", "CLAIM_SNAPSHOT_ONLY"],
            ),
        ]
    )
    return sections


def _build_charts(
    claims: list[StructuredClaim], config: AgentReportConfig
) -> tuple[list[ReportChart], list[str]]:
    facts = [
        (claim.claim_id, fact)
        for claim in claims
        for fact in claim.structured_facts
    ]
    if not facts or config.max_charts == 0:
        return [], ["SERIES_NOT_AVAILABLE"]
    rows = [
        [
            claim_id,
            fact.entity,
            fact.trade_date.isoformat(),
            fact.path,
            str(fact.value),
            fact.unit,
            fact.sample_role,
        ]
        for claim_id, fact in facts[: config.max_points_per_chart]
    ]
    warnings = ["SERIES_NOT_AVAILABLE"]
    if len(facts) > len(rows):
        warnings.append("CHART_POINTS_TRUNCATED")
    charts = [
        ReportChart(
            chart_id="verified-metrics",
            chart_type="table",
            title="已验证指标",
            unit="mixed",
            columns=["claim", "entity", "date", "metric", "value", "unit", "sample"],
            rows=rows,
        )
    ]
    groups: dict[tuple[date, str, str], list[tuple[str, Any]]] = defaultdict(list)
    for _, fact in facts:
        groups[(fact.trade_date, fact.path.split(".")[-1], fact.unit)].append(
            (fact.entity, fact.value)
        )
    for (trade_date, metric, unit), values in sorted(groups.items()):
        if len({entity for entity, _ in values}) < 2 or len(charts) >= config.max_charts:
            continue
        charts.append(
            ReportChart(
                chart_id=f"ranking-{len(charts)}",
                chart_type="bar",
                title=f"{trade_date.isoformat()} {metric}",
                unit=unit,
                columns=["entity", "value"],
                rows=[
                    [entity, str(value)]
                    for entity, value in values[: config.max_points_per_chart]
                ],
            )
        )
    return charts, warnings


def _default_title(report_type: ReportType, as_of_date: date | None) -> str:
    labels = {
        "market_review": "市场复盘",
        "opportunity_review": "机会复盘",
        "strategy_review": "策略复盘",
        "oos_review": "样本外验证复盘",
    }
    return f"{labels[report_type]} · {as_of_date.isoformat() if as_of_date else '日期未提供'}"
