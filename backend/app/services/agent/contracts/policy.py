from decimal import Decimal, localcontext
from types import SimpleNamespace

from app.domain.walk_forward.metrics import window_degradation
from app.services.agent.chat.comparison_contract import compare_contracts
from app.services.agent.chat.fact_validation import _compare_value
from app.services.agent.contracts.canonical import contract_hash
from app.services.agent.contracts.semantics import endpoint_metrics, require, verify_m14
from app.services.agent.report.canonical import decimal_text
from app.services.agent.report.metric_identity import collect_facts

CONTRACT_COMPARISON_POLICY_VERSION = "m16.6-report-comparison-v4"


def _ready(verification):
    return verification is not None and all(
        verification.check.get(key, {}).get("status") == "VERIFIED"
        for key in ("archive_integrity", "frozen_fact_recheck", "contract_integrity")
    )


def _m14_for_fact(fact, verification):
    matches = []
    for row_id, body in verification.verified.items():
        row = verification.rows[row_id]
        if row.contract_kind != "M14_EXACT_BUNDLE" or row.subject_id != fact.descriptor.entity_id:
            continue
        if str(row.tool_result_archive_id) != verification.evidence_tool_ids.get(
            fact.citation.evidence_id
        ):
            continue
        if any(
            ref["evidence_id"] == fact.citation.evidence_id
            and ref["content_hash"] == fact.citation.content_hash
            and ref["report_id"] == fact.citation.report_id
            for ref in body["evidence"]
        ):
            matches.append((row, body))
    require(len(matches) == 1, "EXACT_FROZEN_M14_CONTRACT_REQUIRED")
    row, body = matches[0]
    require(fact.citation.calc_run_id == body["selected"]["run_id"])
    suffix = fact.descriptor.metric_id.split(":", 1)[1].split(".")
    value = body["record"]
    for part in suffix:
        value = value[part]
    _compare_value(value, fact.value, fact.descriptor.unit, "records.0." + ".".join(suffix))
    return row, body


def _contexts(left, right):
    return {
        side: [fact.view() for fact in inventory.unique.values() if fact.value_type != "NUMERIC"]
        for side, inventory in (("left", left), ("right", right))
    }


def _contract_refs(verification):
    if verification is None:
        return []
    refs = []
    for item in verification.check.get("results", []):
        body = verification.verified.get(item["contract_id"])
        source_ids = None
        if body is not None:
            source_ids = body.get("selected") or {
                "study_id": body["study"]["id"],
                "validation_id": body["validation"]["id"],
                "window_no": body["window"]["window_no"],
                "selected_trial_id": body["trial"]["id"],
            }
        refs.append({**item, "source_ids": source_ids})
    return refs


