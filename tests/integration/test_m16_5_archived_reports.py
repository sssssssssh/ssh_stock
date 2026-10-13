import json
from copy import deepcopy

import pytest
import sqlalchemy as sa
from app.core.db import SessionLocal
from app.domain.agent.archive import VerifyArchiveRequest
from app.domain.agent.report import CreateResearchReport
from app.domain.agent.report_errors import AgentReportError
from app.models.agent_archive import AgentTurnArchiveManifest
from app.models.agent_chat import AgentChatMessage
from app.models.agent_report import AgentResearchReport
from app.services.agent.archive.application import AgentArchiveApplication
from app.services.agent.report.application import AgentReportApplication
from test_m16_2_agent_chat import _user
from test_m16_5_archive_migration import cleanup_archives
from test_m16_5_chat_archive import FixtureChat, archive_settings, provider


def mixed_provider():
    fake = provider()
    raw = json.loads(fake._responses[1].final_text)
    fact = raw["claims"][0]
    raw["claims"].append(
        {
            "claim_id": "inference-market",
            "claim_type": "INFERENCE",
            "text": "untrusted model conclusion",
            "evidence_ids": list(fact["evidence_ids"]),
            "structured_facts": [],
            "inference": {
                "hypothesis": "POSSIBLE_REGIME_SENSITIVITY",
                "supporting_claim_ids": [fact["claim_id"]],
                "uncertainties": ["CAUSALITY_NOT_ESTABLISHED"],
                "limitations": ["HISTORICAL_EVIDENCE_ONLY"],
            },
        }
    )
    fake._responses[1].final_text = json.dumps(raw)
    return fake


def test_mixed_claim_report_creates_reads_exports_archives_and_replays():
    with SessionLocal() as db:
        user = _user(db, suffix="mixed-v3")
        owner_id = user.id
        try:
            settings = archive_settings()
            chat_service = FixtureChat(db, settings, provider=mixed_provider())
            chat = chat_service.create_chat(user=user, title="Mixed claims")
            answer = chat_service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="mixed-turn"
            )
            assert [claim.claim_type for claim in answer.verified_claims][-1] == "INFERENCE"
            service = AgentReportApplication(db, settings)
            body = CreateResearchReport(
                source_chat_id=chat.chat_id,
                source_message_id=answer.message_id,
                report_type="market_review",
                request_id="mixed-report",
            )
            report = service.create_report(user=user, body=body)
            assert report.report_version == "m16.5-v1"
            assert (
                service.get_report(user=user, report_id=report.report_id).report_id
                == report.report_id
            )
            assert service.create_report(user=user, body=body).report_id == report.report_id
            for fmt in ("markdown", "html"):
                content, _, _ = service.export_report(
                    user=user, report_id=report.report_id, export_format=fmt
                )
                assert "FROZEN_FACT_RECHECK" in content
            result = AgentArchiveApplication(db, settings).verify_report_archive(
                user=user, report_id=report.report_id, body=VerifyArchiveRequest()
            )
            inference = next(
                item for item in result["fact_recheck"]["results"]
                if item["claim_id"] == "inference-market"
            )
            assert inference["support_status"] == "VERIFIED"
            assert inference["facts_applicable"] is False
            assert service.archive_report(user=user, report_id=report.report_id).archived_at
        finally:
            db.rollback()
            cleanup_archives(owner_id)


def test_mixed_claim_precommit_validation_rolls_back_and_same_request_retries(monkeypatch):
    with SessionLocal() as db:
        user = _user(db, suffix="mixed-rollback")
        owner_id = user.id
        try:
            settings = archive_settings()
            chat_service = FixtureChat(db, settings, provider=mixed_provider())
            chat = chat_service.create_chat(user=user, title="Mixed rollback")
            answer = chat_service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="mixed-rollback"
            )
            service = AgentReportApplication(db, settings)
            body = CreateResearchReport(
                source_chat_id=chat.chat_id,
                source_message_id=answer.message_id,
                report_type="market_review",
                request_id="same-report-request",
            )
            from app.services.agent.report import application as report_application

            original_bind = report_application.bind_archive

            def corrupt_binding(snapshot, contract, manifest):
                original_bind(snapshot, contract, manifest)
                next(
                    claim for claim in snapshot.claims if claim.claim_type == "INFERENCE"
                ).verified_fact_refs.append("forged:records.0.market_score")
                contract.frozen_fields = sorted(
                    {ref for claim in snapshot.claims for ref in claim.verified_fact_refs}
                )
                snapshot.source_contract_hash = report_application.canonical_hash(
                    contract.model_dump(mode="json")
                )

            with monkeypatch.context() as patch:
                patch.setattr(report_application, "bind_archive", corrupt_binding)
                with pytest.raises(AgentReportError) as error:
                    service.create_report(user=user, body=body)
            assert error.value.code == "INFERENCE_FIELD_REFS_INVALID"
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(AgentResearchReport)
                .where(AgentResearchReport.owner_user_id == owner_id)
            ) == 0
            report = service.create_report(user=user, body=body)
            assert service.create_report(user=user, body=body).report_id == report.report_id
        finally:
            db.rollback()
            cleanup_archives(owner_id)


def test_report_commit_failure_rolls_back_without_touching_archive(monkeypatch):
    with SessionLocal() as db:
        user = _user(db, suffix="mixed-commit-failure")
        owner_id = user.id
        try:
            settings = archive_settings()
            chat_service = FixtureChat(db, settings, provider=mixed_provider())
            chat = chat_service.create_chat(user=user, title="Commit failure")
            answer = chat_service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="commit-turn"
            )
            service = AgentReportApplication(db, settings)
            body = CreateResearchReport(
                source_chat_id=chat.chat_id,
                source_message_id=answer.message_id,
                report_type="market_review",
                request_id="commit-report",
            )
            def fail_commit():
                raise sa.exc.SQLAlchemyError("synthetic commit failure")

            with monkeypatch.context() as patch:
                patch.setattr(db, "commit", fail_commit)
                with pytest.raises(AgentReportError) as error:
                    service.create_report(user=user, body=body)
            assert error.value.code == "REPORT_CREATE_FAILED"
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(AgentResearchReport)
                .where(AgentResearchReport.owner_user_id == owner_id)
            ) == 0
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(AgentTurnArchiveManifest)
                .where(AgentTurnArchiveManifest.owner_user_id == owner_id)
            ) == 1
            assert service.create_report(user=user, body=body).report_version == "m16.5-v1"
        finally:
            db.rollback()
            cleanup_archives(owner_id)


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
