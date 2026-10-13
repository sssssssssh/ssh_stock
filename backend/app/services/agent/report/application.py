from __future__ import annotations

import time
import uuid
from typing import Any

from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.agent.archive import AgentArchiveError
from app.domain.agent.frozen_contracts import CONTRACT_REPORT_VERSION
from app.domain.agent.policy import user_audit_hash
from app.domain.agent.report import (
    CreateReportComparison,
    CreateResearchReport,
    ReportComparisonView,
    ResearchReportSummary,
    ResearchReportView,
)
from app.domain.agent.report_errors import (
    AgentReportError,
    comparison_not_found,
    idempotency_conflict,
    invalid_source,
    report_not_found,
)
from app.models.agent_report import AgentResearchReport, AgentResearchReportComparison
from app.repositories.agent_report import AgentReportRepository
from app.services.agent.archive.application import AgentArchiveApplication
from app.services.agent.archive.recheck import recheck_archive
from app.services.agent.contracts.application import AgentFrozenContractApplication
from app.services.agent.contracts.integrity import missing_contracts
from app.services.agent.contracts.policy import (
    CONTRACT_COMPARISON_POLICY_VERSION,
    compare_frozen_research,
)
from app.services.agent.contracts.projection import safe_contract_projection
from app.services.agent.contracts.report_binding import (
    bind_contract_report,
    contract_report_refs,
    report_contract_gaps,
)
from app.services.agent.report.archive_binding import bind_archive
from app.services.agent.report.canonical import canonical_hash, storage_json_bytes
from app.services.agent.report.comparison import compare_report_snapshots
from app.services.agent.report.comparison_policy import (
    REPORT_COMPARISON_POLICY_VERSION,
    contract_signature,
)
from app.services.agent.report.integrity import verify_comparison, verify_report
from app.services.agent.report.render import render_comparison, render_html, render_markdown
from app.services.agent.report.snapshot import build_report_snapshot


