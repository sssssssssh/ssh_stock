from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from fnmatch import fnmatchcase
from typing import Any

from pydantic import ValidationError

from app.domain.agent.chat import (
    ChatCitation,
    StructuredAnswerDraft,
    StructuredClaim,
    StructuredFact,
)
from app.domain.agent.chat_errors import AgentChatError
from app.services.agent.chat.comparison_policy import (
    ComparisonFactContext,
    ComparisonPolicyError,
    EvidenceComparisonPolicy,
)
from app.services.agent.chat.orchestrator import ToolResultContext

_ALLOWED_PATHS: dict[str, tuple[str, ...]] = {
    "test.read": ("records.*.value",),
    "data.coverage": (
        "records.*.dataset_coverage.*.expected_rows",
        "records.*.dataset_coverage.*.actual_rows",
        "records.*.dataset_coverage.*.coverage_rate",
        "records.*.dataset_coverage.*.quality_days",
        "records.*.dataset_coverage.*.open_trade_days",
        "records.*.dataset_coverage.*.missing_quality_days",
        "records.*.latest_trading_date",
    ),
    "market.snapshot": (
        "records.*.market_score",
        "records.*.breadth.breadth20",
        "records.*.breadth.breadth60",
        "records.*.breadth.up_count",
        "records.*.breadth.down_count",
        "records.*.breadth.up_rate",
        "records.*.liquidity.total_amount",
        "records.*.liquidity.amount_ratio20",
        "records.*.liquidity.liquidity_score",
    ),
    "sector.top": (
        "records.*.heat_score",
        "records.*.heat_rank",
        "records.*.momentum.heat_momentum1",
        "records.*.momentum.heat_momentum3",
        "records.*.momentum.rank_change",
        "records.*.member_count",
    ),
    "theme.top": (
        "records.*.heat_score",
        "records.*.heat_rank",
        "records.*.momentum.heat_momentum1",
        "records.*.momentum.heat_momentum3",
        "records.*.momentum.rank_change",
        "records.*.source_coverage",
        "records.*.data_coverage",
        "records.*.member_snapshot_date",
    ),
    "opportunity.list": (
        "records.*.score",
        "records.*.left_reversal_score",
        "records.*.right_side_score",
        "records.*.trend_score",
    ),
    "backtest.summary": (
        "records.*.start_date",
        "records.*.end_date",
        "records.*.initial_cash",
        "records.*.latest_nav_date",
        "records.*.latest_nav",
        "records.*.latest_total_assets",
    ),
    "performance.summary": (
        "records.*.performance.start_date",
        "records.*.performance.end_date",
        "records.*.performance.trade_days",
        "records.*.performance.final_nav",
        "records.*.performance.cumulative_return",
        "records.*.performance.annualized_return",
        "records.*.performance.max_drawdown",
        "records.*.risk.benchmark_cumulative_return",
        "records.*.risk.excess_cumulative_return",
        "records.*.risk.sharpe_ratio",
        "records.*.risk.sortino_ratio",
        "records.*.risk.calmar_ratio",
        "records.*.trade.total_turnover",
        "records.*.trade.total_execution_cost",
        "records.*.trade.closed_episode_count",
        "records.*.trade.open_episode_count",
        "records.*.trade.win_rate",
        "records.*.trade.profit_factor",
        "records.*.period.month_count",
        "records.*.period.year_count",
    ),
    "walk_forward.summary": (
        "records.*.oos_sample.window_count",
        "records.*.oos_sample.total_oos_trade_days",
        "records.*.oos_sample.positive_oos_window_count",
        "records.*.oos_sample.positive_oos_window_rate",
        "records.*.returns.stitched_oos_final_nav",
        "records.*.returns.stitched_oos_cumulative_return",
        "records.*.returns.stitched_oos_annualized_return",
        "records.*.returns.stitched_oos_max_drawdown",
        "records.*.returns.stitched_excess_cumulative_return",
        "records.*.parameter_switching.unique_selected_parameter_hash_count",
        "records.*.parameter_switching.dominant_parameter_hash_rate",
        "records.*.parameter_switching.transition_count",
        "records.*.parameter_switching.switch_count",
        "records.*.parameter_switching.switch_rate",
        "records.*.train_to_oos_degradation.mean_return_degradation",
        "records.*.train_to_oos_degradation.median_return_degradation",
        "records.*.train_to_oos_degradation.mean_drawdown_worsening",
        "records.*.train_to_oos_degradation.median_drawdown_worsening",
    ),
}


@dataclass(frozen=True)
class _EvidenceBinding:
    context: ToolResultContext
    ref: dict[str, Any]
    ref_index: int


