from __future__ import annotations

from typing import Any

from app.domain.agent.report import (
    ReportEvidenceIdentity,
    ReportSourceContract,
    ResearchReportSnapshot,
)
from app.domain.agent.report_errors import AgentReportError
from app.services.agent.report.archive_binding import (
    ARCHIVED_REPORT_VERSION,
    ARCHIVED_SNAPSHOT_VERSION,
    archive_gaps,
    verify_archive_contract,
)
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.comparison_policy import (
    REPORT_COMPARISON_POLICY_VERSION,
    contract_signature,
)


def _failure(code: str) -> AgentReportError:
    return AgentReportError(code, "frozen research integrity check failed", status_code=409)


def verify_report(row: Any) -> tuple[ResearchReportSnapshot, ReportSourceContract]:
    try:
        if canonical_hash(row.snapshot_json) != row.snapshot_hash:
            raise ValueError("snapshot hash")
        snapshot = ResearchReportSnapshot.model_validate(row.snapshot_json)
        contract = ReportSourceContract.model_validate(row.source_contract_json)
        for field in (
            "report_type",
            "title",
            "as_of_date",
            "source_chat_id",
            "source_message_id",
            "source_turn_id",
            "source_answer_status",
        ):
            if getattr(row, field) != getattr(snapshot, field):
                raise ValueError("snapshot metadata")
        if row.report_version != contract.report_version:
            raise ValueError("report version")
        if row.report_version not in {"m16.4-v1", ARCHIVED_REPORT_VERSION}:
            raise ValueError("unsupported frozen report version")
        if row.report_version == ARCHIVED_REPORT_VERSION:
            if (
                snapshot.schema_version != ARCHIVED_SNAPSHOT_VERSION
                or snapshot.source_contract_hash is None
            ):
                raise ValueError("archive snapshot schema")
            verify_archive_contract(snapshot, contract)
        elif snapshot.schema_version not in {
            "m16.4-report-snapshot-v1",
            "m16.4.1-report-snapshot-v2",
        }:
            raise ValueError("snapshot schema")
        elif (
            snapshot.archive_reference is not None
            or snapshot.snapshot_level != "CLAIM_SNAPSHOT_ONLY"
            or contract.snapshot_level != "CLAIM_SNAPSHOT_ONLY"
        ):
            raise ValueError("historical archive escalation")
        if (
            snapshot.schema_version == "m16.4.1-report-snapshot-v2"
            and snapshot.source_contract_hash is None
        ):
            raise ValueError("source contract digest required")
        if snapshot.source_contract_hash is not None and (
            snapshot.source_contract_hash != canonical_hash(row.source_contract_json)
        ):
            raise ValueError("source contract digest")
        verify_source_contract(snapshot, contract)
        return snapshot, contract
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise _failure("REPORT_SNAPSHOT_INTEGRITY_ERROR") from exc


def verify_source_contract(
    snapshot: ResearchReportSnapshot, contract: ReportSourceContract
) -> None:
    refs = {item.evidence_id: item for item in snapshot.citations}
    if len(refs) != len(snapshot.citations):
        raise ValueError("duplicate citation identity")
    if len({item.claim_id for item in snapshot.claims}) != len(snapshot.claims):
        raise ValueError("duplicate claim identity")
    used = {eid for claim in snapshot.claims for eid in claim.evidence_ids}
    if used != set(refs) or any(not claim.evidence_ids for claim in snapshot.claims):
        raise ValueError("claim citation references")
    if any(
        cid not in {claim.claim_id for claim in snapshot.claims}
        for section in snapshot.sections
        for cid in section.claim_ids
    ):
        raise ValueError("section claim references")
    identities = [
        ReportEvidenceIdentity(
            **item.model_dump(mode="python", exclude={"marker", "observed_at", "navigation"})
        )
        for item in snapshot.citations
    ]
    if sorted(canonical_hash(item.model_dump(mode="json")) for item in identities) != sorted(
        canonical_hash(item.model_dump(mode="json")) for item in contract.evidence_identities
    ):
        raise ValueError("source identity citation mismatch")
    if sorted(contract.tool_names) != sorted({item.tool_name for item in snapshot.citations}):
        raise ValueError("source tool mismatch")
    if sorted(contract.evidence_versions) != sorted(
        {item.evidence_version for item in snapshot.citations}
    ):
        raise ValueError("source evidence version mismatch")
    expected_limits = {"SOURCE_PAYLOAD_NOT_ARCHIVED", "REPLAY_UNAVAILABLE"}
    if "performance.summary" in contract.tool_names:
        expected_limits.add("EXACT_M14_BUNDLE_NOT_ARCHIVED")
    if contract.report_version == ARCHIVED_REPORT_VERSION:
        expected_limits = {
            "HISTORICAL_TOOL_RESULT_ONLY",
            "CALCULATION_NOT_REEXECUTED",
            *archive_gaps(contract.tool_names),
        }
    if set(contract.limitations) != expected_limits:
        raise ValueError("source limitations mismatch")
    if contract.comparison_policy_version != "m16.2.2-comparison-v1":
        raise ValueError("source claim policy")


def verify_comparison(row: Any, left: Any, right: Any) -> None:
    try:
        verify_report(left)
        verify_report(right)
        result = row.result_json
        if canonical_hash(result) != row.comparison_hash:
            raise ValueError("comparison hash")
        for side, report in (("left", left), ("right", right)):
            if (
                getattr(row, f"{side}_report_id") != report.id
                or report.owner_user_id != row.owner_user_id
                or result[f"{side}_report_id"] != str(report.id)
                or result[f"{side}_snapshot_hash"] != report.snapshot_hash
                or getattr(row, f"{side}_snapshot_hash") != report.snapshot_hash
            ):
                raise ValueError("comparison report binding")
        if any(result[field] != getattr(row, field) for field in ("state", "policy_version")):
            raise ValueError("comparison metadata")
        if result["reason_codes"] != row.reason_codes_json:
            raise ValueError("comparison reasons")
        if row.policy_version == REPORT_COMPARISON_POLICY_VERSION:
            expected = {
                "left": contract_signature(
                    ReportSourceContract.model_validate(left.source_contract_json)
                ),
                "right": contract_signature(
                    ReportSourceContract.model_validate(right.source_contract_json)
                ),
            }
            if result.get("source_contract_hashes") != expected:
                raise ValueError("comparison source contract binding")
            for fact in result.get("facts", []):
                if "delta" in fact and (
                    row.state != "COMPARABLE" or fact.get("pair_status") != "COMPARABLE"
                ):
                    raise ValueError("comparison delta permission")
    except (AgentReportError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise _failure("REPORT_COMPARISON_INTEGRITY_ERROR") from exc