class AgentReportApplication:
    def __init__(self, db: Session, settings: Settings) -> None:
        if settings.agent_config is None:
            raise RuntimeError("agent config is not loaded")
        self.db = db
        self.settings = settings
        self.config = settings.agent_config.reports
        self.repo = AgentReportRepository(db)

    def create_report(self, *, user: Any, body: CreateResearchReport) -> ResearchReportView:
        started = time.monotonic()
        owner_id = _user_id(user)
        request_hash = canonical_hash(body.model_dump(mode="json", exclude={"request_id"}))
        existing = self.repo.get_by_request(owner_user_id=owner_id, request_id=body.request_id)
        if existing is not None:
            replayed = self._same_report_or_conflict(existing, request_hash)
            _audit(
                user=user,
                operation="create_report",
                object_id=existing.id,
                request_id=body.request_id,
                source_type=body.report_type,
                content_hash=existing.snapshot_hash,
                status="REPLAYED",
                started=started,
            )
            return replayed
        source = self.repo.get_owned_source_message(
            owner_user_id=owner_id,
            chat_id=body.source_chat_id,
            message_id=body.source_message_id,
        )
        if source is None:
            raise invalid_source("SOURCE_MESSAGE_NOT_FOUND", "source message not found")
        if source.role != "ASSISTANT" or source.status != "COMPLETED":
            raise invalid_source(
                "INVALID_SOURCE_MESSAGE", "source must be a completed assistant message"
            )
        turn = self.repo.get_source_turn(
            chat_id=body.source_chat_id, message_id=body.source_message_id
        )
        if turn is None:
            raise invalid_source("SOURCE_TURN_NOT_COMPLETED", "source turn is not completed")
        if (
            body.parent_report_id is not None
            and self.repo.get_owned_report(owner_user_id=owner_id, report_id=body.parent_report_id)
            is None
        ):
            raise report_not_found()
        snapshot, contract = build_report_snapshot(
            report_type=body.report_type,
            title=body.title,
            source_chat_id=body.source_chat_id,
            source_message_id=body.source_message_id,
            source_turn_id=turn.id,
            source_metadata=dict(source.metadata_json or {}),
            config=self.config,
        )
        archive = AgentArchiveApplication(self.db, self.settings)
        try:
            bundle = archive.load_bundle(owner_id, turn.id)
            if bundle is not None and bundle.manifest.archive_status == "COMPLETE":
                result = recheck_archive(bundle, config=archive.config)
                if not _archive_recheck_allows_report(snapshot, result):
                    raise AgentArchiveError(
                        "REPORT_ARCHIVE_UNVERIFIABLE", "frozen facts unavailable", status_code=409
                    )
                bind_archive(snapshot, contract, bundle.manifest)
                frozen = AgentFrozenContractApplication(self.db, self.settings).check_turn(
                    owner_id=owner_id,
                    turn_id=turn.id,
                    base_bundle=bundle,
                )
                if frozen.manifest is not None:
                    bind_contract_report(snapshot, contract, frozen)
        except AgentArchiveError as exc:
            self.db.rollback()
            raise AgentReportError(exc.code, str(exc), status_code=exc.status_code) from exc
        except (ValueError, TypeError, KeyError) as exc:
            self.db.rollback()
            raise AgentReportError(
                "REPORT_ARCHIVE_UNVERIFIABLE", "frozen facts unavailable", status_code=409
            ) from exc
        snapshot_json = snapshot.model_dump(mode="json")
        if len(storage_json_bytes(snapshot_json)) > self.config.max_snapshot_bytes:
            raise invalid_source("REPORT_LIMIT_EXCEEDED", "snapshot size limit exceeded")
        try:
            row = self.repo.add_report(
                owner_user_id=owner_id,
                source_chat_id=body.source_chat_id,
                source_message_id=body.source_message_id,
                source_turn_id=turn.id,
                parent_report_id=body.parent_report_id,
                request_id=body.request_id,
                request_hash=request_hash,
                report_type=body.report_type,
                report_version=contract.report_version,
                title=snapshot.title,
                as_of_date=snapshot.as_of_date,
                source_answer_status=snapshot.source_answer_status,
                snapshot_json=snapshot_json,
                snapshot_hash=canonical_hash(snapshot_json),
                source_contract_json=contract.model_dump(mode="json"),
            )
            result = self._verified_report_view(row)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.repo.get_by_request(owner_user_id=owner_id, request_id=body.request_id)
            if existing is None:
                raise
            return self._same_report_or_conflict(existing, request_hash)
        except AgentReportError:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise AgentReportError(
                "REPORT_CREATE_FAILED", "report creation failed", status_code=503
            ) from exc
        _audit(
            user=user,
            operation="create_report",
            object_id=row.id,
            request_id=body.request_id,
            source_type=body.report_type,
            content_hash=row.snapshot_hash,
            status="CREATED",
            started=started,
        )
        return result

    def list_reports(
        self,
        *,
        user: Any,
        limit: int,
        offset: int,
        include_archived: bool,
        report_type: str | None = None,
        archived: bool | None = None,
    ) -> tuple[list[ResearchReportSummary], int]:
        rows, total = self.repo.report_page(
            owner_user_id=_user_id(user),
            limit=limit,
            offset=offset,
            include_archived=include_archived,
            report_type=report_type,
            archived=archived,
        )
        return [_report_summary(row) for row in rows], total

    def get_report(self, *, user: Any, report_id: uuid.UUID) -> ResearchReportView:
        row = self.repo.get_owned_report(owner_user_id=_user_id(user), report_id=report_id)
        if row is None:
            raise report_not_found()
        return self._verified_report_view(row)

    def archive_report(self, *, user: Any, report_id: uuid.UUID) -> ResearchReportView:
        started = time.monotonic()
        row = self.repo.get_owned_report(
            owner_user_id=_user_id(user), report_id=report_id, for_update=True
        )
        if row is None:
            raise report_not_found()
        verify_report(row)
        self._verify_archive(row)
        self.repo.archive(row)
        self.db.commit()
        self.db.refresh(row)
        result = self._verified_report_view(row)
        _audit(
            user=user,
            operation="archive_report",
            object_id=row.id,
            request_id=None,
            source_type=row.report_type,
            content_hash=row.snapshot_hash,
            status="ARCHIVED",
            started=started,
        )
        return result

    def export_report(
        self, *, user: Any, report_id: uuid.UUID, export_format: str
    ) -> tuple[str, str, str]:
        report = self.get_report(user=user, report_id=report_id)
        contracts = None
        if report.snapshot.contract_reference is not None:
            verification = self._report_contracts(user=user, report_id=report_id)
            contracts = [
                {
                    "metadata": ref.model_dump(mode="json"),
                    "projection": safe_contract_projection(verification.rows[str(ref.contract_id)]),
                }
                for ref in contract_report_refs(verification)
            ]
        if export_format == "markdown":
            content = render_markdown(report.snapshot, report.snapshot_hash, contracts)
            self._check_export_size(content)
            return (
                content,
                "text/markdown; charset=utf-8",
                f"research-report-{report.report_id}.md",
            )
        if export_format == "html":
            content = render_html(report.snapshot, report.snapshot_hash, contracts)
            self._check_export_size(content)
            return (
                content,
                "text/html; charset=utf-8",
                f"research-report-{report.report_id}.html",
            )
        raise AgentReportError(
            "INVALID_EXPORT_FORMAT", "unsupported export format", status_code=422
        )

    def _check_export_size(self, content):
        if len(content.encode("utf-8")) > self.settings.agent_config.frozen_contract.max_turn_bytes:
            raise AgentReportError(
                "REPORT_EXPORT_LIMIT_EXCEEDED", "export exceeds byte limit", status_code=422
            )

    def export_comparison(self, *, user, comparison_id, export_format):
        if export_format not in {"markdown", "html"}:
            raise AgentReportError(
                "INVALID_EXPORT_FORMAT", "unsupported export format", status_code=422
            )
        view = self.get_comparison(user=user, comparison_id=comparison_id)
        content = render_comparison(view, export_format)
        self._check_export_size(content)
        extension = "html" if export_format == "html" else "md"
        media_type = (
            "text/html; charset=utf-8"
            if export_format == "html"
            else "text/markdown; charset=utf-8"
        )
        return content, media_type, f"research-comparison-{comparison_id}.{extension}"

    def create_comparison(self, *, user: Any, body: CreateReportComparison) -> ReportComparisonView:
        started = time.monotonic()
        owner_id = _user_id(user)
        request_content = body.model_dump(mode="json", exclude={"request_id"})
        if body.comparison_mode is None:
            request_content.pop("comparison_mode", None)
        # AUTO retains the original request hash, allowing historical idempotent replay.
        if body.comparison_intent == "AUTO":
            request_content.pop("comparison_intent")
        request_hash = canonical_hash(request_content)
        existing = self.repo.get_comparison_by_request(
            owner_user_id=owner_id, request_id=body.request_id
        )
        if existing is not None:
            replayed = self._same_comparison_or_conflict(existing, request_hash)
            _audit(
                user=user,
                operation="compare_reports",
                object_id=existing.id,
                request_id=body.request_id,
                source_type="report_comparison",
                content_hash=existing.comparison_hash,
                status="REPLAYED",
                started=started,
            )
            return replayed
        left = self.repo.get_owned_report(owner_user_id=owner_id, report_id=body.left_report_id)
        right = self.repo.get_owned_report(owner_user_id=owner_id, report_id=body.right_report_id)
        if left is None or right is None:
            raise report_not_found()
        left_snapshot, left_contract = verify_report(left)
        right_snapshot, right_contract = verify_report(right)
        deadline = (
            time.monotonic() + self.settings.agent_config.frozen_contract.verify_timeout_seconds
        )
        left_frozen = self._verify_archive(left, deadline=deadline)
        right_frozen = self._verify_archive(right, deadline=deadline)
        intent = body.comparison_intent
        if body.comparison_mode is not None and intent == "AUTO":
            intent = (
                "TRAIN_VS_OOS"
                if body.comparison_mode == "WINDOW_DEGRADATION"
                else "INDEPENDENT_BACKTESTS"
            )
        if left.report_version == right.report_version == CONTRACT_REPORT_VERSION and (
            body.comparison_mode is not None or intent in {"INDEPENDENT_BACKTESTS", "TRAIN_VS_OOS"}
        ):
            state, reasons, result = compare_frozen_research(
                left_snapshot,
                right_snapshot,
                left_verification=left_frozen,
                right_verification=right_frozen,
                max_facts=self.config.max_comparison_facts,
                comparison_intent=intent,
                comparison_mode=body.comparison_mode,
            )
            result["source_contract_hashes"] = {
                "left": contract_signature(left_contract),
                "right": contract_signature(right_contract),
            }
        else:
            state, reasons, result = compare_report_snapshots(
                left_snapshot,
                right_snapshot,
                max_facts=self.config.max_comparison_facts,
                left_contract=left_contract,
                right_contract=right_contract,
                comparison_intent=intent,
            )
        frozen = {
            **result,
            "left_report_id": str(left.id),
            "right_report_id": str(right.id),
            "left_snapshot_hash": left.snapshot_hash,
            "right_snapshot_hash": right.snapshot_hash,
        }
        comparison_hash = canonical_hash(frozen)
        try:
            row = self.repo.add_comparison(
                owner_user_id=owner_id,
                left_report_id=left.id,
                right_report_id=right.id,
                request_id=body.request_id,
                request_hash=request_hash,
                policy_version=result["policy_version"],
                state=state,
                reason_codes_json=reasons,
                result_json=frozen,
                left_snapshot_hash=left.snapshot_hash,
                right_snapshot_hash=right.snapshot_hash,
                comparison_hash=comparison_hash,
            )
            result = self._verified_comparison_view(row)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.repo.get_comparison_by_request(
                owner_user_id=owner_id, request_id=body.request_id
            )
            if existing is None:
                raise
            return self._same_comparison_or_conflict(existing, request_hash)
        except AgentReportError:
            self.db.rollback()
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise AgentReportError(
                "REPORT_COMPARISON_CREATE_FAILED", "comparison creation failed", status_code=503
            ) from exc
        _audit(
            user=user,
            operation="compare_reports",
            object_id=row.id,
            request_id=body.request_id,
            source_type="report_comparison",
            content_hash=row.comparison_hash,
            status=row.state,
            started=started,
        )
        return result

    def get_comparison(self, *, user: Any, comparison_id: uuid.UUID) -> ReportComparisonView:
        row = self.repo.get_owned_comparison(
            owner_user_id=_user_id(user), comparison_id=comparison_id
        )
        if row is None:
            raise comparison_not_found()
        return self._verified_comparison_view(row)

    def _report_contracts(self, *, user, report_id):
        row = self.repo.get_owned_report(owner_user_id=_user_id(user), report_id=report_id)
        if row is None:
            raise report_not_found()
        snapshot, _ = verify_report(row)
        if snapshot.contract_reference is None:
            return missing_contracts()
        return self._verify_archive(row)

    def report_contracts(self, *, user, report_id, limit, offset):
        verification = self._report_contracts(user=user, report_id=report_id)
        refs = contract_report_refs(verification)
        return [ref.model_dump(mode="json") for ref in refs[offset : offset + limit]], {
            "limit": limit,
            "offset": offset,
            "total": len(refs),
            "check": {key: value for key, value in verification.check.items() if key != "results"},
        }

    def report_contract(self, *, user, report_id, contract_id):
        verification = self._report_contracts(user=user, report_id=report_id)
        row = verification.rows.get(str(contract_id))
        if row is None:
            raise AgentReportError("CONTRACT_NOT_FOUND", "contract not found", status_code=404)
        metadata = next(
            ref for ref in contract_report_refs(verification) if ref.contract_id == contract_id
        )
        return {**metadata.model_dump(mode="json"), "projection": safe_contract_projection(row)}

    def verify_contracts(self, *, user, report_id):
        return self._report_contracts(user=user, report_id=report_id).check

    def _same_report_or_conflict(
        self, row: AgentResearchReport, request_hash: str
    ) -> ResearchReportView:
        if row.request_hash != request_hash:
            raise idempotency_conflict()
        return self._verified_report_view(row)

    def _verify_archive(self, row, *, deadline=None):
        if row.snapshot_json.get("archive_reference") is not None:
            try:
                archive = AgentArchiveApplication(self.db, self.settings)
                if deadline is not None:
                    archive._deadline = deadline
                _, snapshot, bundle = archive.report_bundle(
                    user=type("Owner", (), {"id": row.owner_user_id})(), report_id=row.id
                )
                reference = row.snapshot_json.get("contract_reference")
                if reference is not None:
                    verification = AgentFrozenContractApplication(
                        self.db, self.settings
                    ).check_turn(
                        owner_id=row.owner_user_id,
                        turn_id=row.source_turn_id,
                        expected_reference=reference,
                        deadline=deadline,
                        base_bundle=bundle,
                    )
                    _, source_contract = verify_report(row)
                    refs = contract_report_refs(verification)
                    if (
                        reference["contract_ids_hash"] != verification.manifest.contract_ids_hash
                        or canonical_hash([ref.model_dump(mode="json") for ref in refs])
                        != reference["contract_refs_hash"]
                        or report_contract_gaps(source_contract, verification)
                        != source_contract.gap_codes
                    ):
                        raise AgentReportError(
                            "REPORT_CONTRACT_BINDING_MISMATCH",
                            "frozen contract binding changed",
                            status_code=409,
                        )
                    return verification
            except AgentArchiveError as exc:
                raise AgentReportError(exc.code, str(exc), status_code=exc.status_code) from exc
        return None

    def _verified_report_view(self, row):
        result = _report_view(row)
        verification = self._verify_archive(row)
        if verification is not None:
            result.contract_check = verification.check
        return result

    def _same_comparison_or_conflict(
        self, row: AgentResearchReportComparison, request_hash: str
    ) -> ReportComparisonView:
        if row.request_hash != request_hash:
            raise idempotency_conflict()
        return self._verified_comparison_view(row)

    def _verified_comparison_view(self, row: AgentResearchReportComparison) -> ReportComparisonView:
        left = self.repo.get_owned_report(
            owner_user_id=row.owner_user_id, report_id=row.left_report_id
        )
        right = self.repo.get_owned_report(
            owner_user_id=row.owner_user_id, report_id=row.right_report_id
        )
        verify_comparison(row, left, right)
        deadline = (
            time.monotonic() + self.settings.agent_config.frozen_contract.verify_timeout_seconds
        )
        left_frozen = self._verify_archive(left, deadline=deadline)
        right_frozen = self._verify_archive(right, deadline=deadline)
        if row.policy_version == CONTRACT_COMPARISON_POLICY_VERSION:
            left_snapshot, _ = verify_report(left)
            right_snapshot, _ = verify_report(right)
            limit = row.result_json.get("max_facts")
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
                raise AgentReportError(
                    "REPORT_COMPARISON_INTEGRITY_ERROR",
                    "frozen resource limit invalid",
                    status_code=409,
                )
            _, _, expected = compare_frozen_research(
                left_snapshot,
                right_snapshot,
                left_verification=left_frozen,
                right_verification=right_frozen,
                max_facts=limit,
                comparison_intent=row.result_json["comparison_intent"],
                comparison_mode=row.result_json["comparison_mode"],
            )
            actual = {
                key: value
                for key, value in row.result_json.items()
                if key
                not in {
                    "left_report_id",
                    "right_report_id",
                    "left_snapshot_hash",
                    "right_snapshot_hash",
                    "source_contract_hashes",
                }
            }
            if canonical_hash(expected) != canonical_hash(actual):
                raise AgentReportError(
                    "REPORT_COMPARISON_INTEGRITY_ERROR",
                    "frozen comparison contract mismatch",
                    status_code=409,
                )
        return _comparison_view(row)


