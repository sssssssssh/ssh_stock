from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from fnmatch import fnmatchcase
from typing import Any

from pydantic import ValidationError

from app.domain.agent.chat import (
    AnswerStatus,
    ChatCitation,
    RejectedClaim,
    ResearchNavigationContext,
    StructuredAnswerDraft,
    StructuredClaim,
    StructuredFact,
)
from app.domain.agent.chat_errors import AgentChatError
from app.services.agent.chat.comparison_policy import (
    ComparisonEvidenceContext,
    ComparisonFactContext,
    EvidenceComparisonPolicy,
)
from app.services.agent.chat.inference_policy import (
    InferencePolicy,
    InferencePolicyError,
)
from app.services.agent.chat.orchestrator import ToolResultContext
from app.services.agent.evidence import canonical_content_hash

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
    "walk_forward.window_lineage": (
        "records.*.window_no",
        "records.*.train_start",
        "records.*.train_end",
        "records.*.test_start",
        "records.*.test_end",
        "records.*.train_metrics.annualized_return",
        "records.*.train_metrics.max_drawdown_abs",
        "records.*.train_metrics.sharpe_ratio",
        "records.*.train_metrics.annualized_turnover",
        "records.*.oos_metrics.cumulative_return",
        "records.*.oos_metrics.annualized_return",
        "records.*.oos_metrics.max_drawdown_abs",
        "records.*.oos_metrics.sharpe_ratio",
        "records.*.oos_metrics.annualized_turnover",
        "records.*.oos_metrics.total_cost_to_initial_capital",
        "records.*.oos_metrics.win_rate",
        "records.*.oos_metrics.profit_factor",
        "records.*.degradation.return",
        "records.*.degradation.sharpe",
        "records.*.degradation.drawdown",
        "records.*.degradation.turnover",
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


def _rejected_claim(
    claim: StructuredClaim,
    reason_codes: list[str],
) -> RejectedClaim:
    return RejectedClaim(
        claim_id=claim.claim_id,
        claim_type=claim.claim_type,
        reason_codes=list(dict.fromkeys(reason_codes)) or ["CLAIM_REJECTED"],
        comparison_state=claim.comparison_state,
        policy_version=claim.policy_version,
    )


class CompiledEvidenceAnswer:
    def __init__(
        self,
        *,
        answer: str,
        claims: list[StructuredClaim],
        rejected_claims: list[RejectedClaim],
        citations: list[ChatCitation],
        warnings: list[str],
        answer_status: AnswerStatus,
        needs_clarification: bool,
    ) -> None:
        self.answer = answer
        self.claims = claims
        self.rejected_claims = rejected_claims
        self.citations = citations
        self.warnings = warnings
        self.answer_status = answer_status
        self.needs_clarification = needs_clarification

    @property
    def insufficient_evidence(self) -> bool:
        return self.answer_status != "COMPLETED"


class EvidenceCompiler:
    def __init__(
        self,
        *,
        max_answer_chars: int,
        max_claims: int = 16,
        max_evidence_ids_per_claim: int = 8,
        max_structured_facts_per_claim: int = 12,
        comparison_policy: EvidenceComparisonPolicy | None = None,
        inference_policy: InferencePolicy | None = None,
    ) -> None:
        self.max_answer_chars = max_answer_chars
        self.max_claims = max_claims
        self.max_evidence_ids_per_claim = max_evidence_ids_per_claim
        self.max_structured_facts_per_claim = max_structured_facts_per_claim
        self.comparison_policy = comparison_policy or EvidenceComparisonPolicy()
        self.inference_policy = inference_policy or InferencePolicy()

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

        accepted_by_id: dict[str, StructuredClaim] = {}
        rejected_by_id: dict[str, RejectedClaim] = {}
        rejected = False
        seen_claim_ids: set[str] = set()
        unique_claims: list[StructuredClaim] = []
        for claim in draft.claims:
            if claim.claim_id in seen_claim_ids:
                warnings.append(f"CLAIM_REJECTED:{claim.claim_id}:DUPLICATE_CLAIM_ID")
                rejected_by_id.setdefault(
                    claim.claim_id,
                    _rejected_claim(claim, ["DUPLICATE_CLAIM_ID"]),
                )
                rejected = True
                continue
            seen_claim_ids.add(claim.claim_id)
            unique_claims.append(claim)
        for claim in (item for item in unique_claims if item.claim_type != "INFERENCE"):
            try:
                checked, policy_warnings, accepted = self._validate_claim(
                    claim,
                    evidence,
                    accepted_by_id,
                )
            except _ClaimValidationError as exc:
                warnings.append(f"CLAIM_REJECTED:{claim.claim_id}:{exc.code}")
                rejected_by_id[claim.claim_id] = _rejected_claim(claim, [exc.code])
                rejected = True
                continue
            warnings.extend(policy_warnings)
            if accepted:
                accepted_by_id[checked.claim_id] = checked
            else:
                rejected_by_id[checked.claim_id] = _rejected_claim(
                    checked,
                    ["COMPARISON_INCOMPATIBLE", *checked.reason_codes],
                )
                warnings.append(f"CLAIM_REJECTED:{claim.claim_id}:COMPARISON_INCOMPATIBLE")
                warnings.extend(
                    f"CLAIM_REJECTED_REASON:{claim.claim_id}:{code}"
                    for code in checked.reason_codes
                )
                rejected = True
        for claim in (item for item in unique_claims if item.claim_type == "INFERENCE"):
            try:
                checked, policy_warnings, accepted = self._validate_claim(
                    claim,
                    evidence,
                    accepted_by_id,
                )
            except _ClaimValidationError as exc:
                warnings.append(f"CLAIM_REJECTED:{claim.claim_id}:{exc.code}")
                rejected_by_id[claim.claim_id] = _rejected_claim(claim, [exc.code])
                rejected = True
                continue
            warnings.extend(policy_warnings)
            if accepted:
                accepted_by_id[checked.claim_id] = checked
            else:
                rejected_by_id[checked.claim_id] = _rejected_claim(
                    checked,
                    checked.reason_codes or ["INFERENCE_REJECTED"],
                )
                rejected = True

        accepted = [
            accepted_by_id[claim.claim_id]
            for claim in unique_claims
            if claim.claim_id in accepted_by_id
        ]
        rejected_claims = [
            rejected_by_id[claim.claim_id]
            for claim in unique_claims
            if claim.claim_id in rejected_by_id
        ]
        bound_evidence_ids = [
            evidence_id for claim in accepted for evidence_id in claim.evidence_ids
        ]

        unbound = set(draft.evidence_ids) - set(bound_evidence_ids)
        if unbound:
            warnings.append("UNBOUND_TOP_LEVEL_CITATION")

        if not accepted:
            return self._insufficient(
                draft.answer,
                warnings,
                draft.needs_clarification,
                rejected_claims=rejected_claims,
            )

        citations = _citations(bound_evidence_ids, evidence)
        marker_by_evidence = {item.evidence_id: item.marker for item in citations}
        answer = _answer_with_claim_markers(
            (
                "以下仅保留通过只读工具证据校验的结论；其余比较或推断已被拒绝。"
                if rejected
                else "以下结论已通过只读工具证据逐项校验。"
            ),
            accepted,
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
            claims=accepted,
            rejected_claims=rejected_claims,
            citations=citations,
            warnings=list(dict.fromkeys(warnings)),
            answer_status="PARTIAL_VERIFIED" if rejected else "COMPLETED",
            needs_clarification=draft.needs_clarification,
        )

    def _validate_claim(
        self,
        claim: StructuredClaim,
        evidence: dict[str, _EvidenceBinding],
        verified_claims: dict[str, StructuredClaim],
    ) -> tuple[StructuredClaim, list[str], bool]:
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
        fact_contexts = [self._validate_fact(fact, bindings) for fact in claim.structured_facts]
        verified_refs = [
            f"{context.evidence['evidence_id']}:{fact.path}"
            for fact, context in zip(
                claim.structured_facts,
                fact_contexts,
                strict=True,
            )
        ]
        if claim.claim_type == "INFERENCE":
            try:
                inference = self.inference_policy.evaluate(claim, verified_claims)
            except InferencePolicyError as exc:
                raise _ClaimValidationError(exc.code) from exc
            return (
                claim.model_copy(
                    update={
                        "quality_status": "WARNING",
                        "text": inference.text,
                        "inference": inference.inference,
                        "reason_codes": list(inference.reason_codes),
                        "verified_fact_refs": list(inference.verified_fact_refs),
                        "policy_version": inference.policy_version,
                        "comparison_state": None,
                        "lineage_decision": None,
                    }
                ),
                [],
                True,
            )

        evidence_contexts = [
            ComparisonEvidenceContext(
                tool_name=binding.context.tool_name,
                evidence=binding.ref,
                identity=(
                    binding.context.payload.get("identity")
                    if isinstance(binding.context.payload.get("identity"), dict)
                    else {}
                ),
            )
            for binding in bindings
        ]
        decision = self.comparison_policy.evaluate(
            claim,
            fact_contexts,
            evidence_contexts,
        )
        policy_warnings = [
            f"COMPARISON_REQUIRES_CONTEXT:{code}"
            for code in decision.reason_codes
            if decision.state == "CONTEXT_REQUIRED"
        ]

        quality = (
            "WARNING"
            if decision.state == "CONTEXT_REQUIRED"
            or any(binding.ref.get("quality_status") != "PASS" for binding in bindings)
            else "PASS"
        )
        accepted = decision.state != "INCOMPATIBLE"
        checked = claim.model_copy(
            update={
                "quality_status": quality if accepted else "WARNING",
                "text": (
                    _verified_claim_text(claim)
                    if accepted
                    else "该比较因证据同源关系或统计口径不兼容而被拒绝。"
                ),
                "comparison_state": (decision.state if claim.claim_type == "COMPARISON" else None),
                "lineage_decision": decision.lineage_decision,
                "reason_codes": list(decision.reason_codes),
                "verified_fact_refs": verified_refs,
                "policy_version": decision.policy_version,
            }
        )
        return checked, policy_warnings, accepted

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
        rejected_claims: list[RejectedClaim] | None = None,
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
            rejected_claims=rejected_claims or [],
            citations=[],
            warnings=list(dict.fromkeys(warnings)),
            answer_status="INSUFFICIENT_EVIDENCE",
            needs_clarification=preserve_answer,
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
            previous = result.get(ref["evidence_id"])
            if previous is not None and canonical_content_hash(
                {
                    "tool": previous.context.tool_name,
                    "payload": previous.context.payload,
                    "ref": previous.ref,
                }
            ) != canonical_content_hash(
                {"tool": context.tool_name, "payload": context.payload, "ref": ref}
            ):
                raise AgentChatError(
                    "EVIDENCE_DUPLICATE_CONFLICT", "conflicting evidence identity", status_code=409
                )
            if previous is None:
                result[ref["evidence_id"]] = _EvidenceBinding(
                    context=context, ref=ref, ref_index=index
                )
    return result


def _validate_fact_binding(
    fact: StructuredFact,
    binding: _EvidenceBinding,
) -> ComparisonFactContext:
    tool_name = binding.context.tool_name
    if not any(fnmatchcase(fact.path, pattern) for pattern in _ALLOWED_PATHS.get(tool_name, ())):
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
    evidence_date = binding.ref.get("trade_date") or binding.context.payload.get("as_of_date")
    if str(evidence_date) != fact.trade_date.isoformat():
        raise _ClaimValidationError("TRADE_DATE_MISMATCH")
    actual = _resolve_path(binding.context.payload, fact.path)
    identity = binding.context.payload.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    if tool_name == "performance.summary":
        section = fact.path.split(".")[2]
        expected_report_id = identity.get(f"{section}_id")
        if section not in {"performance", "risk", "trade", "period"}:
            raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
        if expected_report_id is not None and str(binding.ref.get("report_id")) != str(
            expected_report_id
        ):
            raise _ClaimValidationError("EVIDENCE_RECORD_MISMATCH")
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
    return ComparisonFactContext(
        tool_name=tool_name,
        entity=fact.entity,
        trade_date=fact.trade_date.isoformat(),
        path=fact.path,
        unit=fact.unit,
        sample_role=fact.sample_role,
        evidence=binding.ref,
        identity=identity,
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
    if any(token in leaf for token in ("return", "drawdown", "rate", "coverage", "ratio")):
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
                as_of_date=(ref.get("trade_date") or binding.context.payload.get("as_of_date")),
                report_id=ref.get("report_id"),
                calc_run_id=ref.get("calc_run_id"),
                calc_version=ref.get("calc_version"),
                algo_version=ref.get("algo_version"),
                config_hash=ref.get("config_hash"),
                source_hash=ref.get("source_hash"),
                content_hash=ref.get("content_hash"),
                observed_at=ref.get("observed_at"),
                navigation=_navigation_context(binding),
            )
        )
    return citations