class _ClaimValidationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CompiledEvidenceAnswer:
    def __init__(
        self,
        *,
        answer: str,
        claims: list[StructuredClaim],
        citations: list[ChatCitation],
        warnings: list[str],
        insufficient_evidence: bool,
    ) -> None:
        self.answer = answer
        self.claims = claims
        self.citations = citations
        self.warnings = warnings
        self.insufficient_evidence = insufficient_evidence


class EvidenceCompiler:
    def __init__(
        self,
        *,
        max_answer_chars: int,
        max_claims: int = 16,
        max_evidence_ids_per_claim: int = 8,
        max_structured_facts_per_claim: int = 12,
        comparison_policy: EvidenceComparisonPolicy | None = None,
    ) -> None:
        self.max_answer_chars = max_answer_chars
        self.max_claims = max_claims
        self.max_evidence_ids_per_claim = max_evidence_ids_per_claim
        self.max_structured_facts_per_claim = max_structured_facts_per_claim
        self.comparison_policy = comparison_policy or EvidenceComparisonPolicy()

    def compile(
        self,
        *,
        final_text: str,
        tool_results: list[ToolResultContext],
        inherited_warnings: list[str],
    ) -> CompiledEvidenceAnswer:
        draft = self._parse_draft(final_text)
        evidence = _evidence_map(tool_results)
        warnings = [*inherited_warnings, *draft.warnings]

        if draft.claims is None:
            for evidence_id in draft.evidence_ids:
                binding = evidence.get(evidence_id)
                if binding is None:
                    warnings.append("UNVERIFIED_CITATION")
                elif binding.ref.get("quality_status") == "ERROR":
                    warnings.append("EVIDENCE_QUALITY_ERROR")
            if draft.evidence_ids or not draft.needs_clarification:
                warnings.append("LEGACY_DRAFT_WITHOUT_CLAIMS")
            return self._insufficient(draft.answer, warnings, draft.needs_clarification)
        if len(draft.claims) > self.max_claims:
            raise AgentChatError(
                "LLM_OUTPUT_LIMIT_EXCEEDED",
                "LLM response exceeds the configured claim limit",
                status_code=502,
            )

        verified: list[StructuredClaim] = []
        bound_evidence_ids: list[str] = []
        rejected = False
        seen_claim_ids: set[str] = set()
        for claim in draft.claims:
            if claim.claim_id in seen_claim_ids:
                warnings.append(f"CLAIM_REJECTED:{claim.claim_id}:DUPLICATE_CLAIM_ID")
                rejected = True
                continue
            seen_claim_ids.add(claim.claim_id)
            try:
                checked, policy_warnings = self._validate_claim(claim, evidence)
            except _ClaimValidationError as exc:
                warnings.append(f"CLAIM_REJECTED:{claim.claim_id}:{exc.code}")
                rejected = True
                continue
            verified.append(checked)
            bound_evidence_ids.extend(checked.evidence_ids)
            warnings.extend(policy_warnings)

        unbound = set(draft.evidence_ids) - set(bound_evidence_ids)
        if unbound:
            warnings.append("UNBOUND_TOP_LEVEL_CITATION")

        if rejected or (draft.claims and not verified):
            return self._insufficient(draft.answer, warnings, False)
        if not verified:
            return self._insufficient(
                draft.answer,
                warnings,
                draft.needs_clarification,
            )

        citations = _citations(bound_evidence_ids, evidence)
        marker_by_evidence = {item.evidence_id: item.marker for item in citations}
        answer = _answer_with_claim_markers(
            "以下结论已通过只读工具证据逐项校验。",
            verified,
            marker_by_evidence,
        )
        if len(answer) > self.max_answer_chars:
            raise AgentChatError(
                "LLM_OUTPUT_LIMIT_EXCEEDED",
                "LLM answer exceeds the configured character limit",
                status_code=502,
            )
        return CompiledEvidenceAnswer(
            answer=answer,
            claims=verified,
            citations=citations,
            warnings=list(dict.fromkeys(warnings)),
            insufficient_evidence=False,
        )

    def _validate_claim(
        self,
        claim: StructuredClaim,
        evidence: dict[str, _EvidenceBinding],
    ) -> tuple[StructuredClaim, list[str]]:
        if not claim.evidence_ids:
            raise _ClaimValidationError("MISSING_EVIDENCE")
        if len(claim.evidence_ids) > self.max_evidence_ids_per_claim:
            raise _ClaimValidationError("EVIDENCE_LIMIT_EXCEEDED")
        if len(claim.structured_facts) > self.max_structured_facts_per_claim:
            raise _ClaimValidationError("STRUCTURED_FACT_LIMIT_EXCEEDED")
        bindings = []
        for evidence_id in dict.fromkeys(claim.evidence_ids):
            binding = evidence.get(evidence_id)
            if binding is None:
                raise _ClaimValidationError("UNKNOWN_EVIDENCE_ID")
            if binding.ref.get("quality_status") == "ERROR":
                raise _ClaimValidationError("EVIDENCE_QUALITY_ERROR")
            bindings.append(binding)

        if claim.claim_type in {"FACT", "COMPARISON"} and not claim.structured_facts:
            raise _ClaimValidationError("MISSING_STRUCTURED_FACT")
        fact_contexts = [
            self._validate_fact(fact, bindings) for fact in claim.structured_facts
        ]
        try:
            policy_warnings = self.comparison_policy.evaluate(claim, fact_contexts)
        except ComparisonPolicyError as exc:
            raise _ClaimValidationError("COMPARISON_INCOMPATIBLE") from exc

        quality = (
            "WARNING"
            if claim.claim_type == "INFERENCE"
            or any(binding.ref.get("quality_status") != "PASS" for binding in bindings)
            else "PASS"
        )
        return claim.model_copy(
            update={
                "quality_status": quality,
                "text": _verified_claim_text(claim),
            }
        ), policy_warnings

    @staticmethod
    def _validate_fact(
        fact: StructuredFact,
        bindings: list[_EvidenceBinding],
    ) -> ComparisonFactContext:
        failures: list[str] = []
        for binding in bindings:
            try:
                return _validate_fact_binding(fact, binding)
            except _ClaimValidationError as exc:
                failures.append(exc.code)
        priority = (
            "VALUE_MISMATCH",
            "ENTITY_MISMATCH",
            "TRADE_DATE_MISMATCH",
            "UNIT_MISMATCH",
            "UNCONTROLLED_FIELD_PATH",
            "EVIDENCE_RECORD_MISMATCH",
        )
        for code in priority:
            if code in failures:
                raise _ClaimValidationError(code)
        raise _ClaimValidationError(failures[0] if failures else "MISSING_EVIDENCE")

    def _insufficient(
        self,
        draft_answer: str,
        warnings: list[str],
        preserve_answer: bool,
    ) -> CompiledEvidenceAnswer:
        warnings.append("INSUFFICIENT_EVIDENCE")
        answer = (
            draft_answer
            if preserve_answer
            else "现有只读工具没有提供足够、可逐项验证的证据，无法形成数据结论。"
        )
        if len(answer) > self.max_answer_chars:
            raise AgentChatError(
                "LLM_OUTPUT_LIMIT_EXCEEDED",
                "LLM answer exceeds the configured character limit",
                status_code=502,
            )
        return CompiledEvidenceAnswer(
            answer=answer,
            claims=[],
            citations=[],
            warnings=list(dict.fromkeys(warnings)),
            insufficient_evidence=True,
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


def _evidence_map(tool_results: list[ToolResultContext]) -> dict[str, _EvidenceBinding]:
    result: dict[str, _EvidenceBinding] = {}
    for context in tool_results:
        refs = context.payload.get("evidence")
        if not isinstance(refs, list):
            continue
        for index, ref in enumerate(refs):
            if not isinstance(ref, dict) or not isinstance(ref.get("evidence_id"), str):
                continue
            result.setdefault(
                ref["evidence_id"],
                _EvidenceBinding(context=context, ref=ref, ref_index=index),
            )
    return result


def _validate_fact_binding(
    fact: StructuredFact,
    binding: _EvidenceBinding,
) -> ComparisonFactContext:
    tool_name = binding.context.tool_name
    if not any(
        fnmatchcase(fact.path, pattern) for pattern in _ALLOWED_PATHS.get(tool_name, ())
    ):
        raise _ClaimValidationError("UNCONTROLLED_FIELD_PATH")
    records = binding.context.payload.get("records")
    if not isinstance(records, list):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    record_index = int(fact.path.split(".")[1])
    refs = binding.context.payload.get("evidence")
    if (
        isinstance(refs, list)
        and len(records) > 1
        and len(refs) == len(records)
        and binding.ref_index != record_index
    ):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    if str(binding.ref.get("entity_id")) != fact.entity:
        raise _ClaimValidationError("ENTITY_MISMATCH")
    evidence_date = binding.ref.get("trade_date") or binding.context.payload.get(
        "as_of_date"
    )
    if str(evidence_date) != fact.trade_date.isoformat():
        raise _ClaimValidationError("TRADE_DATE_MISMATCH")
    actual = _resolve_path(binding.context.payload, fact.path)
    if tool_name == "data.coverage":
        parts = fact.path.split(".")
        if len(parts) >= 5 and parts[2] == "dataset_coverage":
            dataset = _resolve_path(
                binding.context.payload,
                f"records.{parts[1]}.dataset_coverage.{parts[3]}.dataset",
                allow_text=True,
            )
            if str(dataset) != fact.entity:
                raise _ClaimValidationError("ENTITY_MISMATCH")
    _compare_value(actual, fact.value, fact.unit, fact.path)
    identity = binding.context.payload.get("identity")
    return ComparisonFactContext(
        tool_name=tool_name,
        entity=fact.entity,
        trade_date=fact.trade_date.isoformat(),
        path=fact.path,
        unit=fact.unit,
        sample_role=fact.sample_role,
        evidence=binding.ref,
        identity=identity if isinstance(identity, dict) else {},
    )


def _resolve_path(
    payload: dict[str, Any],
    path: str,
    *,
    allow_text: bool = False,
) -> Any:
    value: Any = payload
    try:
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH") from exc
    if value is None or isinstance(value, (dict, list, bool)):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    if not allow_text and isinstance(value, str) and not _looks_numeric_or_date(value):
        raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
    return value


def _compare_value(actual: Any, claimed: Any, unit: str, path: str) -> None:
    if unit not in _allowed_units(path):
        raise _ClaimValidationError("UNIT_MISMATCH")
    if unit == "date":
        actual_date = actual.isoformat() if isinstance(actual, date) else str(actual)
        if actual_date != str(claimed):
            raise _ClaimValidationError("VALUE_MISMATCH")
        return
    try:
        actual_decimal = Decimal(str(actual))
        claimed_decimal = Decimal(str(claimed))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _ClaimValidationError("VALUE_MISMATCH") from exc
    if unit == "percent":
        actual_decimal *= Decimal("100")
    if actual_decimal.normalize() != claimed_decimal.normalize():
        raise _ClaimValidationError("VALUE_MISMATCH")


def _allowed_units(path: str) -> set[str]:
    leaf = path.split(".")[-1]
    if leaf.endswith("date"):
        return {"date"}
    if leaf.endswith("rank") or leaf == "rank_change":
        return {"rank"}
    if any(token in leaf for token in ("count", "rows", "days")):
        return {"count"}
    if any(
        token in leaf for token in ("return", "drawdown", "rate", "coverage", "ratio")
    ):
        return {"decimal", "ratio", "percent"}
    if any(token in leaf for token in ("cash", "assets", "amount", "cost", "turnover")):
        return {"currency", "decimal"}
    if "nav" in leaf:
        return {"nav", "decimal"}
    if "score" in leaf or "momentum" in leaf:
        return {"score", "decimal"}
    return {"decimal"}


def _citations(
    evidence_ids: list[str],
    evidence: dict[str, _EvidenceBinding],
) -> list[ChatCitation]:
    citations: list[ChatCitation] = []
    for evidence_id in dict.fromkeys(evidence_ids):
        binding = evidence[evidence_id]
        ref = binding.ref
        citations.append(
            ChatCitation(
                marker=f"E{len(citations) + 1}",
                evidence_id=evidence_id,
                evidence_version=ref.get("evidence_version", "v1"),
                tool_name=binding.context.tool_name,
                entity_id=str(ref.get("entity_id", "unknown")),
                as_of_date=(
                    ref.get("trade_date")
                    or binding.context.payload.get("as_of_date")
                ),
                report_id=ref.get("report_id"),
                calc_run_id=ref.get("calc_run_id"),
                content_hash=ref.get("content_hash"),
            )
        )
    return citations


def _answer_with_claim_markers(
    answer: str,
    claims: list[StructuredClaim],
    marker_by_evidence: dict[str, str],
) -> str:
    lines = [answer, "", "证据声明："]
    labels = {"FACT": "事实", "INFERENCE": "推断", "COMPARISON": "比较"}
    for claim in claims:
        markers = " ".join(
            f"[{marker_by_evidence[evidence_id]}]"
            for evidence_id in dict.fromkeys(claim.evidence_ids)
        )
        lines.append(f"- {labels[claim.claim_type]} {claim.claim_id}：{claim.text} {markers}")
    return "\n".join(lines)


def _verified_claim_text(claim: StructuredClaim) -> str:
    if claim.claim_type == "INFERENCE":
        return "该结论是基于所列证据的推断，不是确定性事实或收益承诺。"
    facts = "; ".join(
        f"{fact.entity} {fact.path}={fact.value} {fact.unit} ({fact.trade_date.isoformat()})"
        for fact in claim.structured_facts
    )
    if claim.claim_type == "COMPARISON":
        return f"已验证比较所使用的独立事实：{facts}。"
    return f"已验证事实：{facts}。"


def _looks_numeric_or_date(value: str) -> bool:
    try:
        Decimal(value)
        return True
    except InvalidOperation:
        pass
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False
