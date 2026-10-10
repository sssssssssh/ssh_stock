from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

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


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any], AgentToolResult]
    layer: str
    max_records: int
    timeout_seconds: int

    def catalog_entry(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "layer": self.layer,
            "max_records": self.max_records,
            "timeout_seconds": self.timeout_seconds,
            "input_schema": self.input_model.model_json_schema(),
        }


class AgentToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        if len(specs) != 8 or len({spec.name for spec in specs}) != 8:
            raise ValueError("M16.1 registry must contain exactly eight unique tools")
        self._specs = {spec.name: spec for spec in specs}

    def get(self, name: str) -> ToolSpec:
        try:
            return self._specs[name]
        except KeyError as exc:
            raise AgentError("INVALID_TOOL", f"unknown tool: {name}", status_code=422) from exc

    def catalog(self) -> list[dict[str, Any]]:
        return [self._specs[name].catalog_entry() for name in sorted(self._specs)]

    def __len__(self) -> int:
        return len(self._specs)


def build_registry(
    market: MarketDataAgentAdapter,
    opportunities: OpportunityAgentAdapter,
    research: ResearchAgentAdapter,
    *,
    timeout_seconds: int,
) -> AgentToolRegistry:
    return AgentToolRegistry(
        [
            ToolSpec(
                "data.coverage",
                "1.0",
                "Summarize persisted data-quality coverage for a bounded date range.",
                DataCoverageInput,
                market.data_coverage,
                "DATA",
                32,
                timeout_seconds,
            ),
            ToolSpec(
                "market.snapshot",
                "1.0",
                "Read one current-identity market snapshot.",
                MarketSnapshotInput,
                opportunities.market_snapshot,
                "FACTOR_TREND",
                1,
                timeout_seconds,
            ),
            ToolSpec(
                "sector.top",
                "1.0",
                "Read top current-identity sector factors.",
                SectorTopInput,
                opportunities.sector_top,
                "FACTOR_TREND",
                20,
                timeout_seconds,
            ),
            ToolSpec(
                "theme.top",
                "1.0",
                "Read top current-identity PIT theme factors.",
                ThemeTopInput,
                opportunities.theme_top,
                "FACTOR_TREND",
                20,
                timeout_seconds,
            ),
            ToolSpec(
                "opportunity.list",
                "1.0",
                "Read bounded same-day opportunities without forward returns.",
                OpportunityListInput,
                opportunities.opportunity_list,
                "FACTOR_TREND",
                30,
                timeout_seconds,
            ),
            ToolSpec(
                "backtest.summary",
                "1.0",
                "Read one persisted successful backtest summary.",
                BacktestSummaryInput,
                research.backtest_summary,
                "STRATEGY_VALIDATION",
                1,
                timeout_seconds,
            ),
            ToolSpec(
                "performance.summary",
                "1.0",
                "Read one unambiguous persisted M14 analytics bundle.",
                PerformanceSummaryInput,
                research.performance_summary,
                "STRATEGY_VALIDATION",
                1,
                timeout_seconds,
            ),
            ToolSpec(
                "walk_forward.summary",
                "1.0",
                "Read one persisted OOS walk-forward validation report.",
                WalkForwardSummaryInput,
                research.walk_forward_summary,
                "STRATEGY_VALIDATION",
                1,
                timeout_seconds,
            ),
        ]
    )
