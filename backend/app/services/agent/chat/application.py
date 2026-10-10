from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.agent_db import agent_db_session
from app.core.config import Settings
from app.domain.agent.chat import (
    ChatAnswer,
    ChatMessageView,
    ChatSessionSummary,
)
from app.domain.agent.chat_errors import (
    AgentChatError,
    chat_conflict,
    chat_not_found,
    llm_disabled,
)
from app.domain.agent.policy import user_audit_hash
from app.models.agent_chat import AgentChatSession, AgentChatTurn
from app.repositories.agent_chat import AgentChatRepository
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.adapters.opportunities import OpportunityAgentAdapter
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.application import AgentApplicationService
from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from app.services.agent.chat.orchestrator import ToolCallAudit, ToolOrchestrator
from app.services.agent.chat.prompt import SYSTEM_PROMPT
from app.services.agent.llm.contracts import ChatMessage, LLMProvider
from app.services.agent.llm.factory import build_llm_provider
from app.services.agent.registry import AgentToolRegistry, build_registry


class AgentChatApplication:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        provider: LLMProvider | None = None,
    ) -> None:
        if settings.agent_config is None:
            raise RuntimeError("agent config is not loaded")
        self.db = db
        self.settings = settings
        self.config = settings.agent_config
        self.repo = AgentChatRepository(db)
        self._provider = provider

    def create_chat(self, *, user: Any, title: str | None) -> ChatSessionSummary:
        owner_id = _user_id(user)
        normalized = (title or "新研究会话").strip()
        if not normalized or len(normalized) > 160:
            raise AgentChatError("INVALID_ARGUMENT", "invalid chat title", status_code=422)
        chat = self.repo.create_session(owner_user_id=owner_id, title=normalized)
        self.db.commit()
        return _session_summary(chat)

    def list_chats(
        self, *, user: Any, limit: int, offset: int
    ) -> tuple[list[ChatSessionSummary], int]:
        rows, total = self.repo.session_page(
            owner_user_id=_user_id(user), limit=limit, offset=offset
        )
        return [_session_summary(row) for row in rows], total

    def get_chat(
        self,
        *,
        user: Any,
        chat_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[ChatSessionSummary, list[ChatMessageView], int]:
        chat = self.repo.get_owned_session(
            chat_id=chat_id, owner_user_id=_user_id(user)
        )
        if chat is None:
            raise chat_not_found()
        messages, total = self.repo.message_page(
            chat_id=chat_id, limit=limit, offset=offset
        )
        return _session_summary(chat), [_message_view(row) for row in messages], total

    def archive_chat(self, *, user: Any, chat_id: uuid.UUID) -> ChatSessionSummary:
        chat = self.repo.get_owned_session(
            chat_id=chat_id,
            owner_user_id=_user_id(user),
            for_update=True,
        )
        if chat is None:
            self.db.rollback()
            raise chat_not_found()
        if self.repo.running_turn(chat_id=chat_id) is not None:
            self.db.rollback()
            raise chat_conflict("cannot archive a chat with a running turn")
        self.repo.archive(chat)
        self.db.commit()
        return _session_summary(chat)

    def send_message(
        self,
        *,
        user: Any,
        chat_id: uuid.UUID,
        content: str,
        request_id: str,
    ) -> ChatAnswer:
        if not self.config.llm_enabled:
            raise llm_disabled()
        normalized = content.strip()
        if not normalized or len(normalized) > self.config.llm.max_user_message_chars:
            raise AgentChatError(
                "INVALID_ARGUMENT", "invalid user message length", status_code=422
            )
        owner_id = _user_id(user)
        turn, existing = self._start_turn(
            owner_id=owner_id,
            chat_id=chat_id,
            content=normalized,
            request_id=request_id,
        )
        if existing is not None:
            return existing

        context_warning: list[str] = []
        orchestrator: ToolOrchestrator | None = None
        try:
            messages, truncated = self.repo.recent_messages(
                chat_id=chat_id, limit=self.config.llm.max_context_messages
            )
            provider_messages = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
            provider_messages.extend(
                ChatMessage(
                    role="user" if message.role == "USER" else "assistant",
                    content=message.content,
                )
                for message in messages
            )
            if truncated:
                context_warning.append("CONTEXT_TRUNCATED")
            self.db.rollback()

            provider = self._provider or build_llm_provider(self.settings)
            registry = self._schema_registry()
            orchestrator = ToolOrchestrator(
                provider=provider,
                registry=registry,
                config=self.config.llm,
                execute_tool=lambda name, args, call_id: self._execute_tool(
                    user=user,
                    request_id=request_id,
                    tool_call_id=call_id,
                    tool_name=name,
                    arguments=args,
                ),
                audit_tool_call=lambda audit: self._persist_tool_call(turn.id, audit),
            )
            orchestration = orchestrator.run(
                messages=provider_messages,
                request_id=request_id,
            )
            compiled = EvidenceCompiler(
                max_answer_chars=self.config.llm.max_answer_chars
            ).compile(
                final_text=orchestration.final_text,
                tool_results=orchestration.tool_results,
                inherited_warnings=context_warning + orchestration.warnings,
            )
            answer = self._complete_turn(
                chat_id=chat_id,
                turn_id=turn.id,
                trace_id=turn.trace_id,
                answer=compiled.answer,
                status=(
                    "INSUFFICIENT_EVIDENCE"
                    if compiled.insufficient_evidence
                    else "COMPLETED"
                ),
                citations=[item.model_dump(mode="json") for item in compiled.citations],
                warnings=compiled.warnings,
                tool_calls=[
                    item.model_dump(mode="json") for item in orchestration.tool_calls
                ],
                usage=orchestration.usage.model_dump(mode="json"),
            )
        except AgentChatError as exc:
            usage = (
                orchestrator.last_usage.model_dump(mode="json")
                if orchestrator is not None
                else {}
            )
            self._fail_turn(turn.id, exc.code, usage)
            self._audit_turn(user, request_id, turn.trace_id, "FAILED", exc.code)
            raise
        except Exception as exc:
            usage = (
                orchestrator.last_usage.model_dump(mode="json")
                if orchestrator is not None
                else {}
            )
            self._fail_turn(turn.id, "INTERNAL_ERROR", usage)
            self._audit_turn(user, request_id, turn.trace_id, "FAILED", "INTERNAL_ERROR")
            raise AgentChatError(
                "INTERNAL_ERROR", "Agent chat execution failed", status_code=500
            ) from exc

        self._audit_turn(user, request_id, turn.trace_id, "COMPLETED", None)
        return answer

    def _start_turn(
        self,
        *,
        owner_id: uuid.UUID,
        chat_id: uuid.UUID,
        content: str,
        request_id: str,
    ) -> tuple[Any, ChatAnswer | None]:
        try:
            chat = self.repo.get_owned_session(
                chat_id=chat_id,
                owner_user_id=owner_id,
                for_update=True,
            )
            if chat is None:
                self.db.rollback()
                raise chat_not_found()
            if chat.status != "ACTIVE":
                self.db.rollback()
                raise chat_conflict("chat is archived")
            existing = self.repo.get_turn_by_request(
                chat_id=chat_id, request_id=request_id
            )
            if existing is not None:
                if existing.status == "COMPLETED":
                    result = self._answer_from_turn(existing)
                    self.db.rollback()
                    return existing, result
                self.db.rollback()
                raise chat_conflict(
                    "request_id already belongs to a running or failed turn"
                )
            if self.repo.running_turn(chat_id=chat_id) is not None:
                self.db.rollback()
                raise chat_conflict()
            sequence_no = self.repo.next_sequence(chat_id=chat_id)
            user_message = self.repo.add_message(
                chat_id=chat_id,
                role="USER",
                content=content,
                sequence_no=sequence_no,
            )
            turn = self.repo.add_turn(
                chat_id=chat_id,
                user_message_id=user_message.id,
                request_id=request_id,
                model=self.config.llm.model,
                trace_id=uuid.uuid4(),
            )
            chat.updated_at = datetime.now(UTC)
            self.db.add(chat)
            self.db.commit()
            return turn, None
        except IntegrityError as exc:
            self.db.rollback()
            raise chat_conflict() from exc

    def _schema_registry(self) -> AgentToolRegistry:
        with agent_db_session(self.settings) as db:
            return build_registry(
                MarketDataAgentAdapter(db, self.settings),
                OpportunityAgentAdapter(db, self.settings),
                ResearchAgentAdapter(db),
                config=self.config,
            )

    def _execute_tool(
        self,
        *,
        user: Any,
        request_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        with agent_db_session(self.settings) as db:
            return AgentApplicationService(db, self.settings).execute(
                tool_name=tool_name,
                raw_input=arguments,
                request_id=f"{request_id}:{tool_call_id}",
                user=user,
            )

    def _persist_tool_call(self, turn_id: uuid.UUID, audit: ToolCallAudit) -> None:
        self.repo.add_tool_call(
            turn_id=turn_id,
            tool_call_id=audit.tool_call_id,
            tool_name=audit.tool_name,
            args_hash=audit.args_hash,
            status=audit.status,
            evidence_ids=audit.evidence_ids,
            duration_ms=audit.duration_ms,
            error_code=audit.error_code,
            cache_reused=audit.cache_reused,
        )
        self.db.commit()

    def _complete_turn(
        self,
        *,
        chat_id: uuid.UUID,
        turn_id: uuid.UUID,
        trace_id: uuid.UUID,
        answer: str,
        status: str,
        citations: list[dict[str, Any]],
        warnings: list[str],
        tool_calls: list[dict[str, Any]],
        usage: dict[str, Any],
    ) -> ChatAnswer:
        metadata = {
            "status": status,
            "citations": citations,
            "warnings": warnings,
            "tool_calls": tool_calls,
            "usage": usage,
            "trace_id": str(trace_id),
        }
        turn = self.db.get(AgentChatTurn, turn_id)
        if turn is None or turn.status != "RUNNING":
            self.db.rollback()
            raise chat_conflict("turn is no longer running")
        assistant = self.repo.add_message(
            chat_id=chat_id,
            role="ASSISTANT",
            content=answer,
            sequence_no=self.repo.next_sequence(chat_id=chat_id),
            metadata=metadata,
        )
        self.repo.complete_turn(
            turn=turn,
            assistant_message_id=assistant.id,
            usage=usage,
        )
        chat = self.db.get(AgentChatSession, chat_id)
        if chat is not None:
            chat.updated_at = datetime.now(UTC)
            self.db.add(chat)
        self.db.commit()
        return ChatAnswer(
            chat_id=chat_id,
            message_id=assistant.id,
            status=status,
            answer=answer,
            citations=citations,
            warnings=warnings,
            tool_calls=tool_calls,
            usage=usage,
            trace_id=trace_id,
        )

    def _fail_turn(
        self, turn_id: uuid.UUID, error_code: str, usage: dict[str, Any]
    ) -> None:
        try:
            self.repo.fail_turn(turn_id=turn_id, error_code=error_code, usage=usage)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _answer_from_turn(self, turn: Any) -> ChatAnswer:
        if turn.assistant_message_id is None:
            raise chat_conflict("completed turn has no assistant message")
        message = self.repo.get_message(turn.assistant_message_id)
        if message is None:
            raise chat_conflict("completed turn response is unavailable")
        metadata = dict(message.metadata_json or {})
        return ChatAnswer(
            chat_id=turn.session_id,
            message_id=message.id,
            status=metadata.get("status", "COMPLETED"),
            answer=message.content,
            citations=metadata.get("citations", []),
            warnings=metadata.get("warnings", []),
            tool_calls=metadata.get("tool_calls", []),
            usage=metadata.get("usage", {}),
            trace_id=metadata.get("trace_id", str(turn.trace_id)),
        )

    @staticmethod
    def _audit_turn(
        user: Any,
        request_id: str,
        trace_id: uuid.UUID,
        status: str,
        error_code: str | None,
    ) -> None:
        logger.bind(
            request_id=request_id,
            trace_id=str(trace_id),
            user_hash=user_audit_hash(user),
            status=status,
            error_code=error_code,
        ).info("agent_chat_turn")


def _user_id(user: Any) -> uuid.UUID:
    value = getattr(user, "id", None)
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise AgentChatError(
            "UNAUTHORIZED", "authenticated user identity is invalid", status_code=401
        ) from exc


def _session_summary(chat: Any) -> ChatSessionSummary:
    return ChatSessionSummary(
        chat_id=chat.id,
        title=chat.title,
        status=chat.status,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


def _message_view(message: Any) -> ChatMessageView:
    return ChatMessageView(
        message_id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        sequence_no=message.sequence_no,
        metadata=dict(message.metadata_json or {}),
        created_at=message.created_at,
    )
