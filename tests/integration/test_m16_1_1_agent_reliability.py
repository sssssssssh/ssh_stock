from datetime import date
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from app.core.agent_db import get_agent_db
from app.core.config import get_settings
from app.domain.agent.contracts import (
    AgentToolResult,
    DataCoverageInput,
    MarketSnapshotInput,
    Readiness,
)
from app.domain.agent.errors import AgentError
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.application import AgentApplicationService
from app.services.agent.registry import AgentToolRegistry, ToolSpec
from sqlalchemy.exc import DBAPIError

_AUDITED_TABLES = (
    "job_run",
    "stock_daily",
    "stock_factor_daily",
    "stock_opportunity_daily",
    "portfolio_backtest_run",
    "portfolio_performance_report",
    "portfolio_walk_forward_validation_report",
)


def _counts(engine: sa.Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table: int(connection.scalar(sa.text(f"SELECT count(*) FROM {table}")) or 0)
            for table in _AUDITED_TABLES
        }


def test_agent_session_is_postgresql_read_only_and_adapter_changes_no_business_rows() -> None:
    settings = get_settings()
    engine = sa.create_engine(settings.database_url)
    before = _counts(engine)
    dependency = get_agent_db()
    db = next(dependency)
    try:
        assert db.scalar(sa.text("SHOW transaction_read_only")) == "on"
        result = MarketDataAgentAdapter(db, settings).data_coverage(
            request=DataCoverageInput(
                start_date=date(2099, 1, 1),
                end_date=date(2099, 1, 1),
            )
        )
        assert result.status == "DATA_INCOMPLETE"
        with pytest.raises(DBAPIError):
            db.execute(sa.text("UPDATE job_run SET status = status WHERE false"))
    finally:
        dependency.close()
    assert _counts(engine) == before
    engine.dispose()


def test_postgresql_statement_timeout_maps_to_safe_agent_error() -> None:
    settings = get_settings()
    original_timeout = settings.agent_config.statement_timeout_ms
    settings.agent_config.statement_timeout_ms = 50
    dependency = get_agent_db()
    db = next(dependency)
    try:
        def slow_query(_request: MarketSnapshotInput) -> AgentToolResult:
            db.execute(sa.text("SELECT pg_sleep(0.2)"))
            return AgentToolResult(
                tool_name="test.slow_query",
                status="READY",
                readiness=Readiness(ready=True, code="READY"),
            )

        registry = AgentToolRegistry(
            [
                ToolSpec(
                    name="test.slow_query",
                    version="1.0",
                    description="Exercise the PostgreSQL statement timeout.",
                    input_model=MarketSnapshotInput,
                    handler=slow_query,
                    layer="DATA",
                    max_records=1,
                    max_evidence=1,
                    max_warnings=1,
                    timeout_seconds=1,
                )
            ]
        )
        service = AgentApplicationService(db, settings, registry=registry)
        with pytest.raises(AgentError) as caught:
            service.execute(
                tool_name="test.slow_query",
                raw_input={},
                request_id="postgres-timeout",
                user=SimpleNamespace(username="test-admin"),
            )
        assert caught.value.code == "SQL_STATEMENT_TIMEOUT"
        assert caught.value.status_code == 504
        assert "pg_sleep" not in str(caught.value)
    finally:
        dependency.close()
        settings.agent_config.statement_timeout_ms = original_timeout
