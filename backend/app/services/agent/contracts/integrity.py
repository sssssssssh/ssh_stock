from dataclasses import dataclass, field
from typing import Any

from app.domain.agent.archive import AgentArchiveError, archive_error
from app.domain.agent.frozen_contracts import (
    CONTRACT_MANIFEST_VERSION,
    M14_CONTRACT_VERSION,
    M15_AGGREGATE_CONTRACT_VERSION,
    M15_WINDOW_CONTRACT_VERSION,
)
from app.services.agent.contracts.canonical import contract_hash, contract_storage_size
from app.services.agent.contracts.semantics import (
    ContractSemanticError,
    require,
    verify_m14,
    verify_m15,
)
from app.services.performance.analytics_bundle import AnalyticsBundleError


@dataclass
class ContractVerification:
    check: dict[str, Any]
    manifest: Any = None
    rows: dict[str, Any] = field(default_factory=dict)
    verified: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_tool_ids: dict[str, str] = field(default_factory=dict)


def missing_contracts():
    return ContractVerification(
        check={
            "contract_integrity": {"status": "UNVERIFIABLE", "reason_codes": ["CONTRACT_MISSING"]},
            "contract_semantics": {"status": "UNVERIFIABLE", "reason_codes": ["CONTRACT_MISSING"]},
            "comparison_permission": {"allowed": False, "reason_codes": ["CONTRACT_MISSING"]},
            "calculation_reproduced": False,
            "results": [],
        }
    )


