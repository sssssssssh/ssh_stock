import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from app.core.agent_db import agent_db_session
from app.core.db import SessionLocal
from app.domain.agent.chat_errors import AgentChatError
from app.domain.agent.contracts import AgentToolResult, Readiness
from app.domain.agent.policy import serialized_result
from app.models.agent_archive import AgentToolResultArchive, AgentTurnArchiveManifest
from app.models.agent_chat import (
    AgentChatMessage,
    AgentChatSession,
    AgentChatToolCall,
    AgentChatTurn,
)
from app.models.market_data import MarketDaily
from app.repositories.agent_archive import AgentArchiveRepository
from app.services.agent.archive.application import AgentArchiveApplication
from app.services.agent.archive.recheck import recheck_archive
from app.services.agent.chat.application import AgentChatApplication
from app.services.agent.chat.orchestrator import CapturedToolPayload
from app.services.agent.evidence import evidence_ref
from app.services.agent.llm.contracts import LLMResponse, ToolCall
from app.services.agent.llm.fake import FakeLLMProvider
from test_m16_2_agent_chat import _enabled_settings, _user
from test_m16_5_archive_migration import cleanup_archives


def archive_settings():
    settings = _enabled_settings()
    settings.agent_config.archive.enabled = True
    return settings


def fixture_payload(name):
    records = (
        [{"ts_code": "A", "score": "80"}, {"ts_code": "B", "score": "70"}]
        if name == "opportunity.list"
        else [{"market_score": "60"}]
    )
    refs = [
        evidence_ref(
            layer="FACTOR_TREND",
            source_type="derived_record",
            entity_id=row.get("ts_code", "market"),
            date_value=date(2026, 1, 2),
            calc_version="fixture_v1",
            config_hash="a" * 64,
            content=row,
            quality_status="PASS",
        )
        for row in records
    ]
    result = AgentToolResult(
        tool_name=name,
        status="READY",
        as_of_date=date(2026, 1, 2),
        identity={"calc_version": "fixture_v1", "config_hash": "a" * 64},
        records=records,
        evidence=refs,
        readiness=Readiness(ready=True, code="READY"),
    )
    return CapturedToolPayload(
        serialized_result(result, max_output_bytes=65536),
        {ref.evidence_id: ref._archive_projection for ref in refs},
    )


def provider(*, cached=False):
    stock = fixture_payload("opportunity.list")
    market = fixture_payload("market.snapshot")
    facts = [(stock, index, "score", row["ts_code"]) for index, row in enumerate(stock["records"])]
    facts.append((market, 0, "market_score", "market"))
    claims = [
        {
            "claim_id": f"c{number}",
            "claim_type": "FACT",
            "text": "verified",
            "evidence_ids": [payload["evidence"][index]["evidence_id"]],
            "structured_facts": [
                {
                    "path": f"records.{index}.{path}",
                    "value": payload["records"][index][path],
                    "unit": "score",
                    "trade_date": "2026-01-02",
                    "entity": entity,
                    "sample_role": "LIVE",
                }
            ],
        }
        for number, (payload, index, path, entity) in enumerate(facts)
    ]
    calls = [
        ToolCall(id="stocks", name="opportunity.list", arguments={"trade_date": "2026-01-02"}),
        ToolCall(id="market", name="market.snapshot", arguments={"trade_date": "2026-01-02"}),
    ]
    if cached:
        calls.append(
            ToolCall(
                id="stock-cache", name="opportunity.list", arguments={"trade_date": "2026-01-02"}
            )
        )
    return FakeLLMProvider(
        [
            LLMResponse(tool_calls=calls),
            LLMResponse(
                final_text=json.dumps(
                    {
                        "answer": "verified",
                        "evidence_ids": [],
                        "claims": claims,
                        "warnings": [],
                        "needs_clarification": False,
                    }
                )
            ),
        ]
    )


class FixtureChat(AgentChatApplication):
    executions = 0

    def _execute_tool(self, **kwargs):
        self.executions += 1
        return fixture_payload(kwargs["tool_name"])


def count(db, model, owner_id):
    return db.scalar(
        sa.select(sa.func.count()).select_from(model).where(model.owner_user_id == owner_id)
    )


def test_partial_verified_archives_only_accepted_claim_bindings_and_no_rejected_number():
    with SessionLocal() as db:
        user = _user(db, suffix="partial-archive")
        owner_id = user.id
        try:
            fake = provider()
            raw = json.loads(fake._responses[1].final_text)
            raw["claims"][0]["structured_facts"][0]["value"] = "999"
            fake._responses[1].final_text = json.dumps(raw)
            service = FixtureChat(db, archive_settings(), provider=fake)
            chat = service.create_chat(user=user, title="Partial verified")
            answer = service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="partial"
            )
            assert answer.answer_status == "PARTIAL_VERIFIED" and len(answer.verified_claims) == 2
            manifest = db.scalar(
                sa.select(AgentTurnArchiveManifest).where(
                    AgentTurnArchiveManifest.owner_user_id == owner_id
                )
            )
            assert len(manifest.manifest_json["required_evidence_ids"]) == 2
            assert "999" not in db.get(AgentChatMessage, answer.message_id).content
            result = AgentArchiveApplication(db, archive_settings()).turn_archive(
                user=user, chat_id=chat.chat_id, request_id="partial"
            )
            assert result["archive_status"] == "COMPLETE" and result["archived_evidence_count"] == 2
        finally:
            cleanup_archives(owner_id)


