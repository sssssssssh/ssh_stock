from __future__ import annotations

import time
import uuid
from typing import Any

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
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
from app.services.agent.report.canonical import canonical_hash, storage_json_bytes
from app.services.agent.report.comparison import compare_report_snapshots
from app.services.agent.report.comparison_policy import REPORT_COMPARISON_POLICY_VERSION
from app.services.agent.report.integrity import verify_comparison, verify_report
from app.services.agent.report.render import render_html, render_markdown
from app.services.agent.report.snapshot import REPORT_VERSION, build_report_snapshot


class AgentReportApplication:
    def __init__(self, db: Session, settings: Settings) -> None:
        if settings.agent_config is None:
            raise RuntimeError("agent config is not loaded")
        self.db = db
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
                report_version=REPORT_VERSION,
                title=snapshot.title,
                as_of_date=snapshot.as_of_date,
                source_answer_status=snapshot.source_answer_status,
                snapshot_json=snapshot_json,
                snapshot_hash=canonical_hash(snapshot_json),
                source_contract_json=contract.model_dump(mode="json"),
            )
            self.db.commit()
            self.db.refresh(row)
        except IntegrityError:
            self.db.rollback()
            existing = self.repo.get_by_request(owner_user_id=owner_id, request_id=body.request_id)
            if existing is None:
                raise
            return self._same_report_or_conflict(existing, request_hash)
        result = _report_view(row)
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
        return _report_view(row)

    def archive_report(self, *, user: Any, report_id: uuid.UUID) -> ResearchReportView:
        started = time.monotonic()
        row = self.repo.get_owned_report(
            owner_user_id=_user_id(user), report_id=report_id, for_update=True
        )
        if row is None:
            raise report_not_found()
        verify_report(row)
        self.repo.archive(row)
        self.db.commit()
        self.db.refresh(row)
        result = _report_view(row)
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
        if export_format == "markdown":
            return (
                render_markdown(report.snapshot, report.snapshot_hash),
                "text/markdown; charset=utf-8",
                f"research-report-{report.report_id}.md",
            )
        if export_format == "html":
            return (
                render_html(report.snapshot, report.snapshot_hash),
                "text/html; charset=utf-8",
                f"research-report-{report.report_id}.html",
            )
        raise AgentReportError(
            "INVALID_EXPORT_FORMAT", "unsupported export format", status_code=422
        )

    def create_comparison(self, *, user: Any, body: CreateReportComparison) -> ReportComparisonView:
        started = time.monotonic()
        owner_id = _user_id(user)
        request_content = body.model_dump(mode="json", exclude={"request_id"})
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
        state, reasons, result = compare_report_snapshots(
            left_snapshot,
            right_snapshot,
            max_facts=self.config.max_comparison_facts,
            left_contract=left_contract,
            right_contract=right_contract,
            comparison_intent=body.comparison_intent,
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
                policy_version=REPORT_COMPARISON_POLICY_VERSION,
                state=state,
                reason_codes_json=reasons,
                result_json=frozen,
                left_snapshot_hash=left.snapshot_hash,
                right_snapshot_hash=right.snapshot_hash,
                comparison_hash=comparison_hash,
            )
            self.db.commit()
            self.db.refresh(row)
        except IntegrityError:
            self.db.rollback()
            existing = self.repo.get_comparison_by_request(
                owner_user_id=owner_id, request_id=body.request_id
            )
            if existing is None:
                raise
            return self._same_comparison_or_conflict(existing, request_hash)
        result = self._verified_comparison_view(row)
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

    @staticmethod
    def _same_report_or_conflict(row: AgentResearchReport, request_hash: str) -> ResearchReportView:
        if row.request_hash != request_hash:
            raise idempotency_conflict()
        return _report_view(row)

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
        return _comparison_view(row)


def _user_id(user: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(user.id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AgentReportError("UNAUTHORIZED", "invalid user identity", status_code=401) from exc


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
    legacy = row.policy_version != REPORT_COMPARISON_POLICY_VERSION
    display_result = {
        **row.result_json,
        "facts": [
            {
                key: value
                for key, value in fact.items()
                if not (legacy and key in {"delta", "delta_semantics"})
            }
            for fact in row.result_json.get("facts", [])
        ],
    }
    if legacy:
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
            "delta_allowed": not legacy and row.state == "COMPARABLE",
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
