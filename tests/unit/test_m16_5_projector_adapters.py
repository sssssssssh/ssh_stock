from app.domain.agent.contracts import AgentToolResult
from app.domain.agent.policy import serialized_result
from app.models import (
    PortfolioPerformancePeriodReport,
    PortfolioPerformanceReport,
    PortfolioPerformanceRiskReport,
    PortfolioPerformanceTradeReport,
)
from app.services.agent.archive.canonical import archive_hash
from app.services.agent.archive.projectors import validate_projection
from test_m16_1_agent_adapters import _FakeDb
from test_m16_1_agent_adapters import (
    test_l1_and_l2_handlers_return_bounded_dto_results_without_writes as exercise_market,
)
from test_m16_1_agent_adapters import (
    test_l3_handlers_use_exact_persisted_report_identity as exercise_research,
)
from test_m16_1_agent_adapters import (
    test_theme_top_exposes_persisted_pit_snapshot_and_degradation as exercise_theme,
)


def assert_actual_projectors(result):
    payload = serialized_result(result, max_output_bytes=65536)
    for ref, raw_ref in zip(result.evidence, payload["evidence"], strict=True):
        path = validate_projection(payload, raw_ref, ref._archive_projection)
        assert path.startswith("records.")
        assert archive_hash(ref._archive_projection) == raw_ref["content_hash"]


def test_eight_actual_adapter_responses_not_approximate_record_fixtures(monkeypatch):
    original = AgentToolResult.__init__
    observed = set()
    db_original = _FakeDb.__init__

    def orm_artifact(value):
        for model, field in (
            (PortfolioPerformanceReport, "performance_version"),
            (PortfolioPerformanceRiskReport, "risk_version"),
            (PortfolioPerformanceTradeReport, "trade_version"),
            (PortfolioPerformancePeriodReport, "period_version"),
        ):
            if hasattr(value, field):
                return model(**vars(value))
        return value

    def orm_db(self, **kwargs):
        if kwargs.get("get_values"):
            kwargs["get_values"] = {
                key: orm_artifact(value) for key, value in kwargs["get_values"].items()
            }
        if "scalars_values" in kwargs:
            kwargs["scalars_values"] = [
                [orm_artifact(item) for item in rows] for rows in kwargs["scalars_values"]
            ]
        db_original(self, **kwargs)

    def checked(self, **data):
        original(self, **data)
        if self.evidence:
            assert_actual_projectors(self)
            observed.add(self.tool_name)

    monkeypatch.setattr(AgentToolResult, "__init__", checked)
    monkeypatch.setattr(_FakeDb, "__init__", orm_db)
    exercise_market()
    exercise_theme()
    exercise_research()
    assert observed == {
        "data.coverage",
        "market.snapshot",
        "sector.top",
        "theme.top",
        "opportunity.list",
        "backtest.summary",
        "performance.summary",
        "walk_forward.summary",
    }
