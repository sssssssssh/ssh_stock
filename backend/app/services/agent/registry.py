import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.core.agent_config import AgentConfig
from app.domain.agent.contracts import (
    AgentToolResult,
    BacktestSummaryInput,
    DataCoverageInput,
    MarketSnapshotInput,
    OpportunityListInput,
    PerformanceSummaryInput,
    SectorTopInput,
    ThemeTopInput,
    WalkForwardSummaryInput,
)
from app.domain.agent.errors import AgentError
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.adapters.opportunities import OpportunityAgentAdapter
from app.services.agent.adapters.research import ResearchAgentAdapter

DEFAULT_TOOL_NAMES = frozenset(
    {
        "data.coverage",
        "market.snapshot",
        "sector.top",
        "theme.top",
        "opportunity.list",
        "backtest.summary",
        "performance.summary",
        "walk_forward.summary",
    }
)
_ALLOWED_LAYERS = frozenset({"DATA", "FACTOR_TREND", "STRATEGY_VALIDATION"})
_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_VERSION_RE = re.compile(r"^[1-9]\d*\.\d+$")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any], AgentToolResult]
    layer: str
    max_records: int
    max_evidence: int
    max_warnings: int
    timeout_seconds: int
    read_only: bool = True
    enabled: bool = True
    nested_limits: dict[str, int] = field(default_factory=dict)

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "layer": self.layer,
            "read_only": self.read_only,
            "enabled": self.enabled,
            "max_records": self.max_records,
            "record_limit_semantics": "top_level_records_only",
            "max_evidence": self.max_evidence,
            "max_warnings": self.max_warnings,
            "nested_limits": dict(sorted(self.nested_limits.items())),
            "timeout_seconds": self.timeout_seconds,
            "timeout_semantics": "soft_end_to_end_budget_post_execution_check",
            "input_schema": self.input_model.model_json_schema(),
        }


class AgentToolRegistry:
    def __init__(self, specs: list[ToolSpec], *, max_timeout_seconds: int = 30) -> None:
        if not specs:
            raise ValueError("agent registry must contain at least one explicit tool")
        if max_timeout_seconds <= 0:
            raise ValueError("registry timeout cap must be positive")
        names = [spec.name for spec in specs]
        if len(names) != len(set(names)):
            raise ValueError("agent tool names must be unique")
        for spec in specs:
            self._validate_spec(spec, max_timeout_seconds=max_timeout_seconds)
        self._specs = {spec.name: spec for spec in specs}

    @staticmethod
    def _validate_spec(spec: ToolSpec, *, max_timeout_seconds: int) -> None:
        if not _TOOL_NAME_RE.fullmatch(spec.name):
            raise ValueError(f"invalid agent tool name: {spec.name}")
        if not _VERSION_RE.fullmatch(spec.version):
            raise ValueError(f"invalid agent tool version: {spec.version}")
        if spec.layer not in _ALLOWED_LAYERS:
            raise ValueError(f"invalid agent tool layer: {spec.layer}")
        if spec.read_only is not True:
            raise ValueError("agent registry accepts read-only tools only")
        if not isinstance(spec.enabled, bool):
            raise ValueError("agent tool enabled flag must be boolean")
        if not isinstance(spec.input_model, type) or not issubclass(spec.input_model, BaseModel):
            raise ValueError("agent tool input_model must be a Pydantic model")
        if not callable(spec.handler):
            raise ValueError("agent tool handler must be callable")
        for field_name in ("max_records", "max_evidence", "max_warnings"):
            value = getattr(spec, field_name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"agent tool {field_name} must be a positive integer")
        if type(spec.timeout_seconds) is not int or spec.timeout_seconds <= 0:
            raise ValueError("agent tool timeout_seconds must be a positive integer")
        if spec.timeout_seconds > max_timeout_seconds:
            raise ValueError("agent tool timeout exceeds the registry timeout cap")
        for name, value in spec.nested_limits.items():
            if not name or type(value) is not int or value <= 0:
                raise ValueError("agent tool nested limits must be named positive integers")

    def get(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise AgentError("INVALID_TOOL", "unknown agent tool", status_code=422) from exc

    def catalog(self) -> list[dict[str, Any]]:
        return [self._specs[name].catalog_entry() for name in sorted(self._specs)]

    def __len__(self) -> int:
        return len(self._specs)


def build_registry(
    market: MarketDataAgentAdapter,
    opportunities: OpportunityAgentAdapter,
    research: ResearchAgentAdapter,
    *,
    config: AgentConfig,
) -> AgentToolRegistry:
    specs = [
        ToolSpec(
            name="data.coverage",
            version="1.0",
            description="Summarize persisted data-quality coverage for a bounded date range.",
            input_model=DataCoverageInput,
            handler=market.data_coverage,
            layer="DATA",
            max_records=1,
            max_evidence=config.max_coverage_datasets,
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
            nested_limits={"dataset_coverage": config.max_coverage_datasets},
        ),
        ToolSpec(
            name="market.snapshot",
            version="1.0",
            description="Read one current-identity market snapshot.",
            input_model=MarketSnapshotInput,
            handler=opportunities.market_snapshot,
            layer="FACTOR_TREND",
            max_records=1,
            max_evidence=min(config.max_evidence_refs, 1),
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
        ),
        ToolSpec(
            name="sector.top",
            version="1.0",
            description="Read top current-identity sector factors.",
            input_model=SectorTopInput,
            handler=opportunities.sector_top,
            layer="FACTOR_TREND",
            max_records=20,
            max_evidence=min(config.max_evidence_refs, 20),
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
        ),
        ToolSpec(
            name="theme.top",
            version="1.0",
            description="Read top current-identity PIT theme factors.",
            input_model=ThemeTopInput,
            handler=opportunities.theme_top,
            layer="FACTOR_TREND",
            max_records=20,
            max_evidence=min(config.max_evidence_refs, 20),
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
        ),
        ToolSpec(
            name="opportunity.list",
            version="1.0",
            description="Read bounded same-day opportunities without forward returns.",
            input_model=OpportunityListInput,
            handler=opportunities.opportunity_list,
            layer="FACTOR_TREND",
            max_records=30,
            max_evidence=min(config.max_evidence_refs, 30),
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
        ),
        ToolSpec(
            name="backtest.summary",
            version="1.0",
            description="Read one persisted successful backtest summary.",
            input_model=BacktestSummaryInput,
            handler=research.backtest_summary,
            layer="STRATEGY_VALIDATION",
            max_records=1,
            max_evidence=min(config.max_evidence_refs, 1),
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
        ),
        ToolSpec(
            name="performance.summary",
            version="1.0",
            description="Read one unambiguous persisted M14 analytics bundle.",
            input_model=PerformanceSummaryInput,
            handler=research.performance_summary,
            layer="STRATEGY_VALIDATION",
            max_records=1,
            max_evidence=min(config.max_evidence_refs, 4),
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
        ),
        ToolSpec(
            name="walk_forward.summary",
            version="1.0",
            description="Read one persisted OOS walk-forward validation report.",
            input_model=WalkForwardSummaryInput,
            handler=research.walk_forward_summary,
            layer="STRATEGY_VALIDATION",
            max_records=1,
            max_evidence=min(config.max_evidence_refs, 1),
            max_warnings=config.max_warnings,
            timeout_seconds=config.default_timeout_seconds,
        ),
    ]
    if {spec.name for spec in specs} != DEFAULT_TOOL_NAMES:
        raise RuntimeError("default agent registry does not match the published tool allowlist")
    return AgentToolRegistry(
        specs,
        max_timeout_seconds=config.max_tool_timeout_seconds,
    )