def compare_frozen_research(
    left,
    right,
    *,
    left_verification,
    right_verification,
    max_facts,
    comparison_intent,
    comparison_mode,
):
    inventories = [collect_facts(left), collect_facts(right)]
    result = {
        "policy_version": CONTRACT_COMPARISON_POLICY_VERSION,
        "comparison_intent": comparison_intent,
        "comparison_mode": comparison_mode,
        "max_facts": max_facts,
        "facts": [],
        "context_facts": _contexts(*inventories),
        "unmatched_facts": {
            side: [
                fact.view() for fact in inventory.unique.values() if fact.value_type == "NUMERIC"
            ]
            for side, inventory in zip(("left", "right"), inventories, strict=True)
        },
        "ambiguous_facts": {"left": inventories[0].issues, "right": inventories[1].issues},
        "contract_refs": {
            side: _contract_refs(value)
            for side, value in (("left", left_verification), ("right", right_verification))
        },
        "contract_check": {
            side: value.check if value else {"status": "UNVERIFIABLE"}
            for side, value in (("left", left_verification), ("right", right_verification))
        },
        "sample_context": {},
        "explain_reasons": [],
        "calculation_reproduced": False,
    }
    reasons = set()
    state = "CONTEXT_REQUIRED"
    if not (_ready(left_verification) and _ready(right_verification)):
        reasons.add("FROZEN_CONTRACT_RECHECK_REQUIRED")
    if any(inventory.issues for inventory in inventories):
        reasons.add("AMBIGUOUS_METRIC_IDENTITY")
    if left.report_type != right.report_type:
        reasons.add("REPORT_TYPE_MISMATCH")
    count = sum(len(inventory.unique) for inventory in inventories)
    if count > max_facts:
        reasons.add("COMPARISON_FACTS_TRUNCATED")
    if not reasons:
        try:
            if comparison_intent == "TRAIN_VS_OOS" and comparison_mode == "WINDOW_DEGRADATION":
                state, codes = _window_pairs(
                    result, inventories, left_verification, right_verification
                )
            elif comparison_intent == "INDEPENDENT_BACKTESTS" and comparison_mode in {
                "STRICT_SAME_SAMPLE",
                "DIFFERENT_ASSUMPTIONS",
            }:
                state, codes = _independent_pairs(
                    result, inventories, left_verification, right_verification, comparison_mode
                )
            else:
                state, codes = "CONTEXT_REQUIRED", ["EXPLICIT_COMPARISON_MODE_REQUIRED"]
            reasons.update(codes)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            reasons.add(getattr(exc, "code", "FROZEN_METRIC_BINDING_UNVERIFIABLE"))
            state = "INCOMPATIBLE"
    if any(
        claim.comparison_state in {"CONTEXT_REQUIRED", "INCOMPATIBLE"}
        for snapshot in (left, right)
        for claim in snapshot.claims
    ):
        reasons.add("SOURCE_COMPARISON_CONTEXT_REQUIRED")
    if reasons:
        state = (
            "INCOMPATIBLE"
            if state == "INCOMPATIBLE"
            or any(
                code in reasons
                for code in (
                    "AMBIGUOUS_METRIC_IDENTITY",
                    "REPORT_TYPE_MISMATCH",
                )
            )
            else "CONTEXT_REQUIRED"
        )
    allowed = state == "COMPARABLE" and not reasons and bool(result["facts"])
    for row in result["facts"]:
        row_allowed = allowed and row.get("pair_status") == "COMPARABLE" and row.get("formula")
        row["comparison_permission"] = {
            "allowed": bool(row_allowed),
            "reason_codes": [] if row_allowed else sorted(reasons),
        }
        if not row_allowed:
            row.pop("delta", None)
    result.update(
        {
            "state": state,
            "reason_codes": sorted(reasons),
            "comparison_permissions": {"allowed": allowed, "reason_codes": sorted(reasons)},
            "delta_policy": "AUTHORIZED_FROZEN_DECIMAL" if allowed else "DISABLED",
        }
    )
    result["facts"] = result["facts"][:max_facts]
    remaining = max_facts - len(result["facts"])
    for group in ("unmatched_facts", "context_facts"):
        for side in ("left", "right"):
            result[group][side] = result[group][side][:remaining]
            remaining -= len(result[group][side])
    return state, sorted(reasons), result


