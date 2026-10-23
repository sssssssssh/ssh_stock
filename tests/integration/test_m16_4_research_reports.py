import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
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
from app.services.agent.report.canonical import canonical_hash
from app.services.agent.report.comparison_policy import REPORT_COMPARISON_POLICY_VERSION
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
                            "path": "records.0.market_score",
                            "value": value,
                            "unit": "score",
                            "trade_date": "2026-10-10",
                            "entity": "market",
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
                    "entity_id": "market",
                    "as_of_date": date(2026, 10, 10).isoformat(),
                    "calc_version": "market-v1",
                    "config_hash": "c" * 64,
                    "source_hash": "b" * 64,
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


def _cleanup(*user_ids: uuid.UUID, session_factory=None) -> None:
    with (session_factory or SessionLocal)() as db:
        comparison_ids = sa.select(AgentResearchReportComparison.id).where(
            AgentResearchReportComparison.owner_user_id.in_(user_ids)
        )
        db.execute(
            sa.delete(AgentResearchReportComparison).where(
                AgentResearchReportComparison.id.in_(comparison_ids)
            )
        )
        db.execute(
            sa.delete(AgentResearchReport).where(AgentResearchReport.owner_user_id.in_(user_ids))
        )
        chat_ids = list(
            db.scalars(
                sa.select(AgentChatSession.id).where(AgentChatSession.owner_user_id.in_(user_ids))
            )
        )
        if chat_ids:
            db.execute(sa.delete(AgentChatTurn).where(AgentChatTurn.session_id.in_(chat_ids)))
            db.execute(sa.delete(AgentChatMessage).where(AgentChatMessage.session_id.in_(chat_ids)))
            db.execute(sa.delete(AgentChatSession).where(AgentChatSession.id.in_(chat_ids)))
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
            assert comparison.policy_version == REPORT_COMPARISON_POLICY_VERSION
            read_comparison = service.get_comparison(
                user=owner, comparison_id=comparison.comparison_id
            )
            assert read_comparison.result == comparison.result
            with pytest.raises(AgentReportError) as hidden_comparison:
                service.get_comparison(user=other, comparison_id=comparison.comparison_id)
            assert hidden_comparison.value.code == "REPORT_COMPARISON_NOT_FOUND"
            assert (
                service.create_comparison(user=owner, body=comparison_body).comparison_id
                == comparison.comparison_id
            )
            with pytest.raises(AgentReportError) as intent_conflict:
                service.create_comparison(
                    user=owner,
                    body=comparison_body.model_copy(
                        update={"comparison_intent": "CROSS_ENTITY_SAME_DATE"}
                    ),
                )
            assert intent_conflict.value.code == "IDEMPOTENCY_CONFLICT"

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
            return service.create_report(user=SimpleNamespace(id=owner_id), body=body).report_id

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


