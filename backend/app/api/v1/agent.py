import json
import uuid
from typing import Any

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.api.v1.common import envelope
from app.core.agent_db import get_agent_db
from app.core.config import get_settings
from app.core.db import get_db
from app.domain.agent.errors import AgentError
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.adapters.opportunities import OpportunityAgentAdapter
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.application import AgentApplicationService
from app.services.agent.registry import build_registry
from app.services.auth.dependencies import (
    SESSION_COOKIE,
    require_auth_session,
    require_authenticated_user,
)

router = APIRouter()
_MAX_REQUEST_BYTES = 16_384


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=64)
    input: dict[str, Any]
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


def require_agent_user(
    token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    auth_db: Session = Depends(get_db),
) -> Any:
    try:
        auth = require_auth_session(token=token, db=auth_db)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail={"code": "UNAUTHORIZED", "message": "authentication required"},
            ) from exc
        raise
    return require_authenticated_user(auth)


@router.get("/tools")
def tools(
    user: Any = Depends(require_agent_user),
    db: Session = Depends(get_agent_db),
) -> dict[str, Any]:
    settings = get_settings()
    registry = build_registry(
        MarketDataAgentAdapter(db, settings),
        OpportunityAgentAdapter(db, settings),
        ResearchAgentAdapter(db),
        timeout_seconds=settings.agent_config.default_timeout_seconds,
    )
    return envelope(
        registry.catalog(),
        {"registry_version": settings.agent_config.registry_version, "tool_count": 8},
    )


@router.get("/status")
def status(user: Any = Depends(require_agent_user)) -> dict[str, Any]:
    config = get_settings().agent_config
    return envelope(
        {
            "agent_mode": config.mode,
            "registry_version": config.registry_version,
            "tool_count": 8,
            "llm_enabled": config.llm_enabled,
            "read_only": True,
        }
    )


@router.post("/tools/execute")
def execute(
    body: dict[str, Any] = Body(...),
    user: Any = Depends(require_agent_user),
    db: Session = Depends(get_agent_db),
) -> dict[str, Any]:
    if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > _MAX_REQUEST_BYTES:
        raise _http_error(
            AgentError("INVALID_ARGUMENT", "request body is too large", status_code=422)
        )
    try:
        request = ExecuteRequest.model_validate(body)
    except ValidationError as exc:
        raise _http_error(
            AgentError("INVALID_ARGUMENT", "invalid execute request", status_code=422)
        ) from exc
    request_id = request.request_id or str(uuid.uuid4())
    try:
        data = AgentApplicationService(db, get_settings()).execute(
            tool_name=request.tool_name,
            raw_input=request.input,
            request_id=request_id,
            user=user,
        )
    except AgentError as exc:
        raise _http_error(exc) from exc
    return envelope(data, {"request_id": request_id})


def _http_error(exc: AgentError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )
