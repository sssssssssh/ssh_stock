import json
import uuid
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.core.agent_config import AgentConfig
from app.domain.agent.archive import AgentArchiveError
from app.domain.agent.contracts import AgentToolResult, WalkForwardWindowLineageInput
from app.domain.agent.frozen_contracts import FrozenContractDraft
from app.services.agent.application import AgentApplicationService
from app.services.agent.chat.application import AgentChatApplication
from app.services.agent.contracts.canonical import contract_hash
from app.services.agent.llm.contracts import LLMResponse, ToolCall
from app.services.agent.llm.fake import FakeLLMProvider
from app.services.agent.registry import AgentToolRegistry, ToolSpec


def entry_case(monkeypatch, *, maximum=100, enabled=True, responses=()):
    config = AgentConfig(
        mode="llm_chat", llm_enabled=True,
        archive={"enabled": enabled},
        frozen_contract={"enabled": enabled, "max_contracts": maximum},
    )
    settings = SimpleNamespace(agent_config=config)
    calls, audits, completed, failed = [], [], [], []
    captured = []

    class DB:
        def rollback(self):
            pass

    db = DB()

    @contextmanager
    def session(*args, **kwargs):
        yield db

    def result(request):
        return AgentToolResult(
            tool_name="walk_forward.window_lineage", status="READY",
            identity={
                "study_id": str(request.study_id), "validation_id": str(request.validation_id),
            },
            records=[{"window_no": n + request.offset + 1} for n in range(request.limit)],
            readiness={"ready": True, "code": "READY"},
        )

    registry = AgentToolRegistry([ToolSpec(
        name="walk_forward.window_lineage", version="1.0", description="Synthetic windows",
        input_model=WalkForwardWindowLineageInput, handler=result,
        layer="STRATEGY_VALIDATION", max_records=50, max_evidence=50,
        max_warnings=20, timeout_seconds=5,
    )])

    def collect(db, result, *, tool_call_id, max_trade_dates, max_contracts):
        calls.append((tool_call_id, max_contracts))
        drafts = [FrozenContractDraft(
            tool_call_id=tool_call_id, contract_kind="M14_EXACT_BUNDLE",
            subject_id=f"window-{record['window_no']}-{part}", role="TRAIN",
            schema_version="m16.6-m14-bundle-v1", verification_scope="FROZEN_CONTRACT_RECHECK",
            contract_json={"status": "GAP", "reason_codes": ["SYNTHETIC_UNIT_ONLY"]},
        ) for record in result.records for part in range(3)]
        captured.extend(drafts)
        return drafts

    monkeypatch.setattr("app.services.agent.chat.application.agent_db_session", session)
    monkeypatch.setattr("app.services.agent.contracts.m15.capture_m15_contracts", collect)
    monkeypatch.setattr(
        "app.services.agent.chat.application.AgentApplicationService",
        lambda db, settings: AgentApplicationService(db, settings, registry=registry),
    )
    service = AgentChatApplication(db, settings, provider=FakeLLMProvider(list(responses)))
    monkeypatch.setattr(service, "_schema_registry", lambda: registry)
    service.repo = SimpleNamespace(recent_messages=lambda **kwargs: ([], False))
    turn = SimpleNamespace(id=uuid.uuid4(), trace_id=uuid.uuid4())
    monkeypatch.setattr(service, "_start_turn", lambda **kwargs: (turn, None))
    monkeypatch.setattr(service, "_persist_tool_call", lambda turn_id, audit: audits.append(audit))
    monkeypatch.setattr(service, "_fail_turn", lambda *args: failed.append(args))
    monkeypatch.setattr(service, "_audit_turn", lambda *args: None)
    monkeypatch.setattr(
        service, "_complete_turn", lambda **kwargs: completed.append(kwargs) or kwargs,
    )
    monkeypatch.setattr(
        "app.services.agent.chat.application.EvidenceCompiler.compile",
        lambda *args, **kwargs: SimpleNamespace(
            claims=[], citations=[], rejected_claims=[], answer="synthetic",
            answer_status="COMPLETED", needs_clarification=True, warnings=[],
        ),
    )
    monkeypatch.setattr(
        "app.services.agent.chat.application.assemble_archive",
        lambda **kwargs: SimpleNamespace(
            tools=[SimpleNamespace(tool_call_id=context.tool_call_id)
                   for context in kwargs["tool_results"]]
        ),
    )
    parameters = {"study_id": str(uuid.uuid4()), "validation_id": str(uuid.uuid4())}
    user = SimpleNamespace(id=uuid.uuid4())
    return SimpleNamespace(
        service=service, parameters=parameters, user=user, calls=calls, audits=audits,
        completed=completed, failed=failed, captured=captured, registry=registry, db=db,
        settings=settings,
    )


def final():
    return LLMResponse(final_text=json.dumps({"answer": "synthetic"}))


def send(case, request_id="turn"):
    return case.service.send_message(
        user=case.user, chat_id=uuid.uuid4(), content="synthetic", request_id=request_id,
    )


@pytest.mark.parametrize("existing,limit", [(0, 37), (95, 2)])
def test_direct_capture_entry_refuses_before_bulk_collect(monkeypatch, existing, limit):
    case = entry_case(monkeypatch)
    with pytest.raises(AgentArchiveError) as caught:
        case.service._execute_tool(
            user=case.user, request_id="direct", tool_call_id="windows",
            tool_name="walk_forward.window_lineage", arguments={**case.parameters, "limit": limit},
            remaining_seconds=30, existing_contract_count=existing,
        )
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"
    assert case.calls == []


def test_manual_read_remains_readonly_but_chat_capture_checks_same_full_result(monkeypatch):
    case = entry_case(monkeypatch)
    payload = AgentApplicationService(case.db, case.settings, registry=case.registry).execute(
        tool_name="walk_forward.window_lineage", raw_input={**case.parameters, "limit": 37},
        request_id="manual-read", user=case.user,
    )
    assert len(payload["records"]) == 37
    assert "frozen_contracts" not in payload and case.calls == []
    with pytest.raises(AgentArchiveError):
        case.service._execute_tool(
            user=case.user, request_id="chat-capture", tool_call_id="windows",
            tool_name="walk_forward.window_lineage", arguments={**case.parameters, "limit": 37},
            remaining_seconds=30,
        )


def test_entry_capture_precedes_compact_serialization(monkeypatch):
    case = entry_case(monkeypatch)
    monkeypatch.setattr(
        "app.services.agent.application.serialized_result",
        lambda *args, **kwargs: pytest.fail("over-budget full result must precede serialization"),
    )
    with pytest.raises(AgentArchiveError) as caught:
        case.service._execute_tool(
            user=case.user, request_id="compact", tool_call_id="windows",
            tool_name="walk_forward.window_lineage", arguments={**case.parameters, "limit": 37},
            remaining_seconds=30,
        )
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"


def test_remaining_budget_does_not_change_public_archive_payload_or_private_contract_hashes(
    monkeypatch,
):
    from app.services.agent.archive.canonical import archive_hash

    case = entry_case(monkeypatch, maximum=9)
    arguments = {**case.parameters, "limit": 2}
    before = deepcopy(arguments)
    expected = AgentApplicationService(case.db, case.settings, registry=case.registry).execute(
        tool_name="walk_forward.window_lineage", raw_input=arguments,
        request_id="manual", user=case.user,
    )
    captured = case.service._execute_tool(
        user=case.user, request_id="chat", tool_call_id="windows",
        tool_name="walk_forward.window_lineage", arguments=arguments,
        remaining_seconds=30, existing_contract_count=3,
    )
    assert dict(captured) == expected
    assert archive_hash(captured) == archive_hash(expected)
    assert arguments == before
    assert case.calls == [("windows", 6)]
    expected_body = {"status": "GAP", "reason_codes": ["SYNTHETIC_UNIT_ONLY"]}
    assert len(captured.frozen_contracts) == 6
    assert all(draft.contract_json == expected_body for draft in captured.frozen_contracts)
    assert all(contract_hash(draft.contract_json) == contract_hash(expected_body)
               for draft in captured.frozen_contracts)


