from __future__ import annotations

from dataclasses import dataclass

from app.domain.agent.report import ReportSourceContract
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.metric_identity import FactCandidate

REPORT_COMPARISON_POLICY_VERSION = "m16.4.1-report-comparison-v2"


def contract_signature(contract: ReportSourceContract) -> str:
    data = contract.model_dump(mode="json")
    data["evidence_identities"] = sorted(data["evidence_identities"], key=canonical_hash)
    for field in ("tool_names", "evidence_versions", "limitations"):
        data[field] = sorted(data[field])
    return canonical_hash(data)


@dataclass(frozen=True)
class PairDecision:
    state: str
    reasons: tuple[str, ...] = ()


class ReportComparisonPolicy:
    """Only frozen contracts grant permission; an intent never supplies evidence."""

    @staticmethod
    def classify(left: list[FactCandidate], right: list[FactCandidate], intent: str) -> str:
        if intent != "AUTO":
            return intent
        facts = [*left, *right]
        roles = {item.descriptor.sample_role for item in facts}
        if {"TRAIN", "OOS"} <= roles:
            return "TRAIN_VS_OOS"
        if facts and all(item.descriptor.entity_kind == "backtest_run" for item in facts):
            if {item.descriptor.entity_id for item in left} != {
                item.descriptor.entity_id for item in right
            }:
                return "INDEPENDENT_BACKTESTS"
        if {item.descriptor for item in left} & {item.descriptor for item in right}:
            return "SAME_ENTITY_OVER_TIME"
        if facts and len({item.trade_date for item in facts}) == 1:
            return "CROSS_ENTITY_SAME_DATE"
        return "AUTO"

    @staticmethod
    def evaluate(
        left: FactCandidate,
        right: FactCandidate,
        intent: str,
        left_contract: ReportSourceContract | None,
        right_contract: ReportSourceContract | None,
    ) -> PairDecision:
        if intent == "TRAIN_VS_OOS":
            return PairDecision("INCOMPATIBLE", ("FROZEN_M15_WINDOW_LINEAGE_REQUIRED",))
        if intent == "INDEPENDENT_BACKTESTS" or left.descriptor.entity_kind == "backtest_run":
            # CLAIM_SNAPSHOT_ONLY has no costs/accounting/benchmark/date-set Bundle.
            return PairDecision("INCOMPATIBLE", ("EXACT_M14_BUNDLE_REQUIRED",))
        if left_contract is None or right_contract is None:
            return PairDecision("INCOMPATIBLE", ("SOURCE_CONTRACT_MISSING",))
        if (left_contract.report_version, left_contract.comparison_policy_version) != (
            right_contract.report_version,
            right_contract.comparison_policy_version,
        ):
            return PairDecision("INCOMPATIBLE", ("SOURCE_CONTRACT_VERSION_MISMATCH",))
        if left.descriptor != right.descriptor:
            return PairDecision("INCOMPATIBLE", ("METRIC_IDENTITY_MISMATCH",))
        a, b = left.citation, right.citation
        if not all(
            (
                a.evidence_version == "v2",
                b.evidence_version == "v2",
                a.calc_version or a.algo_version,
                b.calc_version or b.algo_version,
                a.config_hash,
                b.config_hash,
                a.source_hash or a.content_hash,
                b.source_hash or b.content_hash,
            )
        ):
            return PairDecision("INCOMPATIBLE", ("CALCULATION_IDENTITY_MISSING",))
        if (a.tool_name, a.evidence_version, a.calc_version, a.algo_version, a.config_hash) != (
            b.tool_name,
            b.evidence_version,
            b.calc_version,
            b.algo_version,
            b.config_hash,
        ):
            return PairDecision("INCOMPATIBLE", ("CALCULATION_IDENTITY_MISMATCH",))
        reasons: list[str] = []
        if left.trade_date != right.trade_date:
            reasons.append("AS_OF_DATE_MISMATCH")
        if a.source_hash != b.source_hash:
            reasons.append("SOURCE_HASH_CHANGED")
        if not a.source_hash and not b.source_hash and a.content_hash != b.content_hash:
            reasons.append("SOURCE_CONTENT_HASH_CHANGED")
        if left.descriptor.sample_role in {"TRAIN", "OOS", "UNKNOWN"}:
            reasons.append("SAMPLE_CONTEXT_REQUIRED")
        if intent == "CROSS_ENTITY_SAME_DATE":
            reasons.append("EXPLICIT_ENTITY_PAIR_MAPPING_REQUIRED")
        elif intent == "AUTO":
            reasons.append("COMPARISON_INTENT_AMBIGUOUS")
        return (
            PairDecision("CONTEXT_REQUIRED", tuple(reasons))
            if reasons
            else PairDecision("COMPARABLE")
        )
