import time
from typing import Any

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.agent.errors import AgentError, invalid_argument
from app.domain.agent.policy import serialized_result, user_audit_hash
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.adapters.opportunities import OpportunityAgentAdapter
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.registry import AgentToolRegistry, build_registry


class AgentApplicationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        registry: AgentToolRegistry | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        if settings.agent_config is None:
            raise RuntimeError("agent config is not loaded")
        self.config = settings.agent_config
        self.registry = registry or build_registry(
            MarketDataAgentAdapter(db, settings),
            OpportunityAgentAdapter(db, settings),
            ResearchAgentAdapter(db),
            timeout_seconds=self.config.default_timeout_seconds,
        )

    def execute(
        self,
        *,
        tool_name: str,
        raw_input: dict[str, Any],
        request_id: str,
        user: Any,
    ) -> dict[str, Any]:
        spec = self.registry.get(tool_name)
        try:
            request = spec.input_model.model_validate(raw_input)
        except ValidationError as exc:
            raise invalid_argument(_validation_message(exc)) from exc
        started = time.monotonic()
        try:
            result = spec.handler(request)
            if len(result.records) > spec.max_records:
                raise AgentError(
                    "OUTPUT_LIMIT_EXCEEDED",
                    f"tool returned more than {spec.max_records} records",
                    status_code=422,
                )
            payload = serialized_result(
                result,
                max_output_bytes=self.config.max_output_bytes,
            )
        except AgentError:
            self._audit(tool_name, request_id, user, started, "ERROR", 0, 0)
            raise
        except Exception as exc:
            self._audit(tool_name, request_id, user, started, "ERROR", 0, 0)
            raise AgentError(
                "INTERNAL_ERROR", "agent tool execution failed", status_code=500
            ) from exc
        self._audit(
            tool_name,
            request_id,
            user,
            started,
            result.status,
            len(result.records),
            len(result.evidence),
        )
        return payload

    def _audit(
        self,
        tool_name: str,
        request_id: str,
        user: Any,
        started: float,
        status: str,
        record_count: int,
        evidence_count: int,
    ) -> None:
        logger.info(
            "agent_tool request_id={} user_hash={} tool={} version=1.0 "
            "duration_ms={} status={} record_count={} evidence_count={}",
            request_id,
            user_audit_hash(user),
            tool_name,
            round((time.monotonic() - started) * 1000),
            status,
            record_count,
            evidence_count,
        )


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors(include_url=False, include_input=False)
    return "; ".join(
        f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}" for error in errors
    )
