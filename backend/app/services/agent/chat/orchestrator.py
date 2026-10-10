from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.agent_llm_config import AgentLLMConfig
from app.domain.agent.chat import ChatToolCallSummary, ChatUsage
from app.domain.agent.chat_errors import (
    budget_exceeded,
    invalid_llm_tool_call,
    total_deadline_exceeded,
)
from app.domain.agent.errors import AgentError
from app.services.agent.llm.contracts import (
    ChatMessage,
    LLMProvider,
    LLMTool,
    ToolCall,
)
from app.services.agent.registry import AgentToolRegistry


@dataclass(frozen=True)
class ToolCallAudit:
    tool_call_id: str
    tool_name: str
    args_hash: str
    status: str
    evidence_ids: list[str]
    duration_ms: int
    error_code: str | None = None
    cache_reused: bool = False


@dataclass(frozen=True)
class ToolResultContext:
    tool_call_id: str
    tool_name: str
    payload: dict[str, Any]


@dataclass
class OrchestrationResult:
    final_text: str
    tool_results: list[ToolResultContext] = field(default_factory=list)
    tool_calls: list[ChatToolCallSummary] = field(default_factory=list)
    usage: ChatUsage = field(default_factory=ChatUsage)
    warnings: list[str] = field(default_factory=list)


class ToolOrchestrator:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        registry: AgentToolRegistry,
        config: AgentLLMConfig,
        execute_tool: Callable[[str, dict[str, Any], str], dict[str, Any]],
        audit_tool_call: Callable[[ToolCallAudit], None] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.config = config
        self.execute_tool = execute_tool
        self.audit_tool_call = audit_tool_call or (lambda audit: None)
        self.monotonic = monotonic or time.monotonic
        self.last_usage = ChatUsage()

    def run(self, *, messages: list[ChatMessage], request_id: str) -> OrchestrationResult:
        started = self.monotonic()
        deadline = started + self.config.max_total_deadline_seconds
        provider_messages = list(messages)
        tools = [
            LLMTool(
                name=spec.name,
                description=spec.description,
                parameters=spec.input_model.model_json_schema(),
            )
            for spec in self.registry.enabled_specs()
            if spec.read_only
        ]
        usage = ChatUsage()
        self.last_usage = usage
        results: list[ToolResultContext] = []
        summaries: list[ChatToolCallSummary] = []
        warnings: list[str] = []
        seen_call_ids: set[str] = set()
        tool_rounds = 0

        while True:
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise total_deadline_exceeded()
            response = self.provider.complete(
                provider_messages,
                tools,
                timeout=min(float(self.config.request_timeout_seconds), remaining),
                request_id=request_id,
            )
            usage.add_provider_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
            if self.monotonic() > deadline:
                raise total_deadline_exceeded()
            if response.final_text is not None:
                return OrchestrationResult(
                    final_text=response.final_text,
                    tool_results=results,
                    tool_calls=summaries,
                    usage=usage,
                    warnings=_unique(warnings),
                )

            calls = response.tool_calls
            tool_rounds += 1
            if tool_rounds > self.config.max_tool_rounds:
                raise budget_exceeded("maximum tool rounds exceeded")
            if len(calls) > self.config.max_tool_calls_per_round:
                raise budget_exceeded("maximum tool calls per round exceeded")
            if usage.tool_calls + len(calls) > self.config.max_tool_calls_total:
                raise budget_exceeded("maximum total tool calls exceeded")
            duplicate_ids = seen_call_ids.intersection(call.id for call in calls)
            if duplicate_ids or len({call.id for call in calls}) != len(calls):
                raise invalid_llm_tool_call("duplicate tool_call_id")
            seen_call_ids.update(call.id for call in calls)
            usage.tool_calls += len(calls)

            provider_messages.append(ChatMessage(role="assistant", tool_calls=calls))
            round_cache: dict[str, ToolResultContext] = {}
            for call in calls:
                if self.monotonic() >= deadline:
                    raise total_deadline_exceeded()
                context, summary = self._execute_call(call, round_cache=round_cache)
                results.append(context)
                summaries.append(summary)
                provider_messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps(
                            context.payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )
                )
                warnings.extend(_tool_warnings(context))

    def _execute_call(
        self,
        call: ToolCall,
        *,
        round_cache: dict[str, ToolResultContext],
    ) -> tuple[ToolResultContext, ChatToolCallSummary]:
        try:
            spec = self.registry.get(call.name)
        except AgentError as exc:
            raise invalid_llm_tool_call("model requested an unknown tool") from exc
        if not spec.enabled or not spec.read_only:
            raise invalid_llm_tool_call("model requested a disabled tool")

        args_hash = _args_hash(call.name, call.arguments)
        cached = round_cache.get(args_hash)
        if cached is not None:
            context = ToolResultContext(call.id, call.name, cached.payload)
            cached_error = cached.payload.get("error")
            error_code = (
                str(cached_error["code"])
                if isinstance(cached_error, dict) and cached_error.get("code")
                else None
            )
            audit = ToolCallAudit(
                tool_call_id=call.id,
                tool_name=call.name,
                args_hash=args_hash,
                status="ERROR" if error_code else "READY",
                evidence_ids=_evidence_ids(cached.payload),
                duration_ms=0,
                error_code=error_code,
                cache_reused=True,
            )
            self.audit_tool_call(audit)
            return context, _summary(audit)

        started = self.monotonic()
        try:
            payload = self.execute_tool(call.name, call.arguments, call.id)
            status = "READY"
            error_code = None
        except AgentError as exc:
            payload = {"error": {"code": exc.code, "message": str(exc)}}
            status = "ERROR"
            error_code = exc.code
        duration_ms = max(0, round((self.monotonic() - started) * 1000))
        context = ToolResultContext(call.id, call.name, payload)
        audit = ToolCallAudit(
            tool_call_id=call.id,
            tool_name=call.name,
            args_hash=args_hash,
            status=status,
            evidence_ids=_evidence_ids(payload),
            duration_ms=duration_ms,
            error_code=error_code,
        )
        self.audit_tool_call(audit)
        round_cache[args_hash] = context
        return context, _summary(audit)


def _args_hash(tool_name: str, arguments: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"tool_name": tool_name, "arguments": arguments},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evidence_ids(payload: dict[str, Any]) -> list[str]:
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        return []
    return [
        item["evidence_id"]
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    ]


def _summary(audit: ToolCallAudit) -> ChatToolCallSummary:
    return ChatToolCallSummary(
        tool_call_id=audit.tool_call_id,
        tool_name=audit.tool_name,
        status=audit.status,
        duration_ms=audit.duration_ms,
        error_code=audit.error_code,
        cache_reused=audit.cache_reused,
    )


def _tool_warnings(context: ToolResultContext) -> list[str]:
    payload = context.payload
    warnings = [
        str(item)
        for item in payload.get("warnings", [])
        if isinstance(item, str) and item
    ]
    error = payload.get("error")
    if isinstance(error, dict) and error.get("code"):
        warnings.append(f"TOOL_ERROR:{context.tool_name}:{error['code']}")
    readiness = payload.get("readiness")
    if isinstance(readiness, dict) and readiness.get("ready") is False:
        warnings.append(
            f"TOOL_NOT_READY:{context.tool_name}:{readiness.get('code', 'UNKNOWN')}"
        )
    if payload.get("status") not in {None, "READY"}:
        warnings.append(f"TOOL_STATUS:{context.tool_name}:{payload['status']}")
    return warnings


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
