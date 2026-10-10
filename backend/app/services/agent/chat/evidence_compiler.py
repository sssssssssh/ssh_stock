from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from pydantic import ValidationError

from app.domain.agent.chat import ChatCitation, StructuredAnswerDraft
from app.domain.agent.chat_errors import AgentChatError
from app.services.agent.chat.orchestrator import ToolResultContext


class CompiledEvidenceAnswer:
    def __init__(
        self,
        *,
        answer: str,
        citations: list[ChatCitation],
        warnings: list[str],
        insufficient_evidence: bool,
    ) -> None:
        self.answer = answer
        self.citations = citations
        self.warnings = warnings
        self.insufficient_evidence = insufficient_evidence


class EvidenceCompiler:
    def __init__(self, *, max_answer_chars: int) -> None:
        self.max_answer_chars = max_answer_chars

    def compile(
        self,
        *,
        final_text: str,
        tool_results: list[ToolResultContext],
        inherited_warnings: list[str],
    ) -> CompiledEvidenceAnswer:
        draft = self._parse_draft(final_text)
        evidence = _evidence_map(tool_results)
        warnings = list(inherited_warnings)
        warnings.extend(draft.warnings)
        citations: list[ChatCitation] = []
        seen: set[str] = set()
        for evidence_id in draft.evidence_ids:
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            item = evidence.get(evidence_id)
            if item is None:
                warnings.append("UNVERIFIED_CITATION")
                continue
            tool_name, ref, as_of_date = item
            if ref.get("quality_status") == "ERROR":
                warnings.append("EVIDENCE_QUALITY_ERROR")
                continue
            citations.append(
                ChatCitation(
                    marker=f"E{len(citations) + 1}",
                    evidence_id=evidence_id,
                    evidence_version=ref.get("evidence_version", "v1"),
                    tool_name=tool_name,
                    entity_id=str(ref.get("entity_id", "unknown")),
                    as_of_date=ref.get("trade_date") or as_of_date,
                    report_id=ref.get("report_id"),
                    calc_run_id=ref.get("calc_run_id"),
                    content_hash=ref.get("content_hash"),
                )
            )

        warnings.extend(_context_warnings(citations, evidence))
        insufficient = not citations
        if insufficient:
            warnings.append("INSUFFICIENT_EVIDENCE")
            if not draft.needs_clarification:
                answer = "现有只读工具没有提供足够、可验证的证据，无法形成数据结论。"
            else:
                answer = draft.answer
        else:
            answer = draft.answer
            markers = " ".join(f"[{item.marker}]" for item in citations)
            answer = f"{answer}\n\n证据引用：{markers}"

        if len(answer) > self.max_answer_chars:
            raise AgentChatError(
                "LLM_OUTPUT_LIMIT_EXCEEDED",
                "LLM answer exceeds the configured character limit",
                status_code=502,
            )
        return CompiledEvidenceAnswer(
            answer=answer,
            citations=citations,
            warnings=list(dict.fromkeys(warnings)),
            insufficient_evidence=insufficient,
        )

    @staticmethod
    def _parse_draft(final_text: str) -> StructuredAnswerDraft:
        try:
            payload = json.loads(final_text)
            return StructuredAnswerDraft.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise AgentChatError(
                "LLM_INVALID_RESPONSE",
                "LLM final response does not match the required structured format",
                status_code=502,
            ) from exc


def _evidence_map(
    tool_results: list[ToolResultContext],
) -> dict[str, tuple[str, dict[str, Any], Any]]:
    result: dict[str, tuple[str, dict[str, Any], Any]] = {}
    for context in tool_results:
        as_of_date = context.payload.get("as_of_date")
        refs = context.payload.get("evidence")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("evidence_id"), str):
                continue
            result.setdefault(ref["evidence_id"], (context.tool_name, ref, as_of_date))
    return result


def _context_warnings(
    citations: list[ChatCitation],
    evidence: dict[str, tuple[str, dict[str, Any], Any]],
) -> list[str]:
    warnings: list[str] = []
    dates = {str(item.as_of_date) for item in citations if item.as_of_date is not None}
    if len(dates) > 1:
        warnings.append("MIXED_AS_OF_DATES")

    identities: dict[str, set[tuple[Any, Any, Any]]] = defaultdict(set)
    for citation in citations:
        tool_name, ref, _ = evidence[citation.evidence_id]
        identities[tool_name].add(
            (ref.get("calc_version"), ref.get("config_hash"), ref.get("source_hash"))
        )
    if any(len(values) > 1 for values in identities.values()):
        warnings.append("MIXED_EVIDENCE_IDENTITY")
    tools = {item.tool_name for item in citations}
    if "backtest.summary" in tools and "walk_forward.summary" in tools:
        warnings.append("HISTORICAL_AND_OOS_EVIDENCE_MUST_BE_DISTINGUISHED")
    return warnings