def test_post_commit_lost_response_preserves_completed_manifest_and_idempotent_recovery():
    class LostResponseChat(FixtureChat):
        def _complete_turn(self, **kwargs):
            super()._complete_turn(**kwargs)
            raise RuntimeError("synthetic network loss after durable commit")

    with SessionLocal() as db:
        user = _user(db, suffix="lost-response")
        owner_id = user.id
        try:
            settings = archive_settings()
            service = LostResponseChat(db, settings, provider=provider())
            chat = service.create_chat(user=user, title="Lost response")
            with pytest.raises(AgentChatError):
                service.send_message(
                    user=user, chat_id=chat.chat_id, content="核验", request_id="lost"
                )
            replay = FixtureChat(db, settings, provider=FakeLLMProvider([]))
            answer = replay.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="lost"
            )
            assert replay.executions == 0 and answer.answer_status == "COMPLETED"
            status = replay.get_turn_status(user=user, chat_id=chat.chat_id, request_id="lost")
            assert status.status == "COMPLETED" and status.answer.message_id == answer.message_id
            assert count(db, AgentTurnArchiveManifest, owner_id) == 1
        finally:
            cleanup_archives(owner_id)


def test_two_actual_calls_three_evidence_atomic_archive_and_idempotent_cached_replay():
    with SessionLocal() as db:
        user = _user(db, suffix="m16-5")
        owner_id = user.id
        try:
            fake = provider(cached=True)
            service = FixtureChat(db, archive_settings(), provider=fake)
            chat = service.create_chat(user=user, title="Archive")
            answer = service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="archive"
            )
            assert answer.answer_status == "COMPLETED"
            assert len(answer.verified_claims) == 3 and service.executions == 2
            manifest = db.scalar(
                sa.select(AgentTurnArchiveManifest).where(
                    AgentTurnArchiveManifest.owner_user_id == owner_id
                )
            )
            assert manifest.archive_status == "COMPLETE"
            assert len(manifest.manifest_json["required_evidence_ids"]) == 3
            assert len(manifest.manifest_json["tools"]) == 3
            tools = db.scalars(
                sa.select(AgentToolResultArchive).where(
                    AgentToolResultArchive.owner_user_id == owner_id
                )
            ).all()
            assert (
                next(
                    item for item in tools if item.tool_call_id == "stock-cache"
                ).cache_origin_call_id
                == "stocks"
            )
            assert db.get(AgentChatTurn, manifest.turn_id).assistant_message_id == answer.message_id
            replay = service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="archive"
            )
            assert replay.message_id == answer.message_id
            assert service.executions == 2 and len(fake.calls) == 2
            assert count(db, AgentTurnArchiveManifest, owner_id) == 1
        finally:
            db.rollback()
            cleanup_archives(owner_id)


@pytest.mark.parametrize("fault", ["storage", "deadline", "limit"])
def test_archive_failure_rolls_back_assistant_and_manifest_and_marks_failed(monkeypatch, fault):
    clock = SimpleNamespace(value=0.0)
    original = AgentArchiveRepository.insert_draft

    def inject(self, **kwargs):
        original(self, **kwargs)
        if fault == "storage":
            raise RuntimeError("synthetic transaction failure")
        clock.value = 100.0

    if fault in {"storage", "deadline"}:
        monkeypatch.setattr(AgentArchiveRepository, "insert_draft", inject)
    with SessionLocal() as db:
        user = _user(db, suffix=f"archive-{fault}")
        owner_id = user.id
        try:
            settings = archive_settings()
            if fault == "limit":
                settings.agent_config.archive.max_turn_bytes = 1  # inject a runtime budget fault
            service = FixtureChat(db, settings, provider=provider(), monotonic=lambda: clock.value)
            chat = service.create_chat(user=user, title="failure")
            with pytest.raises(AgentChatError) as error:
                service.send_message(
                    user=user, chat_id=chat.chat_id, content="核验", request_id="failure"
                )
            assert (
                error.value.code
                == {
                    "storage": "ARCHIVE_PERSIST_FAILED",
                    "deadline": "TOTAL_DEADLINE_EXCEEDED",
                    "limit": "ARCHIVE_LIMIT_EXCEEDED",
                }[fault]
            )
            turn = db.scalar(
                sa.select(AgentChatTurn).where(AgentChatTurn.session_id == chat.chat_id)
            )
            assert turn.status == "FAILED" and turn.assistant_message_id is None
            assert count(db, AgentTurnArchiveManifest, owner_id) == 0
            assert count(db, AgentToolResultArchive, owner_id) == 0
            assert (
                db.scalar(
                    sa.select(sa.func.count())
                    .select_from(AgentChatMessage)
                    .where(
                        AgentChatMessage.session_id == chat.chat_id,
                        AgentChatMessage.role == "ASSISTANT",
                    )
                )
                == 0
            )
            assert (
                db.scalar(
                    sa.select(sa.func.count())
                    .select_from(AgentChatToolCall)
                    .where(AgentChatToolCall.turn_id == turn.id)
                )
                == 2
            )
        finally:
            db.rollback()
            cleanup_archives(owner_id)


