import json
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from app.core.agent_config import AgentConfig
from app.core.agent_db import agent_db_session
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.domain.agent.chat_errors import AgentChatError
from app.main import app
from app.models.agent_chat import (
    AgentChatMessage,
    AgentChatSession,
    AgentChatToolCall,
    AgentChatTurn,
)
from app.models.auth import AppUser, AuthSession
from app.models.market_data import DataQualityDaily
from app.services.agent.chat.application import AgentChatApplication
from app.services.agent.llm.contracts import (
    ChatMessage,
    LLMResponse,
    LLMTool,
    LLMUsage,
    ProviderError,
    ToolCall,
)
from app.services.agent.llm.fake import FakeLLMProvider
from app.services.auth.dependencies import SESSION_COOKIE
from app.services.auth.service import session_token_hash
from fastapi.testclient import TestClient


def _enabled_settings() -> Settings:
    settings = get_settings().model_copy(deep=True)
    payload = settings.agent_config.model_dump(mode="json")
    payload.update({"mode": "llm_chat", "llm_enabled": True})
    settings.agent_config = AgentConfig.model_validate(payload)
    return settings


def _enabled_settings_with_context_limit(limit: int) -> Settings:
    settings = _enabled_settings()
    payload = settings.agent_config.model_dump(mode="json")
    payload["llm"]["max_context_messages"] = limit
    settings.agent_config = AgentConfig.model_validate(payload)
    return settings


