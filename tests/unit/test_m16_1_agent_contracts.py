from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.agent_config import AgentConfig
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
from sqlalchemy.exc import OperationalError

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

        specs.append(
            ToolSpec(
                name=name,
                version="1.0",
                description=name,
                input_model=model,
                handler=handler,
                layer="DATA",
                max_records=32,
                max_evidence=32,
                max_warnings=32,
                timeout_seconds=5,
            )
        )
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


def test_registry_is_extensible_but_rejects_unsafe_or_invalid_specs() -> None:
    base = next(iter(_registry()._specs.values()))
    ninth = replace(base, name="research.extra")
    assert len(AgentToolRegistry([*list(_registry()._specs.values()), ninth])) == 9
    with pytest.raises(ValueError, match="unique"):
        AgentToolRegistry([base, base])
    for invalid, message in (
        (replace(base, version="latest"), "version"),
        (replace(base, layer="WRITE"), "layer"),
        (replace(base, read_only=False), "read-only"),
        (replace(base, max_records=0), "max_records"),
        (replace(base, timeout_seconds=31), "timeout"),
    ):
        with pytest.raises(ValueError, match=message):
            AgentToolRegistry([invalid], max_timeout_seconds=30)


def test_agent_config_rejects_uncoordinated_or_nonpositive_budgets() -> None:
    with pytest.raises(ValidationError):
        AgentConfig(default_timeout_seconds=0)
    with pytest.raises(ValidationError):
        AgentConfig(default_timeout_seconds=5, statement_timeout_ms=5001)
    with pytest.raises(ValidationError):
        AgentConfig(max_coverage_datasets=33, max_evidence_refs=32)


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