def _navigation_context(
    binding: _EvidenceBinding,
) -> ResearchNavigationContext | None:
    tool_name = binding.context.tool_name
    ref = binding.ref
    entity_id = str(ref.get("entity_id", ""))
    trade_date = ref.get("trade_date") or binding.context.payload.get("as_of_date")
    if tool_name in {"backtest.summary", "performance.summary"}:
        run_id = ref.get("calc_run_id") or entity_id
        if not run_id:
            return None
        return ResearchNavigationContext(
            view="analytics",
            run_id=str(run_id),
            trade_date=trade_date,
            source_tool=tool_name,
        )
    if tool_name == "sector.top":
        if not entity_id:
            return None
        return ResearchNavigationContext(
            view="long",
            sector_id=entity_id,
            trade_date=trade_date,
            source_tool=tool_name,
        )
    if tool_name == "opportunity.list":
        if not entity_id:
            return None
        return ResearchNavigationContext(
            view="long",
            ts_code=entity_id,
            trade_date=trade_date,
            source_tool=tool_name,
        )
    if tool_name == "walk_forward.window_lineage":
        identity = binding.context.payload.get("identity")
        records = binding.context.payload.get("records")
        record = (
            records[binding.ref_index]
            if isinstance(records, list)
            and binding.ref_index < len(records)
            and isinstance(records[binding.ref_index], dict)
            else {}
        )
        if not isinstance(identity, dict):
            return None
        study_id = identity.get("study_id")
        validation_id = identity.get("validation_id")
        window_no = record.get("window_no")
        if not study_id or not validation_id or not isinstance(window_no, int):
            return None
        return ResearchNavigationContext(
            view="walk_forward",
            study_id=str(study_id),
            validation_id=str(validation_id),
            window_no=window_no,
            trade_date=trade_date,
            source_tool=tool_name,
        )
    return None


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