def _user(db, *, suffix: str) -> AppUser:
    user = AppUser(
        id=uuid.uuid4(),
        username=f"m16_2_{suffix}_{uuid.uuid4().hex[:8]}",
        password_hash="test-only",
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    return user


def _clarification_provider() -> FakeLLMProvider:
    return FakeLLMProvider([_clarification_response()])


def _clarification_response() -> LLMResponse:
    return LLMResponse(
        final_text=json.dumps(
            {
                "answer": "请提供需要分析的回测 run_id。",
                "evidence_ids": [],
                "warnings": [],
                "needs_clarification": True,
            },
            ensure_ascii=False,
        ),
        usage=LLMUsage(prompt_tokens=8, completion_tokens=6),
    )


def _cleanup_users(*user_ids: uuid.UUID) -> None:
    with SessionLocal() as db:
        chat_ids = select_ids(
            db,
            sa.select(AgentChatSession.id).where(
                AgentChatSession.owner_user_id.in_(user_ids)
            ),
        )
        if chat_ids:
            turn_ids = select_ids(
                db,
                sa.select(AgentChatTurn.id).where(AgentChatTurn.session_id.in_(chat_ids)),
            )
            if turn_ids:
                db.execute(
                    sa.delete(AgentChatToolCall).where(
                        AgentChatToolCall.turn_id.in_(turn_ids)
                    )
                )
                db.execute(sa.delete(AgentChatTurn).where(AgentChatTurn.id.in_(turn_ids)))
            db.execute(
                sa.delete(AgentChatMessage).where(
                    AgentChatMessage.session_id.in_(chat_ids)
                )
            )
            db.execute(
                sa.delete(AgentChatSession).where(AgentChatSession.id.in_(chat_ids))
            )
        db.execute(sa.delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
        db.execute(sa.delete(AppUser).where(AppUser.id.in_(user_ids)))
        db.commit()


def select_ids(db, statement) -> list[uuid.UUID]:
    return list(db.scalars(statement).all())


def test_chat_owner_isolation_idempotency_and_running_turn_conflict() -> None:
    settings = _enabled_settings()
    with SessionLocal() as db:
        owner = _user(db, suffix="owner")
        other = _user(db, suffix="other")
        owner_id, other_id = owner.id, other.id
        try:
            service = AgentChatApplication(
                db, settings, provider=_clarification_provider()
            )
            chat = service.create_chat(user=owner, title="回测研究")
            first = service.send_message(
                user=owner,
                chat_id=chat.chat_id,
                content="这个回测怎么样？",
                request_id="idempotent-request",
            )
            repeated = service.send_message(
                user=owner,
                chat_id=chat.chat_id,
                content="不同文本也不得创建重复消息",
                request_id="idempotent-request",
            )
            assert repeated == first
            assert first.status == "INSUFFICIENT_EVIDENCE"
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(AgentChatTurn)
                .where(AgentChatTurn.session_id == chat.chat_id)
            ) == 1
            assert db.scalar(
                sa.select(sa.func.count())
                .select_from(AgentChatMessage)
                .where(AgentChatMessage.session_id == chat.chat_id)
            ) == 2

            with pytest.raises(AgentChatError) as hidden:
                service.get_chat(
                    user=other,
                    chat_id=chat.chat_id,
                    limit=20,
                    offset=0,
                )
            assert hidden.value.code == "CHAT_NOT_FOUND"
            assert service.list_chats(user=other, limit=20, offset=0)[1] == 0

            running, _ = service._start_turn(
                owner_id=owner.id,
                chat_id=chat.chat_id,
                content="正在处理",
                request_id="running-request",
            )
            with SessionLocal() as competing_db:
                competing = AgentChatApplication(
                    competing_db,
                    settings,
                    provider=_clarification_provider(),
                )
                with pytest.raises(AgentChatError) as conflict:
                    competing.send_message(
                        user=SimpleNamespace(id=owner.id),
                        chat_id=chat.chat_id,
                        content="并发问题",
                        request_id="concurrent-request",
                    )
                assert conflict.value.code == "CHAT_CONFLICT"
            service._fail_turn(running.id, "TEST_CLEANUP", {})
        finally:
            db.close()
            _cleanup_users(owner_id, other_id)


def test_context_truncation_is_reported_and_provider_failure_finishes_turn() -> None:
    settings = _enabled_settings_with_context_limit(2)
    scripted = FakeLLMProvider(
        [
            _clarification_response(),
            _clarification_response(),
            ProviderError("LLM_TIMEOUT", "LLM provider request timed out", status_code=504),
        ]
    )
    with SessionLocal() as db:
        owner = _user(db, suffix="context")
        owner_id = owner.id
        try:
            service = AgentChatApplication(db, settings, provider=scripted)
            chat = service.create_chat(user=owner, title="上下文边界")
            service.send_message(
                user=owner,
                chat_id=chat.chat_id,
                content="第一轮问题",
                request_id="context-1",
            )
            second = service.send_message(
                user=owner,
                chat_id=chat.chat_id,
                content="第二轮问题",
                request_id="context-2",
            )
            assert "CONTEXT_TRUNCATED" in second.warnings
            assert [item.role for item in scripted.calls[1]["messages"]] == [
                "system",
                "assistant",
                "user",
            ]

            with pytest.raises(AgentChatError) as failed:
                service.send_message(
                    user=owner,
                    chat_id=chat.chat_id,
                    content="触发超时",
                    request_id="context-timeout",
                )
            assert failed.value.code == "LLM_TIMEOUT"
            turn = db.scalar(
                sa.select(AgentChatTurn).where(
                    AgentChatTurn.session_id == chat.chat_id,
                    AgentChatTurn.request_id == "context-timeout",
                )
            )
            assert turn is not None
            assert turn.status == "FAILED"
            assert turn.error_code == "LLM_TIMEOUT"
            assert service.repo.running_turn(chat_id=chat.chat_id) is None
        finally:
            db.close()
            _cleanup_users(owner_id)


class CoverageProvider:
    def __init__(self, target_date: date) -> None:
        self.target_date = target_date
        self.calls = 0

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[LLMTool],
        *,
        timeout: float,
        request_id: str,
    ) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            assert {tool.name for tool in tools} == {
                "data.coverage",
                "market.snapshot",
                "sector.top",
                "theme.top",
                "opportunity.list",
                "backtest.summary",
                "performance.summary",
                "walk_forward.summary",
            }
            return LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="coverage-call",
                        name="data.coverage",
                        arguments={
                            "start_date": self.target_date.isoformat(),
                            "end_date": self.target_date.isoformat(),
                        },
                    )
                ]
            )
        payload = json.loads(messages[-1].content)
        evidence_id = payload["evidence"][0]["evidence_id"]
        return LLMResponse(
            final_text=json.dumps(
                {
                    "answer": "该日期的数据覆盖证据存在，但需结合质量警告解读。",
                    "evidence_ids": [evidence_id],
                    "warnings": ["不构成收益承诺"],
                    "needs_clarification": False,
                },
                ensure_ascii=False,
            )
        )