def test_same_request_race_has_one_archive_and_one_assistant():
    entered, release = Event(), Event()

    class BlockingProvider(FakeLLMProvider):
        def complete(self, *args, **kwargs):
            if not self.calls:
                entered.set()
                assert release.wait(10)
            return super().complete(*args, **kwargs)

    with SessionLocal() as db:
        user = _user(db, suffix="archive-race")
        owner_id = user.id
        service = FixtureChat(db, archive_settings(), provider=provider())
        chat = service.create_chat(user=user, title="race")
    fake = provider()
    blocking = BlockingProvider(list(fake._responses))

    def send():
        with SessionLocal() as db:
            return FixtureChat(db, archive_settings(), provider=blocking).send_message(
                user=SimpleNamespace(id=owner_id),
                chat_id=chat.chat_id,
                content="same",
                request_id="race",
            )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(send)
            assert entered.wait(10)
            with SessionLocal() as db:
                service = FixtureChat(db, archive_settings(), provider=provider())
                with pytest.raises(AgentChatError) as error:
                    service.send_message(
                        user=SimpleNamespace(id=owner_id),
                        chat_id=chat.chat_id,
                        content="same",
                        request_id="race",
                    )
                assert error.value.code == "CHAT_CONFLICT"
            release.set()
            answer = pending.result(timeout=15)
        with SessionLocal() as db:
            assert count(db, AgentTurnArchiveManifest, owner_id) == 1
            assert (
                db.scalar(
                    sa.select(sa.func.count())
                    .select_from(AgentChatTurn)
                    .where(AgentChatTurn.session_id == chat.chat_id)
                )
                == 1
            )
            assert db.get(AgentChatMessage, answer.message_id).status == "COMPLETED"
    finally:
        release.set()
        cleanup_archives(owner_id)


def test_offline_archive_is_readonly_owner_scoped_and_independent_of_current_market_data():
    settings = archive_settings()
    with SessionLocal() as db:
        user = _user(db, suffix="offline")
        other = _user(db, suffix="offline-other")
        owner_id, other_id = user.id, other.id
        try:
            service = FixtureChat(db, settings, provider=provider())
            chat = service.create_chat(user=user, title="offline")
            service.send_message(
                user=user, chat_id=chat.chat_id, content="核验", request_id="offline"
            )
            archive = AgentArchiveApplication(db, settings)
            turn = db.scalar(
                sa.select(AgentChatTurn).where(AgentChatTurn.session_id == chat.chat_id)
            )
            before = recheck_archive(
                archive.load_bundle(owner_id, turn.id), config=settings.agent_config.archive
            )
            # A current/latest derived fact changes after capture; verifier must never read it.
            db.add(
                MarketDaily(
                    trade_date=date(2098, 1, 2),
                    market_score=999,
                    calc_version="synthetic-latest",
                    config_hash="d" * 64,
                )
            )
            db.commit()
            owned_chat = db.get(AgentChatSession, chat.chat_id)
            owned_chat.status = "ARCHIVED"
            db.commit()
            statements = []

            def observe(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)

            sa.event.listen(db.bind, "before_cursor_execute", observe)
            try:
                with agent_db_session(settings) as readonly:
                    archive = AgentArchiveApplication(readonly, settings)
                    summary = archive.turn_archive(
                        user=SimpleNamespace(id=owner_id),
                        chat_id=chat.chat_id,
                        request_id="offline",
                    )
                    after = recheck_archive(
                        archive.load_bundle(owner_id, turn.id), config=settings.agent_config.archive
                    )
                    with pytest.raises(AgentChatError) as hidden:
                        archive.turn_archive(
                            user=SimpleNamespace(id=other_id),
                            chat_id=chat.chat_id,
                            request_id="offline",
                        )
                    assert hidden.value.status_code == 404
            finally:
                sa.event.remove(db.bind, "before_cursor_execute", observe)
            assert before == after
            assert summary["archive_status"] == "COMPLETE"
            assert summary["integrity"]["status"] == "VERIFIED"
            assert len(summary["evidence"]) == 3
            assert all(
                "market_daily" not in sql.lower() and "portfolio_" not in sql.lower()
                for sql in statements
            )
            assert not any(
                sql.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE"))
                for sql in statements
            )
            assert "payload_json" not in str(summary) and "source_projection_json" not in str(
                summary
            )
        finally:
            db.rollback()
            db.execute(
                sa.delete(MarketDaily).where(
                    MarketDaily.trade_date == date(2098, 1, 2),
                    MarketDaily.calc_version == "synthetic-latest",
                )
            )
            db.commit()
            cleanup_archives(owner_id)
            cleanup_archives(other_id)