@pytest.mark.parametrize("separate_rounds", [False, True])
def test_actual_chat_counts_all_calls_across_rounds(monkeypatch, separate_rounds):
    case = entry_case(monkeypatch, maximum=9)
    first = ToolCall(id="first", name="walk_forward.window_lineage",
                     arguments={**case.parameters, "limit": 2})
    second = ToolCall(id="second", name="walk_forward.window_lineage",
                      arguments={**case.parameters, "limit": 2, "offset": 2})
    responses = ([LLMResponse(tool_calls=[first]), LLMResponse(tool_calls=[second])]
                 if separate_rounds else [LLMResponse(tool_calls=[first, second])])
    case.service._provider = FakeLLMProvider(responses + [final()])
    with pytest.raises(AgentArchiveError) as caught:
        send(case)
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"
    assert case.calls == [("first", 9)]
    assert case.failed[0][1] == "CONTRACT_LIMIT_EXCEEDED"
    assert case.completed == []


@pytest.mark.parametrize("maximum,next_call", [(5, False), (8, True)])
def test_cached_contract_copies_are_counted_before_next_bulk_collect(
    monkeypatch, maximum, next_call,
):
    case = entry_case(monkeypatch, maximum=maximum)
    calls = [ToolCall(id=name, name="walk_forward.window_lineage",
                      arguments={**case.parameters, "limit": 1}) for name in ("original", "cached")]
    if next_call:
        calls.append(ToolCall(id="next", name="walk_forward.window_lineage",
                              arguments={**case.parameters, "limit": 1, "offset": 1}))
    case.service._provider = FakeLLMProvider([LLMResponse(tool_calls=calls), final()])
    with pytest.raises(AgentArchiveError) as caught:
        send(case)
    assert caught.value.code == "CONTRACT_LIMIT_EXCEEDED"
    assert case.calls == [("original", maximum)]
    assert case.completed == []


def test_exact_turn_allowance_and_new_turn_reset_keep_private_source_hashes(monkeypatch):
    case = entry_case(monkeypatch, maximum=9)
    calls = [ToolCall(id=name, name="walk_forward.window_lineage",
                      arguments={**case.parameters, "limit": 1}) for name in ("original", "cached")]
    calls.append(ToolCall(id="next", name="walk_forward.window_lineage",
                          arguments={**case.parameters, "limit": 1, "offset": 1}))
    for request_id in ("one", "two"):
        case.service._provider = FakeLLMProvider([LLMResponse(tool_calls=deepcopy(calls)), final()])
        send(case, request_id)
    assert case.calls == [("original", 9), ("next", 3)] * 2
    assert all(len(turn["frozen_contracts"]) == 9 for turn in case.completed)
    expected_body = {"status": "GAP", "reason_codes": ["SYNTHETIC_UNIT_ONLY"]}
    for turn in case.completed:
        for draft in turn["frozen_contracts"]:
            assert draft.contract_json == expected_body
            assert contract_hash(draft.contract_json) == contract_hash(expected_body)
    assert sum(audit.cache_reused for audit in case.audits) == 2
    assert "frozen_contracts" not in case.service._provider.calls[1]["messages"][-1].content


def test_disabled_capture_does_not_consume_contract_allowance(monkeypatch):
    case = entry_case(monkeypatch, maximum=1, enabled=False)
    case.service._provider = FakeLLMProvider([LLMResponse(tool_calls=[ToolCall(
        id="windows", name="walk_forward.window_lineage",
        arguments={**case.parameters, "limit": 37},
    )]), final()])
    send(case)
    assert case.calls == [] and case.failed == []
    assert "frozen_contracts" not in case.completed[0]
