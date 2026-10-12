from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.agent.report import ReportSourceContract, ResearchReportSnapshot
from app.services.agent.chat.comparison_policy import COMPARISON_POLICY_VERSION
from app.services.agent.report.canonical import decimal_text


def compare_report_snapshots(
    left: ResearchReportSnapshot,
    right: ResearchReportSnapshot,
    *,
    max_facts: int,
    left_contract: ReportSourceContract | None = None,
    right_contract: ReportSourceContract | None = None,
) -> tuple[str, list[str], dict[str, Any]]:
    reasons: list[str] = []
    state = "COMPARABLE"
    if left.report_type != right.report_type:
        state = "INCOMPATIBLE"
        reasons.append("REPORT_TYPE_MISMATCH")
    if left_contract is not None and right_contract is not None:
        if (
            left_contract.report_version != right_contract.report_version
            or left_contract.comparison_policy_version
            != right_contract.comparison_policy_version
            or left_contract.evidence_versions != right_contract.evidence_versions
        ):
            state = "INCOMPATIBLE"
            reasons.append("SOURCE_CONTRACT_VERSION_MISMATCH")
        elif (
            state == "COMPARABLE"
            and left_contract.tool_names != right_contract.tool_names
        ):
            state = "CONTEXT_REQUIRED"
            reasons.append("SOURCE_TOOL_SET_MISMATCH")
        if "EXACT_M14_BUNDLE_NOT_ARCHIVED" in {
            *left_contract.limitations,
            *right_contract.limitations,
        }:
            state = "INCOMPATIBLE"
            reasons.append("EXACT_M14_BUNDLE_REQUIRED")
        left_identity = _identity_signatures(left_contract)
        right_identity = _identity_signatures(right_contract)
        if left_identity is None or right_identity is None:
            state = "INCOMPATIBLE"
            reasons.append("CALCULATION_IDENTITY_MISSING")
        elif left_identity != right_identity:
            state = "INCOMPATIBLE"
            reasons.append("CALCULATION_IDENTITY_MISMATCH")

    claim_states = {
        claim.comparison_state
        for claim in [*left.claims, *right.claims]
        if claim.comparison_state is not None
    }
    if "INCOMPATIBLE" in claim_states:
        state = "INCOMPATIBLE"
        reasons.append("SOURCE_COMPARISON_INCOMPATIBLE")
    elif state == "COMPARABLE" and (
        "CONTEXT_REQUIRED" in claim_states
        or _has_train_oos(left)
        or _has_train_oos(right)
    ):
        state = "CONTEXT_REQUIRED"
        reasons.append("SOURCE_CONTEXT_REQUIRED")
    if state == "COMPARABLE" and left.as_of_date != right.as_of_date:
        state = "CONTEXT_REQUIRED"
        reasons.append("AS_OF_DATE_MISMATCH")

    left_facts = _fact_map(left)
    right_facts = _fact_map(right)
    shared = sorted(set(left_facts) & set(right_facts))
    if not shared:
        state = "INCOMPATIBLE"
        reasons.append("NO_COMMON_METRICS")
    rows: list[dict[str, Any]] = []
    for key in shared[:max_facts]:
        left_value = left_facts[key]
        right_value = right_facts[key]
        row: dict[str, Any] = {
            "metric_key": key,
            "left": left_value,
            "right": right_value,
        }
        if state == "COMPARABLE":
            delta = _delta(left_value, right_value)
            if delta is not None:
                row["delta"] = delta
        rows.append(row)
    if len(shared) > max_facts:
        reasons.append("COMPARISON_FACTS_TRUNCATED")
    return (
        state,
        list(dict.fromkeys(reasons)),
        {
            "policy_version": COMPARISON_POLICY_VERSION,
            "state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
            "facts": rows,
            "delta_policy": "ABSOLUTE_DECIMAL" if state == "COMPARABLE" else "DISABLED",
        },
    )


def _fact_map(snapshot: ResearchReportSnapshot) -> dict[str, str]:
    result: dict[str, str] = {}
    for claim in snapshot.claims:
        for fact in claim.structured_facts:
            key = "|".join(
                (
                    fact.path.split(".")[-1],
                    fact.unit,
                )
            )
            result.setdefault(key, str(fact.value))
    return result


def _has_train_oos(snapshot: ResearchReportSnapshot) -> bool:
    roles = {
        fact.sample_role
        for claim in snapshot.claims
        for fact in claim.structured_facts
    }
    return bool(roles & {"TRAIN", "OOS"})


def _delta(left: str, right: str) -> str | None:
    try:
        return decimal_text(Decimal(right) - Decimal(left))
    except (InvalidOperation, ValueError):
        return None


def _identity_signatures(
    contract: ReportSourceContract,
) -> set[tuple[str, str, str, str, str]] | None:
    signatures: set[tuple[str, str, str, str, str]] = set()
    for identity in contract.evidence_identities:
        version = identity.calc_version or identity.algo_version
        if not version or not identity.config_hash:
            return None
        signatures.add(
            (
                identity.tool_name,
                identity.evidence_version,
                identity.calc_version or "",
                identity.algo_version or "",
                identity.config_hash,
            )
        )
    return signatures or None
