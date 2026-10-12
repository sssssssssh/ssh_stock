import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.domain.agent.report import CreateReportComparison, CreateResearchReport
from app.domain.agent.report_errors import AgentReportError
from app.models.agent_chat import AgentChatMessage, AgentChatSession, AgentChatTurn
from app.models.agent_report import AgentResearchReport, AgentResearchReportComparison
from app.models.auth import AppUser
from app.services.agent.report.application import AgentReportApplication
from sqlalchemy.exc import DBAPIError


def _user(db, suffix: str) -> AppUser:
    user = AppUser(
        id=uuid.uuid4(),
        username=f"m16_4_{suffix}_{uuid.uuid4().hex[:8]}",
        password_hash="test-only",
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    return user


def _source(db, user: AppUser, *, value: str) -> tuple[uuid.UUID, uuid.UUID]:
    chat = AgentChatSession(owner_user_id=user.id, title="M16.4 source")
    db.add(chat)
    db.flush()
    user_message = AgentChatMessage(
        session_id=chat.id,
        role="USER",
        content="请核验回测收益",
        status="COMPLETED",
        sequence_no=1,
        metadata_json={},
    )
    db.add(user_message)
    db.flush()
    evidence_id = f"ev-{value}"
    assistant = AgentChatMessage(
        session_id=chat.id,
        role="ASSISTANT",
        content="收益已核验",
        status="COMPLETED",
        sequence_no=2,
        metadata_json={
            "answer_status": "COMPLETED",
            "verified_claims": [
                {
                    "claim_id": "claim-1",
                    "claim_type": "FACT",
                    "text": "收益已核验",
                    "evidence_ids": [evidence_id],
                    "structured_facts": [
                        {
                            "path": "records.0.market.market_score",
                            "value": value,
                            "unit": "score",
                            "trade_date": "2026-10-10",
                            "entity": f"run-{value}",
                            "sample_role": "LIVE",
                        }
                    ],
                    "quality_status": "PASS",
                    "reason_codes": [],
                }
            ],
            "citations": [
                {
                    "marker": "[1]",
                    "evidence_id": evidence_id,
                    "evidence_version": "v2",
                    "tool_name": "market.snapshot",
                    "entity_id": f"run-{value}",
                    "as_of_date": date(2026, 10, 10).isoformat(),
                    "calc_version": "market-v1",
                    "config_hash": "c" * 64,
                }
            ],
        },
    )
    db.add(assistant)
    db.flush()
    db.add(
        AgentChatTurn(
            session_id=chat.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant.id,
            request_id=f"source-{value}",
            request_content_hash="a" * 64,
            status="COMPLETED",
            model="test-model",
            trace_id=uuid.uuid4(),
            usage_json={},
        )
    )
    db.commit()
    return chat.id, assistant.id


def _cleanup(*user_ids: uuid.UUID) -> None:
    with SessionLocal() as db:
        comparison_ids = sa.select(AgentResearchReportComparison.id).where(
            AgentResearchReportComparison.owner_user_id.in_(user_ids)
        )
        db.execute(
            sa.delete(AgentResearchReportComparison).where(
                AgentResearchReportComparison.id.in_(comparison_ids)
            )
        )
        db.execute(
            sa.delete(AgentResearchReport).where(
                AgentResearchReport.owner_user_id.in_(user_ids)
            )
        )
        chat_ids = list(
            db.scalars(
                sa.select(AgentChatSession.id).where(
                    AgentChatSession.owner_user_id.in_(user_ids)
                )
            )
        )
        if chat_ids:
            db.execute(
                sa.delete(AgentChatTurn).where(AgentChatTurn.session_id.in_(chat_ids))
            )
            db.execute(
                sa.delete(AgentChatMessage).where(AgentChatMessage.session_id.in_(chat_ids))
            )
            db.execute(
                sa.delete(AgentChatSession).where(AgentChatSession.id.in_(chat_ids))
            )
        db.execute(sa.delete(AppUser).where(AppUser.id.in_(user_ids)))
        db.commit()


def test_report_owner_idempotency_immutability_archive_and_comparison() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        owner = _user(db, "owner")
        other = _user(db, "other")
        owner_id, other_id = owner.id, other.id
        try:
            first_chat, first_message = _source(db, owner, value="0.10")
            second_chat, second_message = _source(db, owner, value="0.12")
            service = AgentReportApplication(db, settings)
            first_body = CreateResearchReport(
                source_chat_id=first_chat,
                source_message_id=first_message,
                report_type="strategy_review",
                request_id="report-request-1",
            )
            first = service.create_report(user=owner, body=first_body)
            repeated = service.create_report(user=owner, body=first_body)
            assert repeated.report_id == first.report_id
            with pytest.raises(AgentReportError) as conflict:
                service.create_report(
                    user=owner,
                    body=first_body.model_copy(update={"title": "different"}),
                )
            assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
            with pytest.raises(AgentReportError) as hidden:
                service.get_report(user=other, report_id=first.report_id)
            assert hidden.value.code == "REPORT_NOT_FOUND"

            second = service.create_report(
                user=owner,
                body=CreateResearchReport(
                    source_chat_id=second_chat,
                    source_message_id=second_message,
                    report_type="strategy_review",
                    request_id="report-request-2",
                ),
            )
            comparison_body = CreateReportComparison(
                left_report_id=first.report_id,
                right_report_id=second.report_id,
                request_id="comparison-request-1",
            )
            comparison = service.create_comparison(user=owner, body=comparison_body)
            assert comparison.state == "COMPARABLE"
            assert comparison.result["facts"][0]["delta"] == "0.02"
            assert (
                service.create_comparison(user=owner, body=comparison_body).comparison_id
                == comparison.comparison_id
            )

            archived = service.archive_report(user=owner, report_id=first.report_id)
            assert archived.archived_at is not None
            archived_again = service.archive_report(user=owner, report_id=first.report_id)
            assert archived_again.archived_at == archived.archived_at

            source_chat = db.get(AgentChatSession, first_chat)
            assert source_chat is not None
            source_chat.status = "ARCHIVED"
            db.commit()
            assert service.get_report(user=owner, report_id=first.report_id).snapshot_hash

            with pytest.raises(DBAPIError):
                db.execute(
                    sa.update(AgentResearchReport)
                    .where(AgentResearchReport.id == first.report_id)
                    .values(title="forbidden rewrite")
                )
                db.commit()
            db.rollback()

            other_reports, other_total = service.list_reports(
                user=SimpleNamespace(id=other_id),
                limit=20,
                offset=0,
                include_archived=True,
            )
            assert other_reports == []
            assert other_total == 0
        finally:
            db.rollback()
            _cleanup(owner_id, other_id)


def test_concurrent_same_request_creates_one_report() -> None:
    with SessionLocal() as db:
        owner = _user(db, "concurrent")
        owner_id = owner.id
        chat_id, message_id = _source(db, owner, value="0.15")
    body = CreateResearchReport(
        source_chat_id=chat_id,
        source_message_id=message_id,
        report_type="strategy_review",
        request_id="concurrent-report-request",
    )

    def create() -> uuid.UUID:
        with SessionLocal() as worker_db:
            service = AgentReportApplication(worker_db, get_settings())
            return service.create_report(
                user=SimpleNamespace(id=owner_id), body=body
            ).report_id

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            report_ids = list(pool.map(lambda _: create(), range(2)))
        assert report_ids[0] == report_ids[1]
        with SessionLocal() as verify_db:
            assert (
                verify_db.scalar(
                    sa.select(sa.func.count())
                    .select_from(AgentResearchReport)
                    .where(
                        AgentResearchReport.owner_user_id == owner_id,
                        AgentResearchReport.request_id == "concurrent-report-request",
                    )
                )
                == 1
            )
    finally:
        _cleanup(owner_id)
