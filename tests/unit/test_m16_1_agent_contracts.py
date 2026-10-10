from datetime import date
from types import SimpleNamespace

import pytest
from app.core.config import get_settings
from app.domain.agent.contracts import (
    AgentToolResult,
    BacktestSummaryInput,
    DataCoverageInput,
    MarketSnapshotInput,
    OpportunityListInput,
    PerformanceSummaryInput,
    Readiness,
    SectorTopInput,
    ThemeTopInput,
    WalkForwardSummaryInput,
)
from app.domain.agent.errors import AgentError
from app.services.agent.application import AgentApplicationService
from app.services.agent.evidence import evidence_ref
from app.services.agent.registry import AgentToolRegistry, ToolSpec
from pydantic import ValidationError

_INPUTS = {
    "data.coverage": (DataCoverageInput, {"start_date": "2026-01-01", "end_date": "2026-01-02"}),
    "market.snapshot": (MarketSnapshotInput, {}),
    "sector.top": (SectorTopInput, {"limit": 2}),
    "theme.top": (ThemeTopInput, {"limit": 2}),
    "opportunity.list": (OpportunityListInput, {"stage": "TREND", "limit": 2}),
    "backtest.summary": (
        BacktestSummaryInput,
        {"run_id": "11111111-1111-1111-1111-111111111111"},
    ),
    "performance.summary": (
        PerformanceSummaryInput,
        {"report_id": "22222222-2222-2222-2222-222222222222"},
    ),
    "walk_forward.summary": (
        WalkForwardSummaryInput,
        {
            "study_id": "33333333-3333-3333-3333-333333333333",
            "validation_id": "44444444-4444-4444-4444-444444444444",
        },
    ),
}


def _registry(*, large: bool = False) -> AgentToolRegistry:
    specs = []
    for name, (model, _) in _INPUTS.items():

        def handler(request, tool_name=name):
            record = {"value": "x" * 70_000} if large else {"selector": request.model_dump()}
            return AgentToolResult(
                tool_name=tool_name,
                status="READY",
                as_of_date=date(2026, 1, 2),
                records=[record],
                readiness=Readiness(ready=True, code="READY"),
            )

        specs.append(ToolSpec(name, "1.0", name, model, handler, "DATA", 32, 5))
    return AgentToolRegistry(specs)


def test_registry_contains_only_the_eight_fixed_tools_and_executes_each() -> None:
    registry = _registry()
    assert len(registry) == 8
    assert {item["name"] for item in registry.catalog()} == set(_INPUTS)
    service = AgentApplicationService(object(), get_settings(), registry=registry)
    user = SimpleNamespace(username="admin")
    for name, (_, payload) in _INPUTS.items():
        first = service.execute(
            tool_name=name,
            raw_input=payload,
            request_id="stable-request",
            user=user,
        )
        second = service.execute(
            tool_name=name,
            raw_input=payload,
            request_id="stable-request",
            user=user,
        )
        assert first == second
        assert first["tool_name"] == name
        assert first["tool_version"] == "1.0"


def test_contracts_reject_extra_fields_limits_ranges_and_ambiguous_reports() -> None:
    with pytest.raises(ValidationError):
        SectorTopInput(limit=21)
    with pytest.raises(ValidationError):
        OpportunityListInput(stage="ARBITRARY")
    with pytest.raises(ValidationError):
        MarketSnapshotInput(sql="select * from stock_daily")
    with pytest.raises(ValidationError):
        DataCoverageInput(start_date=date(2025, 1, 1), end_date=date(2026, 1, 2))
    with pytest.raises(ValidationError):
        PerformanceSummaryInput()
    with pytest.raises(ValidationError):
        PerformanceSummaryInput(
            run_id="11111111-1111-1111-1111-111111111111",
            report_id="22222222-2222-2222-2222-222222222222",
        )


def test_evidence_id_is_deterministic_and_changes_with_source_identity() -> None:
    first = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="a" * 64,
    )
    same = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="a" * 64,
    )
    changed = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="b" * 64,
    )
    assert first.evidence_id == same.evidence_id
    assert first.evidence_id != changed.evidence_id


def test_application_rejects_unknown_invalid_and_oversized_output() -> None:
    user = SimpleNamespace(username="admin")
    service = AgentApplicationService(object(), get_settings(), registry=_registry())
    with pytest.raises(AgentError, match="unknown tool") as unknown:
        service.execute(tool_name="sql.execute", raw_input={}, request_id="r", user=user)
    assert unknown.value.code == "INVALID_TOOL"
    with pytest.raises(AgentError) as invalid:
        service.execute(
            tool_name="sector.top",
            raw_input={"limit": 2000},
            request_id="r",
            user=user,
        )
    assert invalid.value.code == "INVALID_ARGUMENT"
    large = AgentApplicationService(object(), get_settings(), registry=_registry(large=True))
    with pytest.raises(AgentError) as oversized:
        large.execute(tool_name="market.snapshot", raw_input={}, request_id="r", user=user)
    assert oversized.value.code == "OUTPUT_LIMIT_EXCEEDED"