def test_evidence_v2_id_is_canonical_and_changes_with_versioned_facts() -> None:
    first = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="a" * 64,
        calc_run_id="run-1",
        content={"score": Decimal("1.00"), "nested": {"b": 2, "a": 1}},
    )
    same = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="a" * 64,
        calc_run_id="run-1",
        content={"nested": {"a": 1, "b": 2}, "score": Decimal("1.0")},
    )
    changed = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="b" * 64,
        calc_run_id="run-1",
        content={"score": Decimal("1")},
    )
    changed_run = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="a" * 64,
        calc_run_id="run-2",
        content={"score": Decimal("1")},
    )
    changed_content = evidence_ref(
        layer="FACTOR_TREND",
        source_type="derived_record",
        entity_id="000001.SZ",
        date_value=date(2026, 1, 2),
        calc_version="factor_v1",
        config_hash="a" * 64,
        calc_run_id="run-1",
        content={"score": Decimal("2")},
        observed_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert first.evidence_id == same.evidence_id
    assert first.evidence_id != changed.evidence_id
    assert first.evidence_id != changed_run.evidence_id
    assert first.evidence_id != changed_content.evidence_id
    assert first.evidence_version == "v2"
    assert first.content_hash == same.content_hash


def test_application_rejects_unknown_invalid_and_oversized_output() -> None:
    user = SimpleNamespace(username="admin")
    service = AgentApplicationService(object(), get_settings(), registry=_registry())
    with pytest.raises(AgentError, match="unknown agent tool") as unknown:
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


def test_application_enforces_soft_timeout_and_audits_failures(monkeypatch) -> None:
    spec = next(iter(_registry()._specs.values()))
    registry = AgentToolRegistry([replace(spec, timeout_seconds=1)])
    clock_values = iter((0.0, 1.1, 1.1))
    service = AgentApplicationService(
        object(),
        get_settings(),
        registry=registry,
        monotonic=lambda: next(clock_values),
    )
    audit = []
    monkeypatch.setattr(service, "_audit", lambda **fields: audit.append(fields))
    with pytest.raises(AgentError) as caught:
        service.execute(
            tool_name=spec.name,
            raw_input=_INPUTS[spec.name][1],
            request_id="slow-request",
            user=SimpleNamespace(username="admin"),
        )
    assert caught.value.code == "TOOL_TIMEOUT"
    assert caught.value.status_code == 504
    assert audit[0]["error_code"] == "TOOL_TIMEOUT"
    assert audit[0]["duration_ms"] == 1100


def test_application_audits_success_validation_agent_and_unknown_paths(monkeypatch) -> None:
    spec = next(iter(_registry()._specs.values()))
    user = SimpleNamespace(username="admin")

    success_service = AgentApplicationService(
        object(), get_settings(), registry=AgentToolRegistry([spec])
    )
    success_audit = []
    monkeypatch.setattr(
        success_service, "_audit", lambda **fields: success_audit.append(fields)
    )
    success_service.execute(
        tool_name=spec.name,
        raw_input=_INPUTS[spec.name][1],
        request_id="success",
        user=user,
    )
    assert success_audit[0]["status"] == "READY"
    assert success_audit[0]["error_code"] is None

    disabled_service = AgentApplicationService(
        object(),
        get_settings(),
        registry=AgentToolRegistry([replace(spec, enabled=False)]),
    )
    with pytest.raises(AgentError) as disabled:
        disabled_service.execute(
            tool_name=spec.name,
            raw_input=_INPUTS[spec.name][1],
            request_id="disabled",
            user=user,
        )
    assert disabled.value.code == "TOOL_DISABLED"

    validation_audit = []
    monkeypatch.setattr(
        success_service, "_audit", lambda **fields: validation_audit.append(fields)
    )
    with pytest.raises(AgentError) as validation:
        success_service.execute(
            tool_name=spec.name,
            raw_input={"unexpected_secret": "do-not-log"},
            request_id="validation",
            user=user,
        )
    assert validation.value.code == "INVALID_ARGUMENT"
    assert validation_audit[0]["error_code"] == "INVALID_ARGUMENT"
    assert "do-not-log" not in repr(validation_audit)

    for handler, expected_code in (
        (
            lambda _: (_ for _ in ()).throw(
                AgentError("NOT_READY", "not ready", status_code=503)
            ),
            "NOT_READY",
        ),
        (lambda _: (_ for _ in ()).throw(RuntimeError("internal secret")), "INTERNAL_ERROR"),
    ):
        audit = []
        service = AgentApplicationService(
            object(),
            get_settings(),
            registry=AgentToolRegistry([replace(spec, handler=handler)]),
        )
        monkeypatch.setattr(
            service,
            "_audit",
            lambda audit=audit, **fields: audit.append(fields),
        )
        with pytest.raises(AgentError) as caught:
            service.execute(
                tool_name=spec.name,
                raw_input=_INPUTS[spec.name][1],
                request_id="failure",
                user=user,
            )
        assert caught.value.code == expected_code
        assert audit[0]["error_code"] == expected_code
        assert "secret" not in repr(audit)


def test_application_maps_statement_timeout_without_exposing_database_details(
    monkeypatch,
) -> None:
    spec = next(iter(_registry()._specs.values()))
    original = RuntimeError("canceling statement due to statement timeout: secret SQL")
    original.sqlstate = "57014"

    def timed_out(_request):
        raise OperationalError("SELECT secret", {}, original)

    service = AgentApplicationService(
        object(),
        get_settings(),
        registry=AgentToolRegistry([replace(spec, handler=timed_out)]),
    )
    audit = []
    monkeypatch.setattr(service, "_audit", lambda **fields: audit.append(fields))
    with pytest.raises(AgentError) as caught:
        service.execute(
            tool_name=spec.name,
            raw_input=_INPUTS[spec.name][1],
            request_id="sql-timeout",
            user=SimpleNamespace(username="admin"),
        )
    assert caught.value.code == "SQL_STATEMENT_TIMEOUT"
    assert "secret" not in str(caught.value)
    assert audit[0]["error_code"] == "SQL_STATEMENT_TIMEOUT"


def test_application_separates_record_evidence_nested_and_byte_limits() -> None:
    spec = next(iter(_registry()._specs.values()))

    def result_with(**overrides):
        payload = {
            "tool_name": spec.name,
            "status": "READY",
            "records": [{"dataset_coverage": []}],
            "readiness": Readiness(ready=True, code="READY"),
        }
        payload.update(overrides)
        return AgentToolResult(**payload)

    cases = (
        (replace(spec, max_records=1, handler=lambda _: result_with(records=[{}, {}])),),
        (
            replace(
                spec,
                max_evidence=1,
                handler=lambda _: result_with(
                    evidence=[
                        evidence_ref(
                            layer="DATA", source_type="dataset", entity_id=str(index)
                        )
                        for index in range(2)
                    ]
                ),
            ),
        ),
        (
            replace(
                spec,
                nested_limits={"dataset_coverage": 1},
                handler=lambda _: result_with(
                    records=[{"dataset_coverage": [{}, {}]}]
                ),
            ),
        ),
    )
    for (limited_spec,) in cases:
        service = AgentApplicationService(
            object(),
            get_settings(),
            registry=AgentToolRegistry([limited_spec]),
        )
        with pytest.raises(AgentError) as caught:
            service.execute(
                tool_name=spec.name,
                raw_input=_INPUTS[spec.name][1],
                request_id="limit",
                user=SimpleNamespace(username="admin"),
            )
        assert caught.value.code == "RESOURCE_LIMIT_EXCEEDED"