def _independent_pairs(result, inventories, left_verification, right_verification, mode):
    groups = []
    bundles = []
    for inventory, verification in zip(
        inventories, (left_verification, right_verification), strict=True
    ):
        group = {}
        selected = {}
        for fact in inventory.unique.values():
            if fact.value_type != "NUMERIC":
                continue
            require(
                fact.citation.tool_name == "performance.summary"
                and fact.descriptor.sample_role == "LIVE",
                "EXACT_M14_METRIC_REQUIRED",
            )
            key = (fact.descriptor.metric_id, fact.descriptor.unit)
            require(key not in group, "AMBIGUOUS_METRIC_IDENTITY")
            row, body = _m14_for_fact(fact, verification)
            selected[row.subject_id] = body
            group[key] = fact
        require(len(selected) == 1 and bool(group), "DISTINCT_SINGLE_RUNS_REQUIRED")
        groups.append(group)
        bundles.append(next(iter(selected.values())))
    require(
        bundles[0]["selected"]["run_id"] != bundles[1]["selected"]["run_id"],
        "DISTINCT_RUNS_REQUIRED",
    )
    contracts = [verify_m14(body) for body in bundles]
    decision = compare_contracts(contracts, metric_paths=[key[0] for key in groups[0]])
    codes = list(decision.reason_codes)
    if set(groups[0]) != set(groups[1]):
        codes.append("UNMATCHED_METRICS")
    differences = []
    for field in contracts[0].__dataclass_fields__:
        a, b = getattr(contracts[0], field), getattr(contracts[1], field)
        if a != b:
            differences.append({"field": field, "left": str(a), "right": str(b)})
    for field in ("algo_version", "opportunity_calc_version"):
        if bundles[0]["bundle_rows"]["run"][field] != bundles[1]["bundle_rows"]["run"][field]:
            codes.append(field.upper() + "_MISMATCH")
    if (contracts[0].benchmark_code, contracts[0].benchmark_source_hash) != (
        contracts[1].benchmark_code,
        contracts[1].benchmark_source_hash,
    ):
        codes.append("BENCHMARK_MISMATCH")
    if mode == "DIFFERENT_ASSUMPTIONS":
        codes.append("SENSITIVITY_CONTEXT_ONLY")
    result["explain_reasons"] = differences
    result["sample_context"] = {
        side: {
            "run_id": str(contract.run_id),
            "start_date": contract.start_date,
            "end_date": contract.end_date,
            "trade_days": contract.trade_days,
            "sample_role": "LIVE",
            "benchmark_code": contract.benchmark_code,
        }
        for side, contract in zip(("left", "right"), contracts, strict=True)
    }
    state = (
        decision.state
        if not codes
        else ("INCOMPATIBLE" if decision.state == "INCOMPATIBLE" else "CONTEXT_REQUIRED")
    )
    for key in sorted(set(groups[0]) & set(groups[1])):
        a, b = groups[0][key], groups[1][key]
        row = {
            "metric_key": "|".join(key),
            "left": a.value,
            "right": b.value,
            "left_fact": a.view(),
            "right_fact": b.view(),
            "pair_status": state,
            "decision_reason_codes": sorted(set(codes)),
            "formula": "RIGHT_MINUS_LEFT",
            "delta_semantics": "PERCENTAGE_POINT_DIFFERENCE"
            if key[1] == "percent"
            else "RIGHT_MINUS_LEFT_SAME_UNIT",
        }
        if state == "COMPARABLE":
            with localcontext() as context:
                context.prec = 1000
                row["delta"] = decimal_text(Decimal(b.value) - Decimal(a.value))
        result["facts"].append(row)
    result["unmatched_facts"] = {
        side: [fact.view() for key, fact in groups[index].items() if key not in groups[1 - index]]
        for index, side in enumerate(("left", "right"))
    }
    return state, codes


