from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.agent_db import agent_db_session
from app.core.config import Settings
from app.domain.agent.chat import (
    AnswerStatus,
    ChatAnswer,
    ChatMessageView,
    ChatSessionSummary,
    ChatTurnStatus,
    RejectedClaim,
    StructuredClaim,
)
from app.domain.agent.chat_errors import (
    AgentChatError,
    chat_conflict,
    chat_not_found,
    idempotency_conflict,
    llm_disabled,
    total_deadline_exceeded,
    turn_not_found,
)
from app.domain.agent.policy import user_audit_hash
from app.models.agent_chat import AgentChatSession, AgentChatTurn
from app.repositories.agent_chat import AgentChatRepository
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.adapters.opportunities import OpportunityAgentAdapter
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.application import AgentApplicationService
from app.services.agent.chat.comparison_contract import (
    BacktestComparisonContractResolver,
)
from app.services.agent.chat.comparison_policy import EvidenceComparisonPolicy
from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from app.services.agent.chat.lineage import ExperimentLineageResolver
from app.services.agent.chat.orchestrator import ToolCallAudit, ToolOrchestrator
from app.services.agent.chat.prompt import SYSTEM_PROMPT
from app.services.agent.chat.request_identity import request_content_hash
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
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        if settings.agent_config is None:
            raise RuntimeError("agent config is not loaded")
        self.db = db
        self.settings = settings
        self.config = settings.agent_config
        self.repo = AgentChatRepository(db)
        self._provider = provider
        self._monotonic = monotonic or time.monotonic

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
        before_sequence: int | None = None,
        latest: bool = False,
    ) -> tuple[
        ChatSessionSummary,
        list[ChatMessageView],
        int,
        bool,
        int | None,
    ]:
        chat = self.repo.get_owned_session(
            chat_id=chat_id, owner_user_id=_user_id(user)
        )
        if chat is None:
            raise chat_not_found()
        if latest or before_sequence is not None:
            messages, total, has_more, next_cursor = self.repo.message_cursor_page(
                chat_id=chat_id,
                limit=limit,
                before_sequence=before_sequence,
            )
        else:
            messages, total = self.repo.message_page(
                chat_id=chat_id, limit=limit, offset=offset
            )
            has_more = offset + len(messages) < total
            next_cursor = None
        return (
            _session_summary(chat),
            [_message_view(row) for row in messages],
            total,
            has_more,
            next_cursor,
        )

    def get_turn_status(
        self,
        *,
        user: Any,
        chat_id: uuid.UUID,
        request_id: str,
    ) -> ChatTurnStatus:
        chat = self.repo.get_owned_session(
            chat_id=chat_id,
            owner_user_id=_user_id(user),
        )
        if chat is None:
            raise chat_not_found()
        turn = self.repo.get_turn_by_request(
            chat_id=chat_id,
            request_id=request_id,
        )
        if turn is None:
            raise turn_not_found()
        user_message = self.repo.get_message(turn.user_message_id)
        if user_message is None:
            raise chat_conflict("turn user message is unavailable")
        answer = self._answer_from_turn(turn) if turn.status == "COMPLETED" else None
        return ChatTurnStatus(
            chat_id=chat_id,
            request_id=turn.request_id,
            status=turn.status,
            error_code=turn.error_code,
            content=user_message.content,
            user_message_id=turn.user_message_id,
            assistant_message_id=turn.assistant_message_id,
            started_at=turn.started_at,
            finished_at=turn.finished_at,
            answer=answer,
        )

    def get_running_turn_status(
        self, *, user: Any, chat_id: uuid.UUID
    ) -> ChatTurnStatus | None:
        chat = self.repo.get_owned_session(
            chat_id=chat_id, owner_user_id=_user_id(user)
        )
        if chat is None:
            raise chat_not_found()
        turn = self.repo.running_turn(chat_id=chat_id)
        if turn is None:
            return None
        return self.get_turn_status(
            user=user, chat_id=chat_id, request_id=turn.request_id
        )

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
        deadline = self._monotonic() + self.config.llm.max_total_deadline_seconds
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
            self._ensure_deadline(deadline)
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
            self._ensure_deadline(deadline)

            provider = self._provider or build_llm_provider(self.settings)
            registry = self._schema_registry()
            orchestrator = ToolOrchestrator(
                provider=provider,
                registry=registry,
                config=self.config.llm,
                execute_tool=lambda name, args, call_id, remaining: self._execute_tool(
                    user=user,
                    request_id=request_id,
                    tool_call_id=call_id,
                    tool_name=name,
                    arguments=args,
                    remaining_seconds=remaining,
                ),
                audit_tool_call=lambda audit: self._persist_tool_call(turn.id, audit),
                monotonic=self._monotonic,
            )
            orchestration = orchestrator.run(
                messages=provider_messages,
                request_id=request_id,
                deadline=deadline,
            )
            self._ensure_deadline(deadline)
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise total_deadline_exceeded()
            with agent_db_session(
                self.settings,
                remaining_seconds=remaining,
            ) as evidence_db:
                compiled = EvidenceCompiler(
                    max_answer_chars=self.config.llm.max_answer_chars,
                    max_claims=self.config.llm.max_claims,
                    max_evidence_ids_per_claim=(
                        self.config.llm.max_evidence_ids_per_claim
                    ),
                    max_structured_facts_per_claim=(
                        self.config.llm.max_structured_facts_per_claim
                    ),
                    comparison_policy=EvidenceComparisonPolicy(
                        lineage_resolver=ExperimentLineageResolver(evidence_db),
                        contract_resolver=BacktestComparisonContractResolver(evidence_db),
                    ),
                ).compile(
                    final_text=orchestration.final_text,
                    tool_results=orchestration.tool_results,
                    inherited_warnings=context_warning + orchestration.warnings,
                )
            self._ensure_deadline(deadline)
            answer = self._complete_turn(
                chat_id=chat_id,
                turn_id=turn.id,
                trace_id=turn.trace_id,
                answer=compiled.answer,
                answer_status=compiled.answer_status,
                claims=[item.model_dump(mode="json") for item in compiled.claims],
                rejected_claims=[
                    item.model_dump(mode="json") for item in compiled.rejected_claims
                ],
                needs_clarification=compiled.needs_clarification,
                citations=[item.model_dump(mode="json") for item in compiled.citations],
                warnings=compiled.warnings,
                tool_calls=[
                    item.model_dump(mode="json") for item in orchestration.tool_calls
                ],
                usage=orchestration.usage.model_dump(mode="json"),
            )
            self._ensure_deadline(deadline)
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
        content_hash = request_content_hash(
            content=content,
            chat_id=chat_id,
            owner_id=owner_id,
        )
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
                if existing.request_content_hash != content_hash:
                    self.db.rollback()
                    raise idempotency_conflict()
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
                request_content_hash=content_hash,
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
        remaining_seconds: float,
    ) -> dict[str, Any]:
        if remaining_seconds < 0.001:
            raise total_deadline_exceeded()
        with agent_db_session(
            self.settings,
            remaining_seconds=remaining_seconds,
        ) as db:
            return AgentApplicationService(db, self.settings).execute(
                tool_name=tool_name,
                raw_input=arguments,
                request_id=f"{request_id}:{tool_call_id}",
                user=user,
                remaining_seconds=remaining_seconds,
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
        answer_status: AnswerStatus,
        claims: list[dict[str, Any]],
        rejected_claims: list[dict[str, Any]],
        needs_clarification: bool,
        citations: list[dict[str, Any]],
        warnings: list[str],
        tool_calls: list[dict[str, Any]],
        usage: dict[str, Any],
    ) -> ChatAnswer:
        metadata = {
            "status": answer_status,
            "answer_status": answer_status,
            "claims": claims,
            "verified_claims": claims,
            "rejected_claims": rejected_claims,
            "needs_clarification": needs_clarification,
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
            status=answer_status,
            answer_status=answer_status,
            answer=answer,
            claims=claims,
            verified_claims=claims,
            rejected_claims=rejected_claims,
            needs_clarification=needs_clarification,
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
        normalized = _normalized_answer_metadata(metadata)
        return ChatAnswer(
            chat_id=turn.session_id,
            message_id=message.id,
            status=normalized["answer_status"],
            answer_status=normalized["answer_status"],
            answer=message.content,
            claims=normalized["verified_claims"],
            verified_claims=normalized["verified_claims"],
            rejected_claims=normalized["rejected_claims"],
            needs_clarification=normalized["needs_clarification"],
            citations=normalized["citations"],
            warnings=normalized["warnings"],
            tool_calls=normalized["tool_calls"],
            usage=normalized["usage"],
            trace_id=normalized.get("trace_id") or str(turn.trace_id),
        )

    def _ensure_deadline(self, deadline: float) -> None:
        if self._monotonic() >= deadline:
            raise total_deadline_exceeded()

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
    metadata = dict(message.metadata_json or {})
    if message.role == "ASSISTANT":
        metadata = _normalized_answer_metadata(metadata)
    return ChatMessageView(
        message_id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        sequence_no=message.sequence_no,
        metadata=metadata,
        created_at=message.created_at,
    )


def _normalized_answer_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    raw_claims = metadata.get("verified_claims", metadata.get("claims", []))
    verified: list[dict[str, Any]] = []
    rejected: dict[str, dict[str, Any]] = {}
    if isinstance(raw_claims, list):
        for raw in raw_claims:
            if not isinstance(raw, dict):
                continue
            if raw.get("comparison_state") == "INCOMPATIBLE":
                safe = _safe_rejected_claim(raw, ["COMPARISON_INCOMPATIBLE"])
                if safe is not None:
                    rejected[safe["claim_id"]] = safe
                continue
            try:
                verified.append(StructuredClaim.model_validate(raw).model_dump(mode="json"))
            except ValueError:
                continue

    raw_rejected = metadata.get("rejected_claims", [])
    if isinstance(raw_rejected, list):
        for raw in raw_rejected:
            if not isinstance(raw, dict):
                continue
            safe = _safe_rejected_claim(raw, [])
            if safe is not None:
                rejected[safe["claim_id"]] = safe

    warnings = [
        str(item)
        for item in metadata.get("warnings", [])
        if isinstance(item, str)
    ]
    for warning in warnings:
        parts = warning.split(":", 2)
        if len(parts) == 3 and parts[0] == "CLAIM_REJECTED":
            claim_id, reason = parts[1], parts[2]
            existing = rejected.get(claim_id)
            if existing is None:
                safe = _safe_rejected_claim(
                    {"claim_id": claim_id, "claim_type": "FACT"},
                    [reason],
                )
                if safe is not None:
                    rejected[claim_id] = safe
            elif reason not in existing["reason_codes"]:
                existing["reason_codes"].append(reason)

    stored_status = metadata.get("answer_status", metadata.get("status"))
    if verified and rejected:
        answer_status: AnswerStatus = "PARTIAL_VERIFIED"
    elif verified:
        answer_status = "COMPLETED"
    elif stored_status == "PARTIAL_VERIFIED":
        answer_status = "INSUFFICIENT_EVIDENCE"
    elif stored_status in {"COMPLETED", "INSUFFICIENT_EVIDENCE"}:
        answer_status = stored_status
    else:
        answer_status = "INSUFFICIENT_EVIDENCE"
    return {
        "status": answer_status,
        "answer_status": answer_status,
        "claims": verified,
        "verified_claims": verified,
        "rejected_claims": list(rejected.values()),
        "needs_clarification": bool(metadata.get("needs_clarification", False)),
        "citations": metadata.get("citations", []),
        "warnings": warnings,
        "tool_calls": metadata.get("tool_calls", []),
        "usage": metadata.get("usage", {}),
        "trace_id": metadata.get("trace_id"),
    }


def _safe_rejected_claim(
    raw: dict[str, Any],
    fallback_reasons: list[str],
) -> dict[str, Any] | None:
    reasons = [
        str(item)
        for item in raw.get("reason_codes", [])
        if isinstance(item, str) and item
    ]
    reasons = list(dict.fromkeys([*fallback_reasons, *reasons]))
    if not reasons:
        reasons = ["CLAIM_REJECTED"]
    try:
        return RejectedClaim(
            claim_id=raw.get("claim_id"),
            claim_type=raw.get("claim_type", "FACT"),
            reason_codes=reasons,
            comparison_state=raw.get("comparison_state"),
            policy_version=raw.get("policy_version"),
        ).model_dump(mode="json")
    except ValueError:
        return None