def verify_contract_archive(manifest, rows, base, config, check_budget=lambda: None):
    try:
        check_budget()
        parent = base.manifest
        require(
            manifest.base_manifest_id == parent.id
            and manifest.base_manifest_hash == parent.manifest_hash
        )
        require(
            all(
                getattr(manifest, key) == getattr(parent, key)
                for key in ("owner_user_id", "chat_id", "turn_id")
            )
        )
        body = manifest.manifest_json
        require(contract_hash(body) == manifest.manifest_hash, "CONTRACT_MANIFEST_HASH_MISMATCH")
        if manifest.policy_version != CONTRACT_MANIFEST_VERSION:
            result = missing_contracts()
            result.manifest = manifest
            for key in ("contract_integrity", "contract_semantics"):
                result.check[key]["reason_codes"] = ["CONTRACT_MANIFEST_VERSION_UNSUPPORTED"]
            return result
        require(
            set(body)
            == {
                "policy_version",
                "base_manifest_id",
                "base_manifest_hash",
                "owner_user_id",
                "chat_id",
                "turn_id",
                "contract_count",
                "contract_ids_hash",
                "contracts",
            }
        )
        for key in ("policy_version", "base_manifest_hash", "contract_count", "contract_ids_hash"):
            require(body[key] == getattr(manifest, key))
        for key in ("base_manifest_id", "owner_user_id", "chat_id", "turn_id"):
            require(body[key] == str(getattr(manifest, key)))
        require(0 < len(rows) == manifest.contract_count <= config.max_contracts)
        refs = body["contracts"]
        require(len(refs) == len(rows) and contract_hash(refs) == manifest.contract_ids_hash)
        require(
            refs
            == sorted(
                refs,
                key=lambda ref: (
                    ref["tool_call_id"],
                    ref["contract_kind"],
                    ref["subject_id"],
                    ref["role"],
                ),
            )
        )
        require(
            {ref["id"] for ref in refs} == {str(row.id) for row in rows}
            and len({ref["id"] for ref in refs}) == len(refs)
        )
        by_id = {str(row.id): row for row in rows}
        tools = {str(tool.id): tool for tool in base.tools}
        total_bytes = contract_storage_size(body)
        statuses = {}
        verified = {}
        for ref in refs:
            check_budget()
            row = by_id[ref["id"]]
            require(
                set(ref)
                == {
                    "id",
                    "tool_call_id",
                    "tool_result_archive_id",
                    "contract_kind",
                    "subject_id",
                    "role",
                    "schema_version",
                    "contract_hash",
                }
                | ({"dependencies"} if row.contract_kind == "M15_WINDOW_LINEAGE" else set())
            )
            require(
                all(
                    getattr(row, key) == getattr(parent, key)
                    for key in ("owner_user_id", "chat_id", "turn_id")
                )
            )
            for key in ("contract_kind", "subject_id", "role", "schema_version", "contract_hash"):
                require(ref[key] == getattr(row, key))
            require(ref["tool_result_archive_id"] == str(row.tool_result_archive_id))
            tool = tools.get(str(row.tool_result_archive_id))
            require(tool is not None and tool.tool_call_id == ref["tool_call_id"])
            size = contract_storage_size(row.contract_json)
            require(
                row.size_bytes == size and size <= config.max_contract_bytes,
                "CONTRACT_SIZE_MISMATCH",
            )
            total_bytes += size
            require(total_bytes <= config.max_turn_bytes, "CONTRACT_LIMIT_EXCEEDED")
            require(contract_hash(row.contract_json) == row.contract_hash, "CONTRACT_HASH_MISMATCH")
            expected_version = {
                "M14_EXACT_BUNDLE": M14_CONTRACT_VERSION,
                "M15_WINDOW_LINEAGE": M15_WINDOW_CONTRACT_VERSION,
                "M15_STUDY_AGGREGATE": M15_AGGREGATE_CONTRACT_VERSION,
            }.get(row.contract_kind)
            if row.schema_version != expected_version:
                statuses[str(row.id)] = ("UNVERIFIABLE", ["CONTRACT_VERSION_UNSUPPORTED"])
                continue
            _tool_binding(row, tool)
            if row.contract_kind == "M15_WINDOW_LINEAGE":
                continue
            if row.contract_kind == "M15_STUDY_AGGREGATE" or row.contract_json["status"] == "GAP":
                reasons = row.contract_json.get("reason_codes", [])
                require(bool(reasons) and len(reasons) <= 32)
                require(
                    set(reasons)
                    <= {
                        "PERIOD_REPORT_MISSING",
                        "PERFORMANCE_DATE_SERIES_INCOMPLETE",
                        "M14_MODEL_VERSION_UNSUPPORTED",
                        "EXECUTION_ACCOUNTING_SNAPSHOT_INCOMPLETE",
                        "STUDY_AGGREGATE_ONLY",
                    }
                )
                statuses[str(row.id)] = ("UNVERIFIABLE", reasons)
            else:
                verify_m14(row.contract_json)
                statuses[str(row.id)] = ("VERIFIED", [])
                verified[str(row.id)] = row.contract_json
        for ref in refs:
            row = by_id[ref["id"]]
            if row.contract_kind != "M15_WINDOW_LINEAGE" or ref["id"] in statuses:
                continue
            check_budget()
            require(
                set(ref)
                == {
                    "id",
                    "tool_call_id",
                    "tool_result_archive_id",
                    "contract_kind",
                    "subject_id",
                    "role",
                    "schema_version",
                    "contract_hash",
                    "dependencies",
                }
            )
            dependencies = ref["dependencies"]
            require(
                len(dependencies) == 2
                and {item["role"] for item in dependencies} == {"TRAIN", "OOS"}
            )
            endpoints = {}
            for dependency in dependencies:
                require(set(dependency) == {"id", "role", "contract_hash"})
                child = by_id.get(dependency["id"])
                require(
                    child is not None
                    and child.contract_kind == "M14_EXACT_BUNDLE"
                    and child.role == dependency["role"]
                    and child.contract_hash == dependency["contract_hash"]
                    and child.tool_result_archive_id == row.tool_result_archive_id,
                    "CONTRACT_DEPENDENCY_MISMATCH",
                )
                require(
                    {
                        "role": child.role,
                        "subject_id": child.subject_id,
                        "contract_hash": child.contract_hash,
                    }
                    in row.contract_json["m14_contract_refs"]
                )
                if dependency["id"] in verified:
                    endpoints[child.role] = verified[dependency["id"]]
            if len(endpoints) != 2 or row.contract_json["status"] == "GAP":
                statuses[ref["id"]] = ("UNVERIFIABLE", ["WINDOW_ENDPOINT_CONTRACT_UNVERIFIABLE"])
                continue
            verify_m15(row.contract_json, endpoints)
            verified[ref["id"]] = row.contract_json
            statuses[ref["id"]] = ("VERIFIED", [])
        results = [
            {
                "contract_id": ref["id"],
                "contract_kind": ref["contract_kind"],
                "subject_id": ref["subject_id"],
                "role": ref["role"],
                "schema_version": ref["schema_version"],
                "contract_hash": ref["contract_hash"],
                "status": statuses[ref["id"]][0],
                "reason_codes": statuses[ref["id"]][1],
            }
            for ref in refs
        ]
        reasons = sorted({code for item in results for code in item["reason_codes"]})
        check_budget()
        return ContractVerification(
            check={
                "contract_manifest_id": str(manifest.id),
                "contract_manifest_hash": manifest.manifest_hash,
                "policy_version": manifest.policy_version,
                "contract_integrity": {"status": "VERIFIED", "reason_codes": []},
                "contract_semantics": {
                    "status": "UNVERIFIABLE" if reasons else "VERIFIED",
                    "reason_codes": reasons,
                },
                "comparison_permission": {
                    "allowed": False,
                    "reason_codes": ["SCENARIO_POLICY_REQUIRED"],
                },
                "calculation_reproduced": False,
                "results": results,
            },
            manifest=manifest,
            rows=by_id,
            verified=verified,
            evidence_tool_ids={
                row.evidence_id: str(row.tool_result_archive_id) for row in base.bindings
            },
        )
    except ContractSemanticError as exc:
        raise archive_error(exc.code) from exc
    except AgentArchiveError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        ArithmeticError,
        AnalyticsBundleError,
    ) as exc:
        raise archive_error("CONTRACT_INTEGRITY_MISMATCH") from exc


