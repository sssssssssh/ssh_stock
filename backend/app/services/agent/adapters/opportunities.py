from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.agent.contracts import (
    AgentToolResult,
    MarketSnapshotInput,
    OpportunityListInput,
    SectorTopInput,
    ThemeTopInput,
)
from app.services.agent.adapters.market_data import MarketDataAgentAdapter


class OpportunityAgentAdapter:
    """Expose only the approved L2 query surface to the tool registry."""

    def __init__(self, db: Session, settings: Settings) -> None:
        self._queries = MarketDataAgentAdapter(db, settings)

    def market_snapshot(self, request: MarketSnapshotInput) -> AgentToolResult:
        return self._queries.market_snapshot(request)

    def sector_top(self, request: SectorTopInput) -> AgentToolResult:
        return self._queries.sector_top(request)

    def theme_top(self, request: ThemeTopInput) -> AgentToolResult:
        return self._queries.theme_top(request)

    def opportunity_list(self, request: OpportunityListInput) -> AgentToolResult:
        return self._queries.opportunity_list(request)
