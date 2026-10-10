from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent_chat import (
    AgentChatMessage,
    AgentChatSession,
    AgentChatToolCall,
    AgentChatTurn,
)


class AgentChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_session(self, *, owner_user_id: uuid.UUID, title: str) -> AgentChatSession:
        chat = AgentChatSession(owner_user_id=owner_user_id, title=title)
        self.db.add(chat)
        self.db.flush()
        return chat

    def get_owned_session(
        self,
        *,
        chat_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        for_update: bool = False,
    ) -> AgentChatSession | None:
        statement = select(AgentChatSession).where(
            AgentChatSession.id == chat_id,
            AgentChatSession.owner_user_id == owner_user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.execute(
            statement.execution_options(populate_existing=True)
        ).scalar_one_or_none()

    def session_page(
        self, *, owner_user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[AgentChatSession], int]:
        where = [AgentChatSession.owner_user_id == owner_user_id]
        total = int(
            self.db.scalar(
                select(func.count()).select_from(AgentChatSession).where(*where)
            )
            or 0
        )
        rows = list(
            self.db.execute(
                select(AgentChatSession)
                .where(*where)
                .order_by(AgentChatSession.updated_at.desc(), AgentChatSession.id.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return rows, total

    def archive(self, chat: AgentChatSession) -> AgentChatSession:
        chat.status = "ARCHIVED"
        chat.updated_at = datetime.now(UTC)
        self.db.add(chat)
        self.db.flush()
        return chat

    def message_page(
        self,
        *,
        chat_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[AgentChatMessage], int]:
        where = [AgentChatMessage.session_id == chat_id]
        total = int(
            self.db.scalar(
                select(func.count()).select_from(AgentChatMessage).where(*where)
            )
            or 0
        )
        rows = list(
            self.db.execute(
                select(AgentChatMessage)
                .where(*where)
                .order_by(AgentChatMessage.sequence_no)
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return rows, total

    def recent_messages(
        self, *, chat_id: uuid.UUID, limit: int
    ) -> tuple[list[AgentChatMessage], bool]:
        total = int(
            self.db.scalar(
                select(func.count())
                .select_from(AgentChatMessage)
                .where(AgentChatMessage.session_id == chat_id)
            )
            or 0
        )
        rows = list(
            self.db.execute(
                select(AgentChatMessage)
                .where(AgentChatMessage.session_id == chat_id)
                .order_by(AgentChatMessage.sequence_no.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        rows.reverse()
        return rows, total > len(rows)

    def next_sequence(self, *, chat_id: uuid.UUID) -> int:
        current = self.db.scalar(
            select(func.max(AgentChatMessage.sequence_no)).where(
                AgentChatMessage.session_id == chat_id
            )
        )
        return int(current or 0) + 1

    def add_message(
        self,
        *,
        chat_id: uuid.UUID,
        role: str,
        content: str,
        sequence_no: int,
        metadata: dict[str, object] | None = None,
    ) -> AgentChatMessage:
        message = AgentChatMessage(
            session_id=chat_id,
            role=role,
            content=content,
            status="COMPLETED",
            sequence_no=sequence_no,
            metadata_json=metadata or {},
        )
        self.db.add(message)
        self.db.flush()
        return message

    def get_turn_by_request(
        self, *, chat_id: uuid.UUID, request_id: str
    ) -> AgentChatTurn | None:
        return self.db.execute(
            select(AgentChatTurn).where(
                AgentChatTurn.session_id == chat_id,
                AgentChatTurn.request_id == request_id,
            )
        ).scalar_one_or_none()

    def running_turn(self, *, chat_id: uuid.UUID) -> AgentChatTurn | None:
        return self.db.execute(
            select(AgentChatTurn).where(
                AgentChatTurn.session_id == chat_id,
                AgentChatTurn.status == "RUNNING",
            )
        ).scalar_one_or_none()

    def add_turn(
        self,
        *,
        chat_id: uuid.UUID,
        user_message_id: uuid.UUID,
        request_id: str,
        model: str,
        trace_id: uuid.UUID,
    ) -> AgentChatTurn:
        turn = AgentChatTurn(
            session_id=chat_id,
            user_message_id=user_message_id,
            request_id=request_id,
            status="RUNNING",
            model=model,
            trace_id=trace_id,
            usage_json={},
        )
        self.db.add(turn)
        self.db.flush()
        return turn

    def add_tool_call(
        self,
        *,
        turn_id: uuid.UUID,
        tool_call_id: str,
        tool_name: str,
        args_hash: str,
        status: str,
        evidence_ids: list[str],
        duration_ms: int,
        error_code: str | None,
        cache_reused: bool,
    ) -> AgentChatToolCall:
        row = AgentChatToolCall(
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            args_hash=args_hash,
            status=status,
            evidence_ids_json=evidence_ids,
            duration_ms=duration_ms,
            error_code=error_code,
            cache_reused=cache_reused,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def tool_calls(self, *, turn_id: uuid.UUID) -> list[AgentChatToolCall]:
        return list(
            self.db.execute(
                select(AgentChatToolCall)
                .where(AgentChatToolCall.turn_id == turn_id)
                .order_by(AgentChatToolCall.id)
            )
            .scalars()
            .all()
        )

    def get_message(self, message_id: uuid.UUID) -> AgentChatMessage | None:
        return self.db.get(AgentChatMessage, message_id)

    def complete_turn(
        self,
        *,
        turn: AgentChatTurn,
        assistant_message_id: uuid.UUID,
        usage: dict[str, object],
    ) -> None:
        turn.assistant_message_id = assistant_message_id
        turn.status = "COMPLETED"
        turn.error_code = None
        turn.usage_json = usage
        turn.finished_at = datetime.now(UTC)
        self.db.add(turn)
        self.db.flush()

    def fail_turn(
        self,
        *,
        turn_id: uuid.UUID,
        error_code: str,
        usage: dict[str, object],
    ) -> None:
        turn = self.db.execute(
            select(AgentChatTurn).where(AgentChatTurn.id == turn_id).with_for_update()
        ).scalar_one()
        turn.status = "FAILED"
        turn.error_code = error_code
        turn.usage_json = usage
        turn.finished_at = datetime.now(UTC)
        self.db.add(turn)
        self.db.flush()