def _user_id(user: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(user.id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AgentReportError("UNAUTHORIZED", "invalid user identity", status_code=401) from exc


def _archive_recheck_allows_report(snapshot, result: dict[str, Any]) -> bool:
    if result["integrity"]["status"] != "VERIFIED":
        return False
    rows = {item["claim_id"]: item for item in result["fact_recheck"]["results"]}
    if len(rows) != len(snapshot.claims):
        return False
    allowed_comparison_gaps = {
        "EXACT_M14_BUNDLE_NOT_ARCHIVED",
        "FROZEN_M15_WINDOW_LINEAGE_REQUIRED",
        "COMPARISON_CONTEXT_REQUIRED",
    }
    for claim in snapshot.claims:
        row = rows.get(claim.claim_id)
        if row is None or row["status"] == "MISMATCH":
            return False
        if claim.claim_type == "INFERENCE":
            if row["support_status"] != "VERIFIED":
                return False
        elif row["facts_status"] != "VERIFIED":
            return False
        if claim.claim_type == "COMPARISON" and row["status"] != "VERIFIED":
            if not set(row["reason_codes"]) & allowed_comparison_gaps:
                return False
        elif claim.claim_type != "COMPARISON" and row["status"] != "VERIFIED":
            return False
    return True


def _report_view(row: AgentResearchReport) -> ResearchReportView:
    snapshot, contract = verify_report(row)
    return ResearchReportView(
        report_id=row.id,
        report_type=row.report_type,
        report_version=row.report_version,
        title=row.title,
        as_of_date=row.as_of_date,
        source_chat_id=row.source_chat_id,
        source_message_id=row.source_message_id,
        source_turn_id=row.source_turn_id,
        parent_report_id=row.parent_report_id,
        source_answer_status=row.source_answer_status,
        answer_status=row.source_answer_status,
        snapshot_level=snapshot.snapshot_level,
        snapshot_hash=row.snapshot_hash,
        snapshot=snapshot,
        source_contract=contract,
        archived_at=row.archived_at,
        created_at=row.created_at,
    )


def _report_summary(row: AgentResearchReport) -> ResearchReportSummary:
    return ResearchReportSummary(
        report_id=row.id,
        report_type=row.report_type,
        report_version=row.report_version,
        title=row.title,
        source_chat_id=row.source_chat_id,
        source_message_id=row.source_message_id,
        as_of_date=row.as_of_date,
        source_answer_status=row.source_answer_status,
        snapshot_hash=row.snapshot_hash,
        archived_at=row.archived_at,
        created_at=row.created_at,
    )


def _comparison_view(row: AgentResearchReportComparison) -> ReportComparisonView:
    legacy = row.policy_version not in {
        REPORT_COMPARISON_POLICY_VERSION,
        CONTRACT_COMPARISON_POLICY_VERSION,
    }
    allowed = (
        not legacy
        and row.state == "COMPARABLE"
        and (
            row.policy_version != CONTRACT_COMPARISON_POLICY_VERSION
            or row.result_json.get("comparison_permissions", {}).get("allowed") is True
        )
    )
    display_result = {
        **row.result_json,
        "facts": [
            {
                key: value
                for key, value in fact.items()
                if not (
                    key in {"delta", "delta_semantics"}
                    and (
                        not allowed
                        or fact.get("pair_status") != "COMPARABLE"
                        or (
                            row.policy_version == CONTRACT_COMPARISON_POLICY_VERSION
                            and fact.get("comparison_permission", {}).get("allowed") is not True
                        )
                    )
                )
            }
            for fact in row.result_json.get("facts", [])
        ],
    }
    if not allowed:
        display_result["delta_policy"] = "DISABLED"
    return ReportComparisonView(
        comparison_id=row.id,
        left_report_id=row.left_report_id,
        right_report_id=row.right_report_id,
        policy_version=row.policy_version,
        state=row.state,
        reason_codes=list(row.reason_codes_json),
        result=dict(row.result_json),
        left_snapshot_hash=row.left_snapshot_hash,
        right_snapshot_hash=row.right_snapshot_hash,
        comparison_hash=row.comparison_hash,
        created_at=row.created_at,
        display_safety={
            "legacy_policy": legacy,
            "delta_allowed": allowed,
            "warnings": ["LEGACY_COMPARISON_POLICY_RECREATE_REQUIRED"] if legacy else [],
        },
        display_result=display_result,
    )


def _audit(
    *,
    user: Any,
    operation: str,
    object_id: uuid.UUID,
    request_id: str | None,
    source_type: str,
    content_hash: str,
    status: str,
    started: float,
) -> None:
    logger.bind(
        operation=operation,
        object_id=str(object_id),
        owner_hash=user_audit_hash(user),
        request_id=request_id,
        duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        source_type=source_type,
        content_hash=content_hash,
        status=status,
    ).info("agent_research_report")
