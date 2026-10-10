import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from app.core.agent_config import AgentConfig
from app.core.agent_llm_config import AgentLLMConfig
from app.domain.agent.chat_errors import AgentChatError
from app.domain.agent.errors import AgentError
from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from app.services.agent.chat.orchestrator import ToolOrchestrator, ToolResultContext
from app.services.agent.llm.contracts import (
    ChatMessage,
    LLMResponse,
    LLMUsage,
    ProviderError,
    ToolCall,
)
from app.services.agent.llm.fake import FakeLLMProvider
from app.services.agent.llm.openai_compatible import OpenAICompatibleProvider
from app.services.agent.registry import AgentToolRegistry, ToolSpec
from pydantic import BaseModel, ConfigDict


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = 1


def _registry() -> AgentToolRegistry:
    return AgentToolRegistry(
        [
            ToolSpec(
                name="test.read",
                version="1.0",
                description="Read deterministic test evidence.",
                input_model=StrictInput,
                handler=lambda request: None,
                layer="DATA",
                max_records=1,
                max_evidence=1,
                max_warnings=2,
                timeout_seconds=2,
            )
        ]
    )


def _payload() -> dict[str, Any]:
    return {
        "tool_name": "test.read",
        "tool_version": "1.0",
        "status": "READY",
        "as_of_date": "2026-10-10",
        "identity": {},
        "records": [{"value": 1}],
        "evidence": [
            {
                "evidence_id": "evidence-1",
                "evidence_version": "v2",
                "layer": "DATA",
                "source_type": "dataset",
                "entity_id": "fixture",
                "trade_date": "2026-10-10",
                "quality_status": "PASS",
                "limitations": [],
                "content_hash": "c" * 64,
            }
        ],
        "warnings": [],
        "readiness": {"ready": True, "code": "READY", "details": {}},
    }


def _final(*evidence_ids: str, clarification: bool = False) -> LLMResponse:
    return LLMResponse(
        final_text=json.dumps(
            {
                "answer": "这是经过工具验证的研究说明。",
                "evidence_ids": list(evidence_ids),
                "warnings": [],
                "needs_clarification": clarification,
            },
            ensure_ascii=False,
        ),
        usage=LLMUsage(prompt_tokens=5, completion_tokens=7),
    )


def _orchestrator(
    responses: list[LLMResponse | Exception],
    execute: Callable[[str, dict[str, Any], str], dict[str, Any]],
    *,
    config: AgentLLMConfig | None = None,
    audits: list[Any] | None = None,
) -> tuple[ToolOrchestrator, FakeLLMProvider]:
    provider = FakeLLMProvider(responses)
    orchestrator = ToolOrchestrator(
        provider=provider,
        registry=_registry(),
        config=config or AgentLLMConfig(),
        execute_tool=execute,
        audit_tool_call=(audits.append if audits is not None else None),
    )
    return orchestrator, provider


def test_llm_config_is_disabled_by_default_and_hard_bounded() -> None:
    assert AgentConfig().llm_enabled is False
    assert AgentConfig().mode == "tools_only"
    with pytest.raises(ValueError, match="agent mode"):
        AgentConfig(llm_enabled=True)
    with pytest.raises(ValueError, match="per-round"):
        AgentLLMConfig(max_tool_calls_total=2, max_tool_calls_per_round=3)
    with pytest.raises(ValueError, match="total deadline"):
        AgentLLMConfig(request_timeout_seconds=30, max_total_deadline_seconds=20)


def test_orchestrator_calls_only_registry_tool_and_compiles_real_evidence() -> None:
    responses = [
        LLMResponse(
            tool_calls=[ToolCall(id="call-1", name="test.read", arguments={"value": 2})],
            usage=LLMUsage(prompt_tokens=10, completion_tokens=2),
        ),
        _final("evidence-1"),
    ]
    executed: list[tuple[str, dict[str, Any], str]] = []
    audits: list[Any] = []
    orchestrator, provider = _orchestrator(
        responses,
        lambda name, args, call_id: executed.append((name, args, call_id)) or _payload(),
        audits=audits,
    )
    result = orchestrator.run(
        messages=[ChatMessage(role="system", content="rules")],
        request_id="request-1",
    )
    compiled = EvidenceCompiler(max_answer_chars=1000).compile(
        final_text=result.final_text,
        tool_results=result.tool_results,
        inherited_warnings=result.warnings,
    )

    assert executed == [("test.read", {"value": 2}, "call-1")]
    assert [tool.name for tool in provider.calls[0]["tools"]] == ["test.read"]
    assert provider.calls[1]["messages"][-1].role == "tool"
    assert compiled.citations[0].evidence_id == "evidence-1"
    assert compiled.citations[0].marker == "E1"
    assert "[E1]" in compiled.answer
    assert result.usage.model_dump() == {
        "prompt_tokens": 15,
        "completion_tokens": 9,
        "provider_calls": 2,
        "tool_calls": 1,
    }
    assert audits[0].status == "READY"


