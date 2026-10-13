import json

import pytest
from app.core.agent_config import AgentConfig
from app.core.agent_llm_config import AgentLLMConfig
from app.domain.agent.frozen_contracts import FrozenContractDraft
from app.services.agent.chat.orchestrator import CapturedToolPayload, ToolOrchestrator
from app.services.agent.llm.contracts import ChatMessage, LLMResponse, ToolCall
from app.services.agent.llm.fake import FakeLLMProvider
from pydantic import ValidationError
from test_m16_2_llm_orchestration import _payload, _registry


def test_contract_capture_requires_archive_and_defaults_off():
    assert not AgentConfig().frozen_contract.enabled
    with pytest.raises(ValidationError, match="require evidence archive"):
        AgentConfig(frozen_contract={"enabled": True})


def test_private_contract_cache_reuses_origin_without_exposing_contract_to_model():
    draft = FrozenContractDraft(
        tool_call_id="call-a", contract_kind="M14_EXACT_BUNDLE", subject_id="run",
        role="LIVE", schema_version="m16.6-m14-bundle-v1",
        verification_scope="FROZEN_CONTRACT_RECHECK",
        contract_json={"status": "GAP", "reason_codes": ["PERIOD_REPORT_MISSING"]},
    )
    provider = FakeLLMProvider([
        LLMResponse(tool_calls=[
            ToolCall(id="call-a", name="test.read", arguments={}),
            ToolCall(id="call-b", name="test.read", arguments={}),
        ]),
        LLMResponse(final_text="done"),
    ])
    calls = []

    def execute(*args):
        calls.append(args)
        return CapturedToolPayload(_payload(), {}, [draft])

    result = ToolOrchestrator(
        provider=provider, registry=_registry(), config=AgentLLMConfig(), execute_tool=execute,
    ).run(messages=[ChatMessage(role="system", content="test")], request_id="private")
    assert len(calls) == 1
    assert result.tool_results[1].cache_origin_call_id == "call-a"
    assert result.tool_results[1].frozen_contracts[0].tool_call_id == "call-b"
    assert result.tool_results[0].frozen_contracts[0].tool_call_id == "call-a"
    for message in provider.calls[1]["messages"]:
        if message.role == "tool":
            assert json.loads(message.content) == _payload()
            assert "contract_json" not in message.content
