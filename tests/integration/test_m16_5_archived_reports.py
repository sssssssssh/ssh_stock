from copy import deepcopy

import pytest
from app.core.db import SessionLocal
from app.domain.agent.archive import VerifyArchiveRequest
from app.domain.agent.report import CreateResearchReport
from app.domain.agent.report_errors import AgentReportError
from app.models.agent_chat import AgentChatMessage
from app.services.agent.archive.application import AgentArchiveApplication
from app.services.agent.report.application import AgentReportApplication
from test_m16_2_agent_chat import _user
from test_m16_5_archive_migration import cleanup_archives
from test_m16_5_chat_archive import FixtureChat, archive_settings, provider


def test_new_report_manifest_binding_owner_archived_chat_replay_exports_and_read_integrity():
    with SessionLocal() as db:
        user, other = _user(db, suffix="report-v3"), _user(db, suffix="other-v3")
        owner_id, other_id = user.id, other.id
        try:
            settings = archive_settings()
            chat_service = FixtureChat(db, settings, provider=provider())
            chat = chat_service.create_chat(user=user, title="Frozen evidence")
            answer = chat_service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="frozen-report"
            )
            service = AgentReportApplication(db, settings)
            body = CreateResearchReport(
                source_chat_id=chat.chat_id,
                source_message_id=answer.message_id,
                report_type="market_review",
                request_id="report",
            )
            report = service.create_report(user=user, body=body)
            assert report.report_version == "m16.5-v1"
            assert report.snapshot.archive_reference.archive_status == "COMPLETE"
            assert service.create_report(user=user, body=body).report_id == report.report_id
            original = deepcopy(report.snapshot.model_dump(mode="json"))
            archive = AgentArchiveApplication(db, settings)
            rows, meta = archive.report_evidence(
                user=user, report_id=report.report_id, limit=2, offset=0
            )
            assert len(rows) == 2 and meta["total"] == 3
            detail = archive.evidence_detail(
                user=user, report_id=report.report_id, evidence_id=rows[0]["evidence_id"]
            )
            assert detail["frozen_facts"] and "payload_json" not in detail
            result = archive.verify_report_archive(
                user=user, report_id=report.report_id, body=VerifyArchiveRequest()
            )
            assert result["verification_level"] == "FACT_REVERIFIED"
            for fmt in ("markdown", "html"):
                content, _, _ = service.export_report(
                    user=user, report_id=report.report_id, export_format=fmt
                )
                assert "FROZEN_FACT_RECHECK" in content and "不是原算法重跑" in content
            chat_service.archive_chat(user=user, chat_id=chat.chat_id)
            assert (
                archive.report_evidence(user=user, report_id=report.report_id, limit=20, offset=0)[
                    1
                ]["archive_status"]
                == "COMPLETE"
            )
            with pytest.raises(AgentReportError) as error:
                archive.report_evidence(user=other, report_id=report.report_id, limit=20, offset=0)
            assert error.value.status_code == 404
            message = db.get(AgentChatMessage, answer.message_id)
            original_content = message.content
            message.content = "tampered source"
            db.commit()
            for read in (
                lambda: service.get_report(user=user, report_id=report.report_id),
                lambda: service.export_report(
                    user=user, report_id=report.report_id, export_format="html"
                ),
                lambda: service.create_report(user=user, body=body),
                lambda: service.archive_report(user=user, report_id=report.report_id),
            ):
                with pytest.raises(AgentReportError) as error:
                    read()
                assert error.value.status_code == 409
            message.content = original_content
            db.commit()
            assert (
                service.get_report(user=user, report_id=report.report_id).snapshot.model_dump(
                    mode="json"
                )
                == original
            )
        finally:
            cleanup_archives(owner_id)
            cleanup_archives(other_id)