def test_same_round_duplicate_request_is_executed_once_but_audited_twice() -> None:
    responses = [
        LLMResponse(
            tool_calls=[
                ToolCall(id="call-a", name="test.read", arguments={"value": 1}),
                ToolCall(id="call-b", name="test.read", arguments={"value": 1}),
            ]
        ),
        _final("evidence-1"),
    ]
    executions = 0
    audits: list[Any] = []

    def execute(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
        nonlocal executions
        executions += 1
        return _payload()

    orchestrator, provider = _orchestrator(responses, execute, audits=audits)
    result = orchestrator.run(
        messages=[ChatMessage(role="system", content="rules")], request_id="request-2"
    )

    assert executions == 1
    assert len(result.tool_results) == 2
    assert len(provider.calls[1]["messages"]) == 4
    assert [audit.cache_reused for audit in audits] == [False, True]
    assert result.usage.tool_calls == 2


def test_same_round_duplicate_tool_error_remains_an_error_in_reused_audit() -> None:
    responses = [
        LLMResponse(
            tool_calls=[
                ToolCall(id="call-a", name="test.read", arguments={}),
                ToolCall(id="call-b", name="test.read", arguments={}),
            ]
        ),
        _final(),
    ]
    audits: list[Any] = []
    executions = 0

    def execute(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
        nonlocal executions
        executions += 1
        raise AgentError("DATA_UNAVAILABLE", "data unavailable", status_code=503)

    orchestrator, _ = _orchestrator(responses, execute, audits=audits)
    orchestrator.run(
        messages=[ChatMessage(role="system", content="rules")], request_id="error-dedup"
    )

    assert executions == 1
    assert [audit.status for audit in audits] == ["ERROR", "ERROR"]
    assert [audit.error_code for audit in audits] == [
        "DATA_UNAVAILABLE",
        "DATA_UNAVAILABLE",
    ]
    assert audits[1].cache_reused is True


@pytest.mark.parametrize(
    "calls,code",
    [
        ([ToolCall(id="bad", name="sql.execute", arguments={})], "LLM_INVALID_TOOL_CALL"),
        (
            [
                ToolCall(id="same", name="test.read", arguments={}),
                ToolCall(id="same", name="test.read", arguments={}),
            ],
            "LLM_INVALID_TOOL_CALL",
        ),
    ],
)
def test_unknown_and_duplicate_tool_calls_fail_closed(
    calls: list[ToolCall], code: str
) -> None:
    orchestrator, _ = _orchestrator(
        [LLMResponse(tool_calls=calls)],
        lambda name, args, call_id: pytest.fail("tool must not execute"),
    )
    with pytest.raises(AgentChatError) as caught:
        orchestrator.run(
            messages=[ChatMessage(role="system", content="rules")],
            request_id="unsafe",
        )
    assert caught.value.code == code


def test_tool_round_and_call_budgets_stop_model_loop() -> None:
    config = AgentLLMConfig(
        max_tool_rounds=1,
        max_tool_calls_total=2,
        max_tool_calls_per_round=2,
    )
    responses = [
        LLMResponse(tool_calls=[ToolCall(id="one", name="test.read", arguments={})]),
        LLMResponse(tool_calls=[ToolCall(id="two", name="test.read", arguments={})]),
    ]
    orchestrator, _ = _orchestrator(responses, lambda *args: _payload(), config=config)
    with pytest.raises(AgentChatError) as caught:
        orchestrator.run(
            messages=[ChatMessage(role="system", content="rules")],
            request_id="loop",
        )
    assert caught.value.code == "BUDGET_EXCEEDED"


def test_total_deadline_stops_after_provider_response() -> None:
    clock = iter([0.0, 0.0, 46.0])
    provider = FakeLLMProvider([_final()])
    orchestrator = ToolOrchestrator(
        provider=provider,
        registry=_registry(),
        config=AgentLLMConfig(),
        execute_tool=lambda *args: pytest.fail("tool must not execute"),
        monotonic=lambda: next(clock),
    )

    with pytest.raises(AgentChatError) as caught:
        orchestrator.run(
            messages=[ChatMessage(role="system", content="rules")],
            request_id="deadline",
        )

    assert caught.value.code == "AGENT_DEADLINE_EXCEEDED"
    assert provider.calls[0]["timeout"] == 20.0


def test_forged_or_error_quality_evidence_is_not_cited() -> None:
    compiler = EvidenceCompiler(max_answer_chars=1000)
    forged = compiler.compile(
        final_text=_final("made-up").final_text,
        tool_results=[ToolResultContext("call", "test.read", _payload())],
        inherited_warnings=[],
    )
    assert forged.insufficient_evidence is True
    assert forged.citations == []
    assert "UNVERIFIED_CITATION" in forged.warnings

    payload = _payload()
    payload["evidence"][0]["quality_status"] = "ERROR"
    rejected = compiler.compile(
        final_text=_final("evidence-1").final_text,
        tool_results=[ToolResultContext("call", "test.read", payload)],
        inherited_warnings=[],
    )
    assert rejected.insufficient_evidence is True
    assert "EVIDENCE_QUALITY_ERROR" in rejected.warnings


def test_clarification_without_evidence_is_preserved_but_marked_insufficient() -> None:
    compiled = EvidenceCompiler(max_answer_chars=1000).compile(
        final_text=_final(clarification=True).final_text,
        tool_results=[],
        inherited_warnings=[],
    )
    assert compiled.insufficient_evidence is True
    assert compiled.answer == "这是经过工具验证的研究说明。"
    assert compiled.warnings == ["INSUFFICIENT_EVIDENCE"]


def test_openai_compatible_provider_parses_tools_and_maps_safe_errors() -> None:
    captured: list[httpx.Request] = []

    def success(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            headers={"x-request-id": "provider-1"},
            json={
                "id": "completion-1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "test.read",
                                        "arguments": '{"value":2}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    config = AgentLLMConfig()
    with httpx.Client(transport=httpx.MockTransport(success)) as client:
        response = OpenAICompatibleProvider(config, "secret-key", client=client).complete(
            [ChatMessage(role="user", content="question")],
            [],
            timeout=1,
            request_id="request",
        )
    assert response.tool_calls[0].arguments == {"value": 2}
    assert response.provider_request_id == "provider-1"
    assert captured[0].headers["authorization"] == "Bearer secret-key"

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "secret-key invalid"}})

    with httpx.Client(transport=httpx.MockTransport(unauthorized)) as client:
        provider = OpenAICompatibleProvider(config, "secret-key", client=client)
        with pytest.raises(ProviderError) as caught:
            provider.complete(
                [ChatMessage(role="user", content="question")],
                [],
                timeout=1,
                request_id="request",
            )
    assert caught.value.code == "LLM_AUTHENTICATION_FAILED"
    assert "secret-key" not in str(caught.value)


def test_openai_provider_rejects_non_json_tool_arguments() -> None:
    def invalid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "test.read",
                                        "arguments": "not-json",
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(invalid)) as client:
        provider = OpenAICompatibleProvider(
            AgentLLMConfig(), "secret-key", client=client
        )
        with pytest.raises(ProviderError) as caught:
            provider.complete(
                [ChatMessage(role="user", content="question")],
                [],
                timeout=1,
                request_id="request",
            )
    assert caught.value.code == "LLM_INVALID_RESPONSE"


def test_openai_provider_maps_unsupported_tool_calling_safely() -> None:
    def unsupported(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "tool_calls_unsupported",
                    "message": "This model does not support tool calls for tenant-secret",
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(unsupported)) as client:
        provider = OpenAICompatibleProvider(
            AgentLLMConfig(), "secret-key", client=client
        )
        with pytest.raises(ProviderError) as caught:
            provider.complete(
                [ChatMessage(role="user", content="question")],
                [],
                timeout=1,
                request_id="request",
            )

    assert caught.value.code == "LLM_TOOL_CALL_UNSUPPORTED"
    assert "tenant-secret" not in str(caught.value)
