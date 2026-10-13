from app.domain.agent.frozen_contracts import (
    CONTRACT_MANIFEST_VERSION,
    CONTRACT_REPORT_SNAPSHOT_VERSION,
    CONTRACT_REPORT_VERSION,
)
from app.domain.agent.report import ReportContractReference, ReportFrozenContractReference
from app.services.agent.report.archive_binding import ARCHIVE_CHECK_SCOPE, verify_archive_contract
from app.services.agent.report.canonical import canonical_hash

CONTRACT_REPORT_CHECK_SCOPE = [
    *ARCHIVE_CHECK_SCOPE,
    "CONTRACT_MANIFEST",
    "CONTRACT_SOURCE_RELATIONS",
    "CONTRACT_DATE_SETS",
    "CONTRACT_ASSUMPTIONS",
    "WINDOW_SELECTION",
]


def contract_report_refs(verification):
    return [
        ReportFrozenContractReference(
            **item,
            tool_result_archive_id=verification.rows[item["contract_id"]].tool_result_archive_id,
        )
        for item in sorted(verification.check["results"], key=lambda item: item["contract_id"])
    ]


def report_contract_gaps(contract, verification):
    gaps = {code for item in verification.check["results"] for code in item["reason_codes"]}
    verified = {verification.rows[row_id].contract_kind for row_id in verification.verified}
    if "backtest.summary" in contract.tool_names or (
        "performance.summary" in contract.tool_names and "M14_EXACT_BUNDLE" not in verified
    ):
        gaps.add("EXACT_M14_BUNDLE_NOT_ARCHIVED")
    if "walk_forward.summary" in contract.tool_names:
        gaps.add("STUDY_AGGREGATE_ONLY")
    if (
        "walk_forward.window_lineage" in contract.tool_names
        and "M15_WINDOW_LINEAGE" not in verified
    ):
        gaps.add("FROZEN_M15_WINDOW_LINEAGE_REQUIRED")
    return sorted(gaps)


def bind_contract_report(snapshot, contract, verification):
    manifest = verification.manifest
    if manifest is None or verification.check["contract_integrity"]["status"] != "VERIFIED":
        raise ValueError("verified contract manifest required")
    if (
        snapshot.archive_reference is None
        or manifest.base_manifest_id != snapshot.archive_reference.manifest_id
    ):
        raise ValueError("contract base manifest mismatch")
    refs = contract_report_refs(verification)
    gaps = report_contract_gaps(contract, verification)
    scope = sorted({ref.contract_kind for ref in refs if ref.status == "VERIFIED"})
    if "M14_EXACT_BUNDLE" in scope and not set(contract.tool_names) & {
        "performance.summary",
        "walk_forward.window_lineage",
    }:
        raise ValueError("M14 contract is outside the report evidence scope")
    if "M15_WINDOW_LINEAGE" in scope and "walk_forward.window_lineage" not in contract.tool_names:
        raise ValueError("window contract is outside the report evidence scope")
    contract.report_version = CONTRACT_REPORT_VERSION
    contract.contract_manifest_id = manifest.id
    contract.contract_manifest_hash = manifest.manifest_hash
    contract.contract_policy_version = manifest.policy_version
    contract.contract_scope = scope
    contract.contract_refs = refs
    contract.gap_codes = gaps
    contract.verification_scope = list(CONTRACT_REPORT_CHECK_SCOPE)
    contract.limitations = [
        "HISTORICAL_TOOL_RESULT_ONLY",
        "FROZEN_CONTRACT_RECHECK",
        "CALCULATION_NOT_REEXECUTED",
        *gaps,
    ]
    snapshot.schema_version = CONTRACT_REPORT_SNAPSHOT_VERSION
    snapshot.contract_reference = ReportContractReference(
        manifest_id=manifest.id,
        manifest_hash=manifest.manifest_hash,
        policy_version=manifest.policy_version,
        contract_ids_hash=manifest.contract_ids_hash,
        contract_refs_hash=canonical_hash([ref.model_dump(mode="json") for ref in refs]),
        contract_count=len(refs),
        contract_scope=scope,
        gap_codes=gaps,
    )
    old_limits = {"EXACT_M14_BUNDLE_NOT_ARCHIVED", "FROZEN_M15_WINDOW_LINEAGE_REQUIRED"}
    snapshot.warnings = list(
        dict.fromkeys(
            [
                *[warning for warning in snapshot.warnings if warning not in old_limits],
                *contract.limitations,
            ]
        )
    )
    for section in snapshot.sections:
        if section.section_id == "methodology-limitations":
            section.items = list(contract.limitations)
        elif section.section_id == "generation-notes":
            section.items = [
                CONTRACT_REPORT_VERSION,
                snapshot.snapshot_level,
                manifest.policy_version,
            ]
    snapshot.source_contract_hash = canonical_hash(contract.model_dump(mode="json"))


def verify_contract_report(snapshot, contract):
    reference = snapshot.contract_reference
    if reference is None or (
        reference.policy_version != CONTRACT_MANIFEST_VERSION
        or contract.contract_policy_version != reference.policy_version
        or contract.contract_manifest_id != reference.manifest_id
        or contract.contract_manifest_hash != reference.manifest_hash
        or contract.contract_scope != reference.contract_scope
        or contract.gap_codes != reference.gap_codes
        or reference.contract_count != len(contract.contract_refs)
        or canonical_hash([ref.model_dump(mode="json") for ref in contract.contract_refs])
        != reference.contract_refs_hash
        or len({ref.contract_id for ref in contract.contract_refs}) != len(contract.contract_refs)
        or sorted({ref.contract_kind for ref in contract.contract_refs if ref.status == "VERIFIED"})
        != reference.contract_scope
    ):
        raise ValueError("frozen report contract reference mismatch")
    verify_archive_contract(
        snapshot,
        contract,
        expected_gaps=reference.gap_codes,
        expected_scope=CONTRACT_REPORT_CHECK_SCOPE,
    )