def test_postgres_history_is_frozen_and_corruption_injection_stays_in_memory() -> None:
    with SessionLocal() as db:
        owner = _user(db, "integrity")
        owner_id = owner.id
        try:
            service = AgentReportApplication(db, get_settings())
            views = []
            for index, value in enumerate(("0.10", "0.12")):
                chat_id, message_id = _source(db, owner, value=value)
                views.append(
                    service.create_report(
                        user=owner,
                        body=CreateResearchReport(
                            source_chat_id=chat_id,
                            source_message_id=message_id,
                            report_type="market_review",
                            request_id=f"integrity-{index}",
                        ),
                    )
                )
            a, b = views
            body = CreateReportComparison(
                left_report_id=a.report_id, right_report_id=b.report_id, request_id="new-comparison"
            )
            comparison = service.create_comparison(user=owner, body=body)
            row = db.get(AgentResearchReport, a.report_id)
            original = deepcopy(row.snapshot_json)
            corrupted = deepcopy(original)
            corrupted["claims"][0]["structured_facts"][0]["value"] = "999"
            # set_committed_value simulates a corrupted read; no SQL writes or trigger disabling.
            from sqlalchemy.orm.attributes import set_committed_value

            set_committed_value(row, "snapshot_json", corrupted)
            for operation in (
                lambda: service.get_report(user=owner, report_id=a.report_id),
                lambda: service.export_report(
                    user=owner, report_id=a.report_id, export_format="html"
                ),
                lambda: service.create_comparison(
                    user=owner, body=body.model_copy(update={"request_id": "corrupt"})
                ),
                lambda: service.create_report(
                    user=owner,
                    body=CreateResearchReport(
                        source_chat_id=a.source_chat_id,
                        source_message_id=a.source_message_id,
                        report_type="market_review",
                        request_id="integrity-0",
                    ),
                ),
            ):
                with pytest.raises(AgentReportError) as error:
                    operation()
                assert error.value.code == "REPORT_SNAPSHOT_INTEGRITY_ERROR"
            db.refresh(row)
            assert row.snapshot_json == original
            comparison_row = db.get(AgentResearchReportComparison, comparison.comparison_id)
            original_result = deepcopy(comparison_row.result_json)
            corrupted_result = deepcopy(original_result)
            corrupted_result["facts"][0]["delta"] = "999"
            set_committed_value(comparison_row, "result_json", corrupted_result)
            with pytest.raises(AgentReportError) as error:
                service.get_comparison(user=owner, comparison_id=comparison.comparison_id)
            assert error.value.code == "REPORT_COMPARISON_INTEGRITY_ERROR"
            db.refresh(comparison_row)
            assert comparison_row.result_json == original_result

            # A real legacy record is inserted once, then always read without UPDATE/recompute.
            frozen = {**original_result, "policy_version": "m16.2.2-comparison-v1"}
            old_request = body.model_copy(update={"request_id": "legacy-comparison"})
            old = service.repo.add_comparison(
                owner_user_id=owner.id,
                left_report_id=a.report_id,
                right_report_id=b.report_id,
                request_id=old_request.request_id,
                request_hash=canonical_hash(
                    old_request.model_dump(mode="json", exclude={"request_id", "comparison_intent"})
                ),
                policy_version="m16.2.2-comparison-v1",
                state=comparison.state,
                reason_codes_json=comparison.reason_codes,
                result_json=frozen,
                left_snapshot_hash=a.snapshot_hash,
                right_snapshot_hash=b.snapshot_hash,
                comparison_hash=canonical_hash(frozen),
            )
            db.commit()
            replay = service.create_comparison(user=owner, body=old_request)
            assert replay.comparison_id == old.id
            assert replay.result == frozen
            assert replay.display_safety["delta_allowed"] is False
            assert "delta" not in replay.display_result["facts"][0]
            statements = []

            def capture_statement(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)

            sa.event.listen(db.bind, "before_cursor_execute", capture_statement)
            try:
                service.get_comparison(user=SimpleNamespace(id=owner_id), comparison_id=old.id)
            finally:
                sa.event.remove(db.bind, "before_cursor_execute", capture_statement)
            assert len(statements) == 3  # comparison + left snapshot + right snapshot, no N+1
            assert all(statement.lstrip().startswith("SELECT") and
                       "FROM agent_research_report" in statement for statement in statements)
            db.refresh(old)
            assert old.result_json == frozen
            # Exercise database owner FK, request uniqueness and state CHECK, not only metadata.
            other = _user(db, "constraint-owner")
            try:
                for changes in (
                    {"owner_user_id": other.id, "request_id": "cross-owner"},
                    {"request_id": old.request_id},
                    {"request_id": "invalid-state", "state": "INVALID"},
                ):
                    values = {
                        "owner_user_id": owner_id,
                        "left_report_id": a.report_id, "right_report_id": b.report_id,
                        "request_id": "constraint", "request_hash": "a" * 64,
                        "policy_version": "m16.2.2-comparison-v1", "state": "COMPARABLE",
                        "reason_codes_json": [], "result_json": frozen,
                        "left_snapshot_hash": a.snapshot_hash,
                        "right_snapshot_hash": b.snapshot_hash,
                        "comparison_hash": canonical_hash(frozen),
                        **changes,
                    }
                    with pytest.raises(DBAPIError):
                        db.execute(sa.insert(AgentResearchReportComparison).values(**values))
                        db.commit()
                    db.rollback()
            finally:
                _cleanup(other.id)
            for model, object_id, values in (
                (AgentResearchReport, a.report_id, {"snapshot_json": corrupted}),
                (AgentResearchReportComparison, old.id, {"result_json": corrupted_result}),
            ):
                with pytest.raises(DBAPIError):
                    db.execute(sa.update(model).where(model.id == object_id).values(**values))
                    db.commit()
                db.rollback()
            assert service.archive_report(user=owner, report_id=a.report_id).archived_at
        finally:
            db.rollback()
            _cleanup(owner_id)
