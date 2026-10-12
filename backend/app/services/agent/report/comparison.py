from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, localcontext
from typing import Any

from app.domain.agent.report import ReportSourceContract, ResearchReportSnapshot
from app.services.agent.report.canonical import canonical_hash, decimal_text
from app.services.agent.report.comparison_policy import (
    REPORT_COMPARISON_POLICY_VERSION,
    ReportComparisonPolicy,
    contract_signature,
)
from app.services.agent.report.metric_identity import FactCandidate, collect_facts, pairing_key


def compare_report_snapshots(
    left: ResearchReportSnapshot,
    right: ResearchReportSnapshot,
    *,
    max_facts: int,
    left_contract: ReportSourceContract | None = None,
    right_contract: ReportSourceContract | None = None,
    comparison_intent: str = "AUTO",
) -> tuple[str, list[str], dict[str, Any]]:
    inventories = [collect_facts(left), collect_facts(right)]
    intent = ReportComparisonPolicy.classify(
        list(inventories[0].unique.values()),
        list(inventories[1].unique.values()),
        comparison_intent,
    )
    reasons = {issue["reason_code"] for inventory in inventories for issue in inventory.issues}
    if left.report_type != right.report_type:
        reasons.add("REPORT_TYPE_MISMATCH")
    if intent == "TRAIN_VS_OOS":
        reasons.add("FROZEN_M15_WINDOW_LINEAGE_REQUIRED")
    if (
        intent == "INDEPENDENT_BACKTESTS"
        or any(
            item.citation.tool_name in {"performance.summary", "backtest.summary"}
            for inventory in inventories
            for item in inventory.unique.values()
        )
        or any(
            contract is not None and "EXACT_M14_BUNDLE_NOT_ARCHIVED" in contract.limitations
            for contract in (left_contract, right_contract)
        )
    ):
        reasons.add("EXACT_M14_BUNDLE_REQUIRED")
    context_facts = {
        side: [item.view() for item in inventory.unique.values() if item.value_type != "NUMERIC"]
        for side, inventory in zip(("left", "right"), inventories, strict=True)
    }
    groups: list[dict[tuple[str, ...], list[FactCandidate]]] = []
    for inventory in inventories:
        grouped: dict[tuple[str, ...], list[FactCandidate]] = defaultdict(list)
        for key, item in inventory.unique.items():
            if item.value_type != "NUMERIC":
                continue
            grouped[pairing_key(key, intent)].append(item)
        groups.append(grouped)
    rows: list[dict[str, Any]] = []
    unmatched: dict[str, list[dict[str, Any]]] = {"left": [], "right": []}
    for key in sorted(set(groups[0]) | set(groups[1])):
        a, b = groups[0].get(key, []), groups[1].get(key, [])
        if len(a) > 1 or len(b) > 1:
            reasons.add("AMBIGUOUS_METRIC_IDENTITY")
            for side, items in (("left", a), ("right", b)):
                unmatched[side].extend(item.view() for item in items)
            continue
        if not a or not b:
            for side, items in (("left", a), ("right", b)):
                unmatched[side].extend(item.view() for item in items)
            continue
        decision = ReportComparisonPolicy.evaluate(
            a[0], b[0], intent, left_contract, right_contract
        )
        reasons.update(decision.reasons)
        rows.append(
            {
                "metric_key": "|".join(key),
                "left": a[0].value,
                "right": b[0].value,
                "left_fact": a[0].view(),
                "right_fact": b[0].view(),
                "pair_status": decision.state,
                "decision_reason_codes": list(decision.reasons),
            }
        )
    distinct_entities = not (
        {item.descriptor.entity_id for item in inventories[0].unique.values()}
        & {item.descriptor.entity_id for item in inventories[1].unique.values()}
    )
    side_by_side = (
        intent == "CROSS_ENTITY_SAME_DATE"
        and all(unmatched.values())
        and not rows
        and distinct_entities
    )
    if side_by_side:
        # No A/B pairing is inferred. Validate comparable *contexts* before showing parallel facts.
        left_items, right_items = (list(inventory.unique.values()) for inventory in inventories)
        if any(
            item.descriptor.sample_role in {"TRAIN", "OOS", "UNKNOWN"}
            for item in [*left_items, *right_items]
        ):
            reasons.add("SAMPLE_CONTEXT_REQUIRED")
        if left_contract is None or right_contract is None:
            reasons.add("SOURCE_CONTRACT_MISSING")
        elif (left_contract.report_version, left_contract.comparison_policy_version) != (
            right_contract.report_version,
            right_contract.comparison_policy_version,
        ):
            reasons.add("SOURCE_CONTRACT_VERSION_MISMATCH")
        for item in [*left_items, *right_items]:
            ref = item.citation
            if not (
                ref.evidence_version == "v2"
                and (ref.calc_version or ref.algo_version)
                and ref.config_hash
                and (ref.source_hash or ref.content_hash)
            ):
                reasons.add("CALCULATION_IDENTITY_MISSING")
        if {
            (
                item.descriptor.metric_id,
                item.descriptor.entity_kind,
                item.descriptor.unit,
                item.descriptor.sample_role,
                item.trade_date,
                item.citation.calc_version,
                item.citation.algo_version,
                item.citation.config_hash,
            )
            for item in left_items
        } != {
            (
                item.descriptor.metric_id,
                item.descriptor.entity_kind,
                item.descriptor.unit,
                item.descriptor.sample_role,
                item.trade_date,
                item.citation.calc_version,
                item.citation.algo_version,
                item.citation.config_hash,
            )
            for item in right_items
        }:
            reasons.add("METRIC_IDENTITY_MISMATCH")
        reasons.add("EXPLICIT_ENTITY_PAIR_MAPPING_REQUIRED")
        reasons.add("PAIR_MAPPING_NOT_PROVIDED")
    elif not rows and not any(context_facts.values()):
        reasons.add("NO_COMPARABLE_FACTS")
    elif not rows:
        reasons.add("CONTEXT_FACTS_ONLY")
    if any(unmatched.values()):
        reasons.add("UNMATCHED_METRICS")
    source_states = {
        claim.comparison_state for snapshot in (left, right) for claim in snapshot.claims
    }
    if "INCOMPATIBLE" in source_states:
        reasons.add("SOURCE_COMPARISON_INCOMPATIBLE")
    if "CONTEXT_REQUIRED" in source_states:
        reasons.add("SOURCE_CONTEXT_REQUIRED")
    context_codes = {
        "AS_OF_DATE_MISMATCH",
        "SOURCE_HASH_CHANGED",
        "SOURCE_CONTENT_HASH_CHANGED",
        "SAMPLE_CONTEXT_REQUIRED",
        "SOURCE_CONTEXT_REQUIRED",
        "UNMATCHED_METRICS",
        "EXPLICIT_ENTITY_PAIR_MAPPING_REQUIRED",
        "COMPARISON_INTENT_AMBIGUOUS",
        "CONTEXT_FACTS_ONLY",
        "PAIR_MAPPING_NOT_PROVIDED",
    }
    state = (
        "INCOMPATIBLE"
        if reasons - context_codes
        else "CONTEXT_REQUIRED"
        if reasons
        else "COMPARABLE"
    )
    if (
        len(rows) + sum(map(len, unmatched.values())) + sum(map(len, context_facts.values()))
        > max_facts
    ):
        reasons.add("COMPARISON_FACTS_TRUNCATED")
        if state == "COMPARABLE":
            state = "CONTEXT_REQUIRED"
    # Both the global gate and each pair gate must grant permission independently.
    for row in rows:
        if state == "COMPARABLE" and row["pair_status"] == "COMPARABLE":
            with localcontext() as ctx:
                ctx.prec = 1000
                row["delta"] = decimal_text(Decimal(row["right"]) - Decimal(row["left"]))
            row["delta_semantics"] = "RIGHT_MINUS_LEFT_SAME_UNIT"
    remaining = max_facts - min(len(rows), max_facts)
    for side in ("left", "right"):
        unmatched[side] = sorted(unmatched[side], key=canonical_hash)[:remaining]
        remaining -= len(unmatched[side])
    for side in ("left", "right"):
        context_facts[side] = sorted(context_facts[side], key=canonical_hash)[:remaining]
        remaining -= len(context_facts[side])
    result = {
        "policy_version": REPORT_COMPARISON_POLICY_VERSION,
        "state": state,
        "comparison_intent": intent,
        "requested_intent": comparison_intent,
        "reason_codes": sorted(reasons),
        "facts": rows[:max_facts],
        "unmatched_facts": unmatched,
        "side_by_side_facts": unmatched if side_by_side else {"left": [], "right": []},
        "context_facts": context_facts,
        "ambiguous_facts": {"left": inventories[0].issues, "right": inventories[1].issues},
        "source_contract_hashes": {
            "left": contract_signature(left_contract) if left_contract else None,
            "right": contract_signature(right_contract) if right_contract else None,
        },
        "delta_policy": "ABSOLUTE_DECIMAL" if state == "COMPARABLE" else "DISABLED",
    }
    return state, sorted(reasons), result
