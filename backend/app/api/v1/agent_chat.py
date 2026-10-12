import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.v1.agent import require_agent_user
from app.api.v1.common import envelope
from app.core.config import get_settings
from app.core.db import get_db
from app.domain.agent.chat_errors import AgentChatError
from app.services.agent.chat.application import AgentChatApplication

router = APIRouter()


class CreateChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


def get_chat_application(db: Session = Depends(get_db)) -> AgentChatApplication:
    return AgentChatApplication(db, get_settings())


@router.post("/chats", status_code=status.HTTP_201_CREATED)
def create_chat(
    body: CreateChatRequest,
    user: Any = Depends(require_agent_user),
    service: AgentChatApplication = Depends(get_chat_application),
) -> dict[str, Any]:
    try:
        chat = service.create_chat(user=user, title=body.title)
    except AgentChatError as exc:
        raise _http_error(exc) from exc
    return envelope(chat.model_dump(mode="json"))


@router.get("/chats")
def list_chats(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: Any = Depends(require_agent_user),
    service: AgentChatApplication = Depends(get_chat_application),
) -> dict[str, Any]:
    chats, total = service.list_chats(
        user=user,
        limit=limit,
        offset=offset,
    )
    return envelope(
        [chat.model_dump(mode="json") for chat in chats],
        {"limit": limit, "offset": offset, "total": total},
    )


@router.get("/chats/{chat_id}")
def get_chat(
    chat_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    before_sequence: int | None = Query(default=None, ge=1),
    latest: bool = Query(default=False),
    user: Any = Depends(require_agent_user),
    service: AgentChatApplication = Depends(get_chat_application),
) -> dict[str, Any]:
    try:
        chat, messages, total, has_more, next_cursor = service.get_chat(
            user=user,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            before_sequence=before_sequence,
            latest=latest,
        )
        active_turn = service.get_running_turn_status(user=user, chat_id=chat_id)
    except AgentChatError as exc:
        raise _http_error(exc) from exc
    return envelope(
        {
            **chat.model_dump(mode="json"),
            "messages": [message.model_dump(mode="json") for message in messages],
            "active_turn": active_turn.model_dump(mode="json") if active_turn else None,
        },
        {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": has_more,
            "next_cursor": next_cursor,
        },
    )


@router.get("/chats/{chat_id}/turns/{request_id:path}")
def get_turn_status(
    chat_id: uuid.UUID,
    request_id: str,
    user: Any = Depends(require_agent_user),
    service: AgentChatApplication = Depends(get_chat_application),
) -> dict[str, Any]:
    if not request_id or len(request_id) > 128:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_ARGUMENT", "message": "invalid request_id"},
        )
    try:
        result = service.get_turn_status(
            user=user,
            chat_id=chat_id,
            request_id=request_id,
        )
    except AgentChatError as exc:
        raise _http_error(exc) from exc
    return envelope(result.model_dump(mode="json"))


@router.post("/chats/{chat_id}/messages")
def send_message(
    chat_id: uuid.UUID,
    body: SendMessageRequest,
    user: Any = Depends(require_agent_user),
    service: AgentChatApplication = Depends(get_chat_application),
) -> dict[str, Any]:
    request_id = body.request_id or str(uuid.uuid4())
    try:
        answer = service.send_message(
            user=user,
            chat_id=chat_id,
            content=body.content,
            request_id=request_id,
        )
    except AgentChatError as exc:
        raise _http_error(exc) from exc
    return envelope(answer.model_dump(mode="json"), {"request_id": request_id})


@router.delete("/chats/{chat_id}")
def archive_chat(
    chat_id: uuid.UUID,
    user: Any = Depends(require_agent_user),
    service: AgentChatApplication = Depends(get_chat_application),
) -> dict[str, Any]:
    try:
        chat = service.archive_chat(user=user, chat_id=chat_id)
    except AgentChatError as exc:
        raise _http_error(exc) from exc
    return envelope(chat.model_dump(mode="json"))


def _http_error(exc: AgentChatError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )
