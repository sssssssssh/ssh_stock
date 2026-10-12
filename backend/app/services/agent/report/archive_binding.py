"""Versioned Report v3 binding; never reconstruct old source payloads."""

from app.domain.agent.archive import ARCHIVE_VERSION, RECHECK_VERSION
from app.domain.agent.report import ReportArchiveReference
from app.services.agent.report.canonical import canonical_hash

ARCHIVED_REPORT_VERSION = "m16.5-v1"
ARCHIVED_SNAPSHOT_VERSION = "m16.5-report-snapshot-v3"
ARCHIVE_CHECK_SCOPE = [
    "PAYLOAD_HASH",
    "TOOL_AUDIT",
    "MANIFEST_BINDING",
    "EVIDENCE_IDENTITY",
    "FIELD_PATH",
    "ENTITY_DATE_UNIT",
    "DECIMAL_VALUE",
    "INFERENCE_SUPPORT",
]


def archive_gaps(tool_names):
    gaps = []
    if "performance.summary" in tool_names or "backtest.summary" in tool_names:
        gaps.append("EXACT_M14_BUNDLE_NOT_ARCHIVED")
    if any(name.startswith("walk_forward.") for name in tool_names):
        gaps.append("FROZEN_M15_WINDOW_LINEAGE_REQUIRED")
    return sorted(gaps)


def frozen_fields(snapshot):
    return sorted({ref for claim in snapshot.claims for ref in claim.verified_fact_refs})


def bind_archive(snapshot, contract, manifest):
    snapshot.schema_version = ARCHIVED_SNAPSHOT_VERSION
    snapshot.snapshot_level = contract.snapshot_level = "FROZEN_TOOL_EVIDENCE"
    snapshot.archive_reference = ReportArchiveReference(
        manifest_id=manifest.id,
        manifest_version=manifest.manifest_version,
        manifest_hash=manifest.manifest_hash,
        archive_status=manifest.archive_status,
        reproduction_level="FROZEN_FACT_RECHECK",
    )
    contract.report_version = ARCHIVED_REPORT_VERSION
    contract.archive_manifest_hash = manifest.manifest_hash
    contract.archive_policy_version = RECHECK_VERSION
    contract.verification_scope = list(ARCHIVE_CHECK_SCOPE)
    contract.frozen_fields = frozen_fields(snapshot)
    contract.gap_codes = archive_gaps(contract.tool_names)
    contract.limitations = [
        "HISTORICAL_TOOL_RESULT_ONLY",
        "CALCULATION_NOT_REEXECUTED",
        *contract.gap_codes,
    ]
    legacy_warnings = {"SOURCE_PAYLOAD_NOT_ARCHIVED", "REPLAY_UNAVAILABLE"}
    snapshot.warnings = list(
        dict.fromkeys(
            [
                *[item for item in snapshot.warnings if item not in legacy_warnings],
                *contract.limitations,
            ]
        )
    )
    for section in snapshot.sections:
        if section.section_id == "methodology-limitations":
            section.items = list(contract.limitations)
        elif section.section_id == "generation-notes":
            section.items = [ARCHIVED_REPORT_VERSION, snapshot.snapshot_level, RECHECK_VERSION]
    snapshot.source_contract_hash = canonical_hash(contract.model_dump(mode="json"))


def verify_archive_contract(snapshot, contract):
    if any(
        len(claim.verified_fact_refs) != len(claim.structured_facts) for claim in snapshot.claims
    ):
        raise ValueError("frozen field bindings")
    ref = snapshot.archive_reference
    if (
        ref is None
        or ref.manifest_version != ARCHIVE_VERSION
        or snapshot.snapshot_level != "FROZEN_TOOL_EVIDENCE"
        or contract.snapshot_level != snapshot.snapshot_level
        or contract.archive_manifest_hash != ref.manifest_hash
        or contract.archive_policy_version != RECHECK_VERSION
        or contract.verification_scope != ARCHIVE_CHECK_SCOPE
        or contract.frozen_fields != frozen_fields(snapshot)
        or contract.gap_codes != archive_gaps(contract.tool_names)
    ):
        raise ValueError("archive source contract")
