from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.agent.chat import LineageDecision, StructuredClaim
from app.services.agent.chat.comparison_contract import (
    BacktestComparisonContractResolver,
)
from app.services.agent.chat.lineage import ExperimentLineageResolver

COMPARISON_POLICY_VERSION = "m16.2.2-comparison-v1"


class ComparisonPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ComparisonFactContext:
    tool_name: str
    entity: str
    trade_date: str
    path: str
    unit: str
    sample_role: str
    evidence: dict[str, Any]
    identity: dict[str, Any]


@dataclass(frozen=True)
class ComparisonEvidenceContext:
    tool_name: str
    evidence: dict[str, Any]
    identity: dict[str, Any]


@dataclass(frozen=True)
class ComparisonPolicyDecision:
    state: str
    reason_codes: tuple[str, ...] = ()
    lineage_decision: LineageDecision | None = None
    policy_version: str = COMPARISON_POLICY_VERSION


class EvidenceComparisonPolicy:
    """Deterministic compatibility gate; provider prose cannot override it."""

    def __init__(
        self,
        *,
        lineage_resolver: ExperimentLineageResolver | None = None,
        contract_resolver: BacktestComparisonContractResolver | None = None,
    ) -> None:
        self.lineage_resolver = lineage_resolver
        self.contract_resolver = contract_resolver

    def evaluate(
        self,
        claim: StructuredClaim,
        facts: list[ComparisonFactContext],
        evidence: list[ComparisonEvidenceContext],
    ) -> ComparisonPolicyDecision:
        if claim.claim_type != "COMPARISON":
            return ComparisonPolicyDecision("COMPARABLE")
        if len(facts) < 2:
            return _incompatible("COMPARISON_REQUIRES_TWO_FACTS")
        try:
            method = getattr(self, f"_validate_{claim.comparison_type.lower()}")
            return method(facts, evidence)
        except ComparisonPolicyError as exc:
            return _incompatible(str(exc))

    @staticmethod
    def _validate_same_date_ranking(
        facts: list[ComparisonFactContext],
        evidence: list[ComparisonEvidenceContext],
    ) -> ComparisonPolicyDecision:
        del evidence
        if len({fact.trade_date for fact in facts}) != 1:
            raise ComparisonPolicyError("SAME_DATE_RANKING_DATE_MISMATCH")
        if len({fact.entity for fact in facts}) < 2:
            raise ComparisonPolicyError("SAME_DATE_RANKING_DISTINCT_ENTITY_REQUIRED")
        if len({fact.tool_name for fact in facts}) != 1:
            raise ComparisonPolicyError("SAME_DATE_RANKING_TOOL_MISMATCH")
        _require_same_units_and_leaf_path(facts)
        _require_same_identity(facts, include_source_hash=True)
        return ComparisonPolicyDecision("COMPARABLE")

    @staticmethod
    def _validate_entity_over_time(
        facts: list[ComparisonFactContext],
        evidence: list[ComparisonEvidenceContext],
    ) -> ComparisonPolicyDecision:
        del evidence
        if len({fact.entity for fact in facts}) != 1:
            raise ComparisonPolicyError("ENTITY_OVER_TIME_ENTITY_MISMATCH")
        if len({fact.trade_date for fact in facts}) < 2:
            raise ComparisonPolicyError("ENTITY_OVER_TIME_DISTINCT_DATE_REQUIRED")
        if len({fact.tool_name for fact in facts}) != 1:
            raise ComparisonPolicyError("ENTITY_OVER_TIME_TOOL_MISMATCH")
        _require_same_units_and_leaf_path(facts)
        _require_same_identity(facts, include_source_hash=False)
        return ComparisonPolicyDecision(
            "CONTEXT_REQUIRED",
            ("ENTITY_OVER_TIME",),
        )

    def _validate_independent_backtests(
        self,
        facts: list[ComparisonFactContext],
        evidence: list[ComparisonEvidenceContext],
    ) -> ComparisonPolicyDecision:
        del evidence
        if len({fact.entity for fact in facts}) < 2:
            raise ComparisonPolicyError("INDEPENDENT_BACKTEST_DISTINCT_RUN_REQUIRED")
        _require_same_units_and_leaf_path(facts)
        if self.contract_resolver is None:
            return _incompatible("COMPARISON_CONTRACT_RESOLVER_UNAVAILABLE")
        decision = self.contract_resolver.resolve(facts)
        return ComparisonPolicyDecision(
            decision.state,
            decision.reason_codes,
            policy_version=decision.policy_version,
        )

    def _validate_train_vs_oos(
        self,
        facts: list[ComparisonFactContext],
        evidence: list[ComparisonEvidenceContext],
    ) -> ComparisonPolicyDecision:
        roles = {fact.sample_role for fact in facts}
        if roles != {"TRAIN", "OOS"}:
            raise ComparisonPolicyError("TRAIN_AND_OOS_ROLES_REQUIRED")
        _require_same_units_and_leaf_path(facts)
        if self.lineage_resolver is None:
            return _incompatible("LINEAGE_RESOLVER_UNAVAILABLE")
        lineage = self.lineage_resolver.resolve_train_oos(facts, evidence)
        if lineage.status != "VERIFIED":
            return ComparisonPolicyDecision(
                "INCOMPATIBLE",
                tuple(lineage.reason_codes),
                lineage_decision=lineage,
            )
        return ComparisonPolicyDecision(
            "CONTEXT_REQUIRED",
            ("TRAIN_OOS_DISTINCT_SAMPLE_WINDOWS",),
            lineage_decision=lineage,
        )


def _require_same_units_and_leaf_path(facts: list[ComparisonFactContext]) -> None:
    if len({fact.unit for fact in facts}) != 1:
        raise ComparisonPolicyError("METRIC_UNIT_MISMATCH")
    if len({fact.path.split(".")[-1] for fact in facts}) != 1:
        raise ComparisonPolicyError("METRIC_FIELD_MISMATCH")


def _require_same_identity(
    facts: list[ComparisonFactContext],
    *,
    include_source_hash: bool,
) -> None:
    required_keys = ("calc_version", "config_hash")
    optional_keys = ("algo_version",)
    signatures = {
        tuple(
            fact.evidence.get(key) or fact.identity.get(key)
            for key in (*required_keys, *optional_keys)
        )
        for fact in facts
    }
    signature = next(iter(signatures))
    if len(signatures) != 1 or any(
        signature[index] is None for index in range(len(required_keys))
    ):
        raise ComparisonPolicyError("CALCULATION_IDENTITY_MISMATCH")
    if include_source_hash:
        source_hashes = {
            fact.evidence.get("source_hash") or fact.identity.get("source_hash")
            for fact in facts
        }
        source_hashes.discard(None)
        if len(source_hashes) > 1:
            raise ComparisonPolicyError("SOURCE_IDENTITY_MISMATCH")


def _incompatible(reason_code: str) -> ComparisonPolicyDecision:
    return ComparisonPolicyDecision("INCOMPATIBLE", (reason_code,))