def _window_pairs(result, inventories, left_verification, right_verification):
    windows = []
    for verification in (left_verification, right_verification):
        selected = list(
            {
                contract_hash(body): body
                for row_id, body in verification.verified.items()
                if verification.rows[row_id].contract_kind == "M15_WINDOW_LINEAGE"
            }.values()
        )
        require(len(selected) == 1, "EXACT_SINGLE_WINDOW_REQUIRED")
        windows.append(selected[0])
    require(windows[0] == windows[1], "FROZEN_WINDOW_CONTRACT_MISMATCH")
    body = windows[0]
    endpoints = {}
    for ref in body["m14_contract_refs"]:
        matches = [
            candidate
            for row_id, candidate in left_verification.verified.items()
            if left_verification.rows[row_id].contract_kind == "M14_EXACT_BUNDLE"
            and left_verification.rows[row_id].subject_id == ref["subject_id"]
            and left_verification.rows[row_id].role == ref["role"]
        ]
        require(len(matches) == 1, "WINDOW_ENDPOINT_CONTRACT_UNVERIFIABLE")
        endpoints[ref["role"]] = matches[0]
    metrics = {role: endpoint_metrics(endpoint) for role, endpoint in endpoints.items()}
    degradation = window_degradation(
        SimpleNamespace(
            **{
                ("train" if role == "TRAIN" else "oos") + "_" + key: value
                for role, values in metrics.items()
                for key, value in values.items()
            }
        )
    )
    groups = []
    allowed_metrics = {
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown_abs",
        "annualized_turnover",
    }
    for inventory, role in zip(inventories, ("TRAIN", "OOS"), strict=True):
        group = {}
        for fact in inventory.unique.values():
            if fact.value_type != "NUMERIC" or fact.descriptor.sample_role != role:
                continue
            require(
                fact.citation.tool_name == "walk_forward.window_lineage"
                and fact.citation.entity_id
                == f"{body['study']['id']}:window:{body['window']['window_no']}"
                and fact.citation.report_id == body["validation"]["id"],
                "WINDOW_FACT_ROLE_MISMATCH",
            )
            require(
                any(
                    ref["evidence_id"] == fact.citation.evidence_id
                    and ref["content_hash"] == fact.citation.content_hash
                    for ref in body["evidence"]
                ),
                "WINDOW_EVIDENCE_BINDING_MISMATCH",
            )
            metric = fact.descriptor.metric_id.rsplit(".", 1)[-1]
            if metric not in allowed_metrics:
                continue
            require(metric not in group, "AMBIGUOUS_METRIC_IDENTITY")
            prefix = "train" if role == "TRAIN" else "oos"
            _compare_value(
                metrics[role][metric],
                fact.value,
                fact.descriptor.unit,
                "records.0." + prefix + "_metrics." + metric,
            )
            group[metric] = fact
        groups.append(group)
    require(bool(groups[0]) and set(groups[0]) == set(groups[1]), "WINDOW_METRICS_UNMATCHED")
    result["sample_context"] = {
        "study_id": body["study"]["id"],
        "validation_id": body["validation"]["id"],
        "window_no": body["window"]["window_no"],
        "train_start_date": body["window"]["train_start_date"],
        "train_end_date": body["window"]["train_end_date"],
        "oos_start_date": body["window"]["test_start_date"],
        "oos_end_date": body["window"]["test_end_date"],
        "mode": "WINDOW_DEGRADATION",
        "train_trade_dates_hash": body["window"]["train_date_hash"],
        "oos_trade_dates_hash": body["window"]["test_date_hash"],
        "limitations": ["DIFFERENT_TRAIN_OOS_SAMPLES", "NO_GENERAL_ROI_RANKING"],
        "optional_metric_gaps": ["SHARPE_NOT_AVAILABLE"]
        if any(values["sharpe_ratio"] is None for values in metrics.values())
        else [],
    }
    for key in sorted(groups[0]):
        a, b = groups[0][key], groups[1][key]
        require(a.descriptor.unit == b.descriptor.unit, "WINDOW_UNIT_MISMATCH")
        reverse = key in {"annualized_return", "sharpe_ratio"}
        output_key = {
            "annualized_return": "return_degradation",
            "sharpe_ratio": "sharpe_degradation",
            "max_drawdown_abs": "drawdown_worsening",
            "annualized_turnover": "turnover_change",
        }[key]
        delta = degradation[output_key]
        require(delta is not None, "WINDOW_OPTIONAL_METRIC_MISSING")
        if a.descriptor.unit == "percent":
            delta *= Decimal("100")
        result["facts"].append(
            {
                "metric_key": key,
                "left": a.value,
                "right": b.value,
                "left_fact": a.view(),
                "right_fact": b.view(),
                "pair_status": "COMPARABLE",
                "decision_reason_codes": [],
                "formula": "TRAIN_MINUS_OOS" if reverse else "OOS_MINUS_TRAIN",
                "delta": decimal_text(delta),
                "delta_semantics": "PERCENTAGE_POINT_DIFFERENCE"
                if a.descriptor.unit == "percent"
                else "WINDOW_DEGRADATION",
            }
        )
    for side, group, inventory in zip(("left", "right"), groups, inventories, strict=True):
        matched = {fact.descriptor for fact in group.values()}
        result["unmatched_facts"][side] = [
            fact.view()
            for fact in inventory.unique.values()
            if fact.value_type == "NUMERIC" and fact.descriptor not in matched
        ]
    return "COMPARABLE", []