def _tool_binding(row, tool):
    body = row.contract_json
    require(body["status"] in {"COMPLETE", "GAP"})
    if row.contract_kind == "M14_EXACT_BUNDLE" and body["status"] == "GAP":
        require(set(body) == {"selected", "evidence", "status", "reason_codes"})
    refs = {ref["evidence_id"]: ref for ref in tool.payload_json["evidence"]}
    anchors = body["evidence"]
    require(bool(anchors) and len({item["evidence_id"] for item in anchors}) == len(anchors))
    for anchor in anchors:
        require(set(anchor) == {"evidence_id", "content_hash", "report_id"})
        require(anchor["evidence_id"] in refs)
        require(
            all(
                anchor[key] == refs[anchor["evidence_id"]].get(key)
                for key in ("content_hash", "report_id")
            ),
            "CONTRACT_EVIDENCE_MISMATCH",
        )
    if row.contract_kind == "M14_EXACT_BUNDLE":
        require(row.subject_id == body["selected"]["run_id"])
        require(row.verification_scope == "FROZEN_CONTRACT_RECHECK")
        if tool.tool_name == "performance.summary":
            require(row.role == "LIVE")
            require(
                all(
                    str(tool.payload_json["identity"].get(key)) == str(value)
                    for key, value in body["selected"].items()
                )
            )
            if body["status"] == "COMPLETE":
                require(
                    contract_hash(body["record"]) == contract_hash(tool.payload_json["records"][0])
                )
        else:
            require(
                tool.tool_name == "walk_forward.window_lineage" and row.role in {"TRAIN", "OOS"}
            )
            prefix = "train" if row.role == "TRAIN" else "oos"
            matches = [
                record
                for record in tool.payload_json["records"]
                if str(record[prefix + "_run_id"]) == row.subject_id
                and str(record[prefix + "_performance_id"]) == body["selected"]["performance_id"]
            ]
            require(len(matches) == 1, "CONTRACT_WINDOW_EVIDENCE_MISMATCH")
            if body["status"] == "COMPLETE":
                require(
                    all(
                        contract_hash(matches[0][prefix + "_metrics"][key]) == contract_hash(value)
                        for key, value in body["record"]["window_metrics"].items()
                    )
                )
    else:
        require(row.role == "STUDY")
        require(body["validation"]["id"] == str(tool.payload_json["identity"]["validation_id"]))
        if row.contract_kind == "M15_STUDY_AGGREGATE":
            require(
                tool.tool_name == "walk_forward.summary"
                and row.verification_scope == "STUDY_AGGREGATE_ONLY"
            )
            require(contract_hash(body["record"]) == contract_hash(tool.payload_json["records"][0]))
        else:
            require(tool.tool_name == "walk_forward.window_lineage")
            require(
                row.subject_id
                == f"{body['study']['id']}:{body['validation']['id']}:{body['window']['window_no']}"
            )
            matches = [
                record
                for record in tool.payload_json["records"]
                if record["window_no"] == body["window"]["window_no"]
            ]
            require(
                len(matches) == 1 and contract_hash(matches[0]) == contract_hash(body["record"])
            )
