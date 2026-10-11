import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from app.core.agent_db import _effective_statement_timeout_ms
from app.core.agent_llm_config import AgentLLMConfig
from app.domain.agent.chat_errors import AgentChatError
from app.domain.agent.errors import AgentError
from app.services.agent.chat.evidence_compiler import EvidenceCompiler
from app.services.agent.chat.orchestrator import ToolOrchestrator, ToolResultContext
from app.services.agent.chat.request_identity import (
    normalize_request_content,
    request_content_hash,
)
from app.services.agent.llm.contracts import ChatMessage, LLMResponse, ToolCall
from app.services.agent.llm.fake import FakeLLMProvider
from app.services.agent.registry import AgentToolRegistry, ToolSpec
from pydantic import BaseModel, ConfigDict


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = 1


def _registry() -> AgentToolRegistry:
    return AgentToolRegistry(
        [
            ToolSpec(
                name="test.read",
                version="1.0",
                description="Read test data.",
                input_model=_Input,
                handler=lambda request: None,
                layer="DATA",
                max_records=2,
                max_evidence=2,
                max_warnings=2,
                timeout_seconds=2,
            )
        ]
    )


def _context(
    *,
    tool_name: str,
    evidence_id: str,
    entity: str,
    trade_date: str,
    records: list[dict[str, Any]],
    identity: dict[str, Any] | None = None,
    evidence_extra: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> ToolResultContext:
    refs = evidence or [
        {
            "evidence_id": evidence_id,
            "evidence_version": "v2",
            "entity_id": entity,
            "trade_date": trade_date,
            "quality_status": "PASS",
            "calc_version": "calc-v1",
            "config_hash": "config-v1",
            "content_hash": "c" * 64,
            **(evidence_extra or {}),
        }
    ]
    return ToolResultContext(
        tool_call_id=f"call-{evidence_id}",
        tool_name=tool_name,
        payload={
            "tool_name": tool_name,
            "status": "READY",
            "as_of_date": trade_date,
            "identity": identity
            or {"calc_version": "calc-v1", "config_hash": "config-v1"},
            "records": records,
            "evidence": refs,
            "warnings": [],
            "readiness": {"ready": True, "code": "READY", "details": {}},
        },
    )


def _compile(
    claims: list[dict[str, Any]],
    contexts: list[ToolResultContext],
) -> Any:
    evidence_ids = [
        evidence_id
        for claim in claims
        for evidence_id in claim.get("evidence_ids", [])
    ]
    return EvidenceCompiler(max_answer_chars=8000).compile(
        final_text=json.dumps(
            {
                "answer": "模型原始文本中的数字不应直接进入正式答案。",
                "evidence_ids": evidence_ids,
                "claims": claims,
                "warnings": [],
                "needs_clarification": False,
            },
            ensure_ascii=False,
        ),
        tool_results=contexts,
        inherited_warnings=[],
    )


def _fact(
    *,
    evidence_id: str = "market-1",
    path: str = "records.0.breadth.up_rate",
    value: Any = 12.5,
    unit: str = "percent",
    trade_date: str = "2026-10-10",
    entity: str = "market",
) -> dict[str, Any]:
    return {
        "claim_id": "fact-1",
        "claim_type": "FACT",
        "text": "模型声称错误的 99%。",
        "evidence_ids": [evidence_id],
        "structured_facts": [
            {
                "path": path,
                "value": value,
                "unit": unit,
                "trade_date": trade_date,
                "entity": entity,
            }
        ],
        "quality_status": "UNKNOWN",
    }


def test_verified_numeric_claim_uses_decimal_percent_normalization_and_safe_text() -> None:
    context = _context(
        tool_name="market.snapshot",
        evidence_id="market-1",
        entity="market",
        trade_date="2026-10-10",
        records=[{"breadth": {"up_rate": "0.125"}}],
    )
    compiled = _compile([_fact()], [context])

    assert compiled.insufficient_evidence is False
    assert compiled.claims[0].quality_status == "PASS"
    assert compiled.claims[0].text == (
        "已验证事实：market records.0.breadth.up_rate=12.5 percent (2026-10-10)。"
    )
    assert "99%" not in compiled.answer
    assert "[E1]" in compiled.answer


@pytest.mark.parametrize(
    "change,code",
    [
        ({"value": 13}, "VALUE_MISMATCH"),
        ({"entity": "another-market"}, "ENTITY_MISMATCH"),
        ({"trade_date": "2026-10-09"}, "TRADE_DATE_MISMATCH"),
        ({"unit": "count"}, "UNIT_MISMATCH"),
        ({"path": "records.0.uncontrolled.return"}, "UNCONTROLLED_FIELD_PATH"),
        ({"evidence_id": "forged"}, "UNKNOWN_EVIDENCE_ID"),
    ],
)
def test_numeric_fact_mismatches_fail_closed(change: dict[str, Any], code: str) -> None:
    context = _context(
        tool_name="market.snapshot",
        evidence_id="market-1",
        entity="market",
        trade_date="2026-10-10",
        records=[{"breadth": {"up_rate": "0.125"}}],
    )
    compiled = _compile([_fact(**change)], [context])

    assert compiled.insufficient_evidence is True
    assert compiled.citations == []
    assert f"CLAIM_REJECTED:fact-1:{code}" in compiled.warnings


def test_inference_is_explicitly_downgraded_to_warning_quality() -> None:
    context = _context(
        tool_name="market.snapshot",
        evidence_id="market-1",
        entity="market",
        trade_date="2026-10-10",
        records=[{"breadth": {"up_rate": "0.125"}}],
    )
    claim = {
        "claim_id": "inference-1",
        "claim_type": "INFERENCE",
        "text": "模型的推断语言不会被当作事实。",
        "evidence_ids": ["market-1"],
        "structured_facts": [],
        "quality_status": "PASS",
    }
    compiled = _compile([claim], [context])

    assert compiled.insufficient_evidence is False
    assert compiled.claims[0].quality_status == "WARNING"
    assert "推断" in compiled.claims[0].text


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(AgentChatError) as caught:
        EvidenceCompiler(max_answer_chars=1000).compile(
            final_text="not-json",
            tool_results=[],
            inherited_warnings=[],
        )
    assert caught.value.code == "LLM_INVALID_RESPONSE"


def test_legal_entity_over_time_comparison_requires_context() -> None:
    first = _context(
        tool_name="market.snapshot",
        evidence_id="market-1",
        entity="market",
        trade_date="2026-10-09",
        records=[{"market_score": "60"}],
    )
    second = _context(
        tool_name="market.snapshot",
        evidence_id="market-2",
        entity="market",
        trade_date="2026-10-10",
        records=[{"market_score": "65"}],
    )
    claim = {
        "claim_id": "comparison-1",
        "claim_type": "COMPARISON",
        "comparison_type": "ENTITY_OVER_TIME",
        "text": "跨日变化。",
        "evidence_ids": ["market-1", "market-2"],
        "structured_facts": [
            {
                "path": "records.0.market_score",
                "value": 60,
                "unit": "score",
                "trade_date": "2026-10-09",
                "entity": "market",
            },
            {
                "path": "records.0.market_score",
                "value": 65,
                "unit": "score",
                "trade_date": "2026-10-10",
                "entity": "market",
            },
        ],
        "quality_status": "UNKNOWN",
    }
    compiled = _compile([claim], [first, second])

    assert compiled.insufficient_evidence is False
    assert "COMPARISON_REQUIRES_CONTEXT:ENTITY_OVER_TIME" in compiled.warnings


def test_same_date_ranking_rejects_mixed_calculation_identity() -> None:
    evidence = [
        {
            "evidence_id": "sector-1",
            "evidence_version": "v2",
            "entity_id": "sector-a",
            "trade_date": "2026-10-10",
            "quality_status": "PASS",
            "calc_version": "sector-v1",
            "config_hash": "config-a",
        },
        {
            "evidence_id": "sector-2",
            "evidence_version": "v2",
            "entity_id": "sector-b",
            "trade_date": "2026-10-10",
            "quality_status": "PASS",
            "calc_version": "sector-v1",
            "config_hash": "config-b",
        },
    ]
    context = _context(
        tool_name="sector.top",
        evidence_id="unused",
        entity="unused",
        trade_date="2026-10-10",
        records=[{"heat_rank": 1}, {"heat_rank": 2}],
        evidence=evidence,
    )
    claim = {
        "claim_id": "comparison-1",
        "claim_type": "COMPARISON",
        "comparison_type": "SAME_DATE_RANKING",
        "text": "排名比较。",
        "evidence_ids": ["sector-1", "sector-2"],
        "structured_facts": [
            {
                "path": "records.0.heat_rank",
                "value": 1,
                "unit": "rank",
                "trade_date": "2026-10-10",
                "entity": "sector-a",
            },
            {
                "path": "records.1.heat_rank",
                "value": 2,
                "unit": "rank",
                "trade_date": "2026-10-10",
                "entity": "sector-b",
            },
        ],
        "quality_status": "UNKNOWN",
    }
    compiled = _compile([claim], [context])

    assert compiled.insufficient_evidence is True
    assert "CLAIM_REJECTED:comparison-1:COMPARISON_INCOMPATIBLE" in compiled.warnings


def test_train_oos_policy_rejects_oos_label_on_training_evidence() -> None:
    context = _context(
        tool_name="performance.summary",
        evidence_id="train-1",
        entity="run-1",
        trade_date="2026-10-10",
        records=[{"performance": {"cumulative_return": "0.1"}}],
        evidence_extra={"calc_run_id": "run-1", "source_hash": "s" * 64},
    )
    claim = {
        "claim_id": "comparison-1",
        "claim_type": "COMPARISON",
        "comparison_type": "TRAIN_VS_OOS",
        "text": "训练与样本外比较。",
        "evidence_ids": ["train-1"],
        "structured_facts": [
            {
                "path": "records.0.performance.cumulative_return",
                "value": 0.1,
                "unit": "decimal",
                "trade_date": "2026-10-10",
                "entity": "run-1",
                "sample_role": "TRAIN",
            },
            {
                "path": "records.0.performance.cumulative_return",
                "value": 0.1,
                "unit": "decimal",
                "trade_date": "2026-10-10",
                "entity": "run-1",
                "sample_role": "OOS",
            },
        ],
        "quality_status": "UNKNOWN",
    }
    compiled = _compile([claim], [context])

    assert compiled.insufficient_evidence is True
    assert "CLAIM_REJECTED:comparison-1:COMPARISON_INCOMPATIBLE" in compiled.warnings


def test_request_hash_normalization_is_stable_and_identity_bound() -> None:
    chat_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    first = request_content_hash(
        content="Ａ股研究  \r\n第二行\r\n",
        chat_id=chat_id,
        owner_id=owner_id,
    )
    second = request_content_hash(
        content="A股研究\n第二行",
        chat_id=chat_id,
        owner_id=owner_id,
    )

    assert normalize_request_content(" x  \r\n") == "x"
    assert first == second
    assert len(first) == 64
    assert request_content_hash(
        content="A股研究\n第二行",
        chat_id=uuid.uuid4(),
        owner_id=owner_id,
    ) != first
    assert request_content_hash(
        content="A股研究\n第二行",
        chat_id=chat_id,
        owner_id=uuid.uuid4(),
    ) != first


@dataclass
class _Clock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value


def _final_response() -> LLMResponse:
    return LLMResponse(
        final_text=json.dumps(
            {
                "answer": "需要更多证据。",
                "evidence_ids": [],
                "claims": [],
                "warnings": [],
                "needs_clarification": True,
            }
        )
    )


def test_slow_tool_cannot_return_success_after_total_deadline() -> None:
    clock = _Clock()
    provider = FakeLLMProvider(
        [
            LLMResponse(
                tool_calls=[ToolCall(id="call-1", name="test.read", arguments={})]
            ),
            _final_response(),
        ]
    )
    remaining_seen: list[float] = []

    def execute(
        name: str,
        arguments: dict[str, Any],
        call_id: str,
        remaining_seconds: float,
    ) -> dict[str, Any]:
        remaining_seen.append(remaining_seconds)
        clock.value += 1.1
        return {
            "records": [{"value": 1}],
            "evidence": [],
            "warnings": [],
            "readiness": {"ready": True, "code": "READY"},
        }

    orchestrator = ToolOrchestrator(
        provider=provider,
        registry=_registry(),
        config=AgentLLMConfig(
            request_timeout_seconds=1,
            max_total_deadline_seconds=1,
        ),
        execute_tool=execute,
        monotonic=clock,
    )
    with pytest.raises(AgentChatError) as caught:
        orchestrator.run(
            messages=[ChatMessage(role="system", content="rules")],
            request_id="slow-tool",
        )

    assert caught.value.code == "TOTAL_DEADLINE_EXCEEDED"
    assert remaining_seen == [1.0]


def test_cached_tool_audit_is_still_inside_total_deadline() -> None:
    clock = _Clock()
    provider = FakeLLMProvider(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(id="call-1", name="test.read", arguments={}),
                    ToolCall(id="call-2", name="test.read", arguments={}),
                ]
            ),
            _final_response(),
        ]
    )

    def audit(item: Any) -> None:
        if item.cache_reused:
            clock.value += 2.1

    orchestrator = ToolOrchestrator(
        provider=provider,
        registry=_registry(),
        config=AgentLLMConfig(
            request_timeout_seconds=2,
            max_total_deadline_seconds=2,
        ),
        execute_tool=lambda *args: {
            "records": [{"value": 1}],
            "evidence": [],
            "warnings": [],
            "readiness": {"ready": True, "code": "READY"},
        },
        audit_tool_call=audit,
        monotonic=clock,
    )
    with pytest.raises(AgentChatError) as caught:
        orchestrator.run(
            messages=[ChatMessage(role="system", content="rules")],
            request_id="cache-deadline",
        )

    assert caught.value.code == "TOTAL_DEADLINE_EXCEEDED"


