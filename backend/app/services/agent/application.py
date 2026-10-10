import time
from collections.abc import Callable
from typing import Any

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.agent.contracts import AgentToolResult
from app.domain.agent.errors import (
    AgentError,
    invalid_argument,
    resource_limit_exceeded,
    statement_timeout,
    tool_timeout,
)
from app.domain.agent.policy import serialized_result, user_audit_hash
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.adapters.opportunities import OpportunityAgentAdapter
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.agent.registry import AgentToolRegistry, ToolSpec, build_registry


class AgentApplicationService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        registry: AgentToolRegistry | None = None,
        monotonic: Callable[[], float] | None = None,
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
            config=self.config,
        )
        self._monotonic = monotonic or time.monotonic

    def execute(
        self,
        *,
        tool_name: str,
        raw_input: dict[str, Any],
        request_id: str,
        user: Any,
    ) -> dict[str, Any]:
        started = self._monotonic()
        spec: ToolSpec | None = None
        result: AgentToolResult | None = None
        try:
            spec = self.registry.get(tool_name)
            if not spec.enabled:
                raise AgentError("TOOL_DISABLED", "agent tool is disabled", status_code=503)
            try:
                request = spec.input_model.model_validate(raw_input)
            except ValidationError as exc:
                raise invalid_argument(_validation_message(exc)) from exc

            result = spec.handler(request)
            self._check_soft_timeout(spec, started)
            self._validate_result_contract(spec, result)
            self._validate_resource_limits(spec, result)
            payload = serialized_result(
                result,
                max_output_bytes=self.config.max_output_bytes,
            )
            self._check_soft_timeout(spec, started)
        except DBAPIError as exc:
            error = statement_timeout() if _is_statement_timeout(exc) else AgentError(
                "INTERNAL_ERROR", "agent tool execution failed", status_code=500
            )
            self._audit_failure(tool_name, request_id, user, started, spec, result, error)
            raise error from exc
        except AgentError as exc:
            self._audit_failure(tool_name, request_id, user, started, spec, result, exc)
            raise
        except Exception as exc:
            error = AgentError(
                "INTERNAL_ERROR", "agent tool execution failed", status_code=500
            )
            self._audit_failure(tool_name, request_id, user, started, spec, result, error)
            raise error from exc

        self._audit(
            tool_name=tool_name,
            tool_version=spec.version,
            request_id=request_id,
            user=user,
            duration_ms=self._duration_ms(started),
            status=result.status,
            error_code=None,
            record_count=len(result.records),
            evidence_count=len(result.evidence),
        )
        return payload

    def _check_soft_timeout(self, spec: ToolSpec, started: float) -> None:
        if self._duration_ms(started) > spec.timeout_seconds * 1000:
            raise tool_timeout()

    @staticmethod
    def _validate_result_contract(spec: ToolSpec, result: AgentToolResult) -> None:
        if result.tool_name != spec.name or result.tool_version != spec.version:
            raise AgentError(
                "INTERNAL_ERROR",
                "tool returned an incompatible result contract",
                status_code=500,
            )

    @staticmethod
    def _validate_resource_limits(spec: ToolSpec, result: AgentToolResult) -> None:
        if len(result.records) > spec.max_records:
            raise resource_limit_exceeded(
                f"tool returned more than {spec.max_records} top-level records"
            )
        if len(result.evidence) > spec.max_evidence:
            raise resource_limit_exceeded(
                f"tool returned more than {spec.max_evidence} evidence references"
            )
        if len(result.warnings) > spec.max_warnings:
            raise resource_limit_exceeded(
                f"tool returned more than {spec.max_warnings} warnings"
            )
        for field_name, limit in spec.nested_limits.items():
            count = sum(
                len(value)
                for record in result.records
                if isinstance(record, dict)
                and isinstance((value := record.get(field_name)), list)
            )
            if count > limit:
                raise resource_limit_exceeded(
                    f"tool nested field {field_name} exceeds its limit of {limit}"
                )

    def _audit_failure(
        self,
        tool_name: str,
        request_id: str,
        user: Any,
        started: float,
        spec: ToolSpec | None,
        result: AgentToolResult | None,
        error: AgentError,
    ) -> None:
        self._audit(
            tool_name=tool_name,
            tool_version=spec.version if spec else None,
            request_id=request_id,
            user=user,
            duration_ms=self._duration_ms(started),
            status="ERROR",
            error_code=error.code,
            record_count=len(result.records) if result else 0,
            evidence_count=len(result.evidence) if result else 0,
        )

    def _duration_ms(self, started: float) -> int:
        return max(0, round((self._monotonic() - started) * 1000))

    @staticmethod
    def _audit(
        *,
        tool_name: str,
        tool_version: str | None,
        request_id: str,
        user: Any,
        duration_ms: int,
        status: str,
        error_code: str | None,
        record_count: int,
        evidence_count: int,
    ) -> None:
        logger.bind(
            request_id=request_id,
            user_hash=user_audit_hash(user),
            tool=tool_name,
            version=tool_version,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            record_count=record_count,
            evidence_count=evidence_count,
        ).info("agent_tool")


def _is_statement_timeout(exc: DBAPIError) -> bool:
    current: BaseException | None = exc
    while current is not None:
        code = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if code == "57014":
            return True
        current = getattr(current, "orig", None) or current.__cause__
        if current is exc:
            break
    original_message = str(getattr(exc, "orig", "")).lower()
    return "statement timeout" in original_message or (
        "canceling statement" in original_message and "timeout" in original_message
    )


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors(include_url=False, include_input=False)
    return "; ".join(
        f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}" for error in errors
    )