def test_chat_tool_call_uses_read_only_session_and_persists_only_chat_audit() -> None:
    settings = _enabled_settings()
    target_date = date(2098, 12, 30)
    dataset = f"m16_2_{uuid.uuid4().hex[:16]}"
    with SessionLocal() as db:
        owner = _user(db, suffix="tools")
        owner_id = owner.id
        quality = DataQualityDaily(
            trade_date=target_date,
            dataset=dataset,
            expected_rows=1,
            actual_rows=1,
            coverage_rate=1.0,
            status="PASS",
        )
        db.add(quality)
        db.commit()
        quality_id = quality.id
        before = db.scalar(
            sa.select(sa.func.count()).select_from(DataQualityDaily).where(
                DataQualityDaily.id == quality_id
            )
        )
        try:
            with agent_db_session(settings) as read_db:
                assert read_db.scalar(sa.text("SHOW transaction_read_only")) == "on"

            service = AgentChatApplication(
                db, settings, provider=CoverageProvider(target_date)
            )
            chat = service.create_chat(user=owner, title="覆盖率研究")
            result = service.send_message(
                user=owner,
                chat_id=chat.chat_id,
                content="这个日期的数据质量如何？",
                request_id="coverage-request",
            )
            assert result.status == "COMPLETED"
            assert len(result.citations) == 1
            assert result.citations[0].tool_name == "data.coverage"
            audit = db.scalar(
                sa.select(AgentChatToolCall).where(
                    AgentChatToolCall.tool_call_id == "coverage-call"
                )
            )
            assert audit is not None
            assert audit.status == "READY"
            assert audit.evidence_ids_json == [result.citations[0].evidence_id]
            assert db.scalar(
                sa.select(sa.func.count()).select_from(DataQualityDaily).where(
                    DataQualityDaily.id == quality_id
                )
            ) == before
        finally:
            db.execute(sa.delete(DataQualityDaily).where(DataQualityDaily.id == quality_id))
            db.commit()
            db.close()
            _cleanup_users(owner_id)


def test_real_session_cookie_authentication_and_cross_user_404() -> None:
    raw_owner_token = f"owner-{uuid.uuid4()}"
    raw_other_token = f"other-{uuid.uuid4()}"
    with SessionLocal() as db:
        owner = _user(db, suffix="cookie_owner")
        other = _user(db, suffix="cookie_other")
        owner_id, other_id = owner.id, other.id
        now = datetime.now(UTC)
        db.add_all(
            [
                AuthSession(
                    user_id=owner.id,
                    token_hash=session_token_hash(raw_owner_token),
                    expires_at=now + timedelta(hours=1),
                    last_seen_at=now,
                ),
                AuthSession(
                    user_id=other.id,
                    token_hash=session_token_hash(raw_other_token),
                    expires_at=now + timedelta(hours=1),
                    last_seen_at=now,
                ),
            ]
        )
        db.commit()
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/agent/chats",
            json={"title": "Cookie 鉴权"},
            cookies={SESSION_COOKIE: raw_owner_token},
        )
        assert created.status_code == 201
        chat_id = created.json()["data"]["chat_id"]
        owner_view = client.get(
            f"/api/v1/agent/chats/{chat_id}",
            cookies={SESSION_COOKIE: raw_owner_token},
        )
        assert owner_view.status_code == 200
        hidden = client.get(
            f"/api/v1/agent/chats/{chat_id}",
            cookies={SESSION_COOKIE: raw_other_token},
        )
        assert hidden.status_code == 404
        assert hidden.json()["detail"]["code"] == "CHAT_NOT_FOUND"
    finally:
        _cleanup_users(owner_id, other_id)


def test_m16_2_postgresql_constraints_and_indexes_exist() -> None:
    with SessionLocal() as db:
        assert db.scalar(
            sa.text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname='uq_agent_chat_turn_running_session'"
            )
        ) == 1
        assert db.scalar(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname='uq_agent_chat_turn_request'"
            )
        ) == 1
        assert db.scalar(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname='ck_agent_chat_message_content_length'"
            )
        ) == 1
        assert db.scalar(
            sa.text(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname LIKE 'ck_agent_chat_%_ck_agent_chat_%'"
            )
        ) == 0