@pytest.mark.parametrize("code", ["TOOL_TIMEOUT", "STATEMENT_TIMEOUT"])
def test_tool_and_statement_timeouts_abort_the_turn(code: str) -> None:
    provider = FakeLLMProvider(
        [
            LLMResponse(
                tool_calls=[ToolCall(id="call-1", name="test.read", arguments={})]
            )
        ]
    )
    audits: list[Any] = []

    def execute(*args: Any) -> dict[str, Any]:
        raise AgentError(code, "safe timeout", status_code=504)

    orchestrator = ToolOrchestrator(
        provider=provider,
        registry=_registry(),
        config=AgentLLMConfig(),
        execute_tool=execute,
        audit_tool_call=audits.append,
    )
    with pytest.raises(AgentChatError) as caught:
        orchestrator.run(
            messages=[ChatMessage(role="system", content="rules")],
            request_id="fatal-timeout",
        )

    assert caught.value.code == code
    assert audits[0].status == "ERROR"
    assert audits[0].error_code == code


def test_statement_timeout_is_positive_and_never_exceeds_remaining_budget() -> None:
    assert _effective_statement_timeout_ms(5000, 1.2349) == 1234
    assert _effective_statement_timeout_ms(500, 5) == 500
    with pytest.raises(ValueError, match="below one millisecond"):
        _effective_statement_timeout_ms(5000, 0.0009)
