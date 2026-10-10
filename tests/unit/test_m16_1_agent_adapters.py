from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.core.config import get_settings
from app.domain.agent.contracts import (
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
from app.models.market_data import MarketDaily
from app.models.performance import PortfolioPerformanceReport
from app.models.portfolio import PortfolioBacktestRun
from app.models.walk_forward import PortfolioWalkForwardStudy
from app.services.agent.adapters.market_data import MarketDataAgentAdapter
from app.services.agent.adapters.research import ResearchAgentAdapter
from app.services.performance.period_identity import period_identity_hash
from app.services.performance.risk_identity import risk_source_hash


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(
        self,
        *,
        scalar_values=(),
        scalars_values=(),
        execute_rows=(),
        get_values=None,
    ):
        self.scalar_values = list(scalar_values)
        self.scalars_values = list(scalars_values)
        self.execute_rows = list(execute_rows)
        self.get_values = get_values or {}
        self.commit_called = False

    def scalar(self, statement):
        return self.scalar_values.pop(0)

    def execute(self, statement):
        return _Rows(self.execute_rows)

    def scalars(self, statement):
        return _Rows(self.scalars_values.pop(0))

    def get(self, model, identity):
        return self.get_values.get(model)

    def commit(self):
        self.commit_called = True
        raise AssertionError("read adapter must not commit")


def test_historical_identity_mismatch_is_not_silently_read() -> None:
    db = _FakeDb(scalar_values=[0, 1])
    adapter = MarketDataAgentAdapter(db, get_settings())
    with pytest.raises(AgentError) as caught:
        adapter._derived_date(
            MarketDaily,
            date(2026, 1, 2),
            (MarketDaily.calc_version == "market_v1",),
        )
    assert caught.value.code == "SOURCE_IDENTITY_MISMATCH"
    assert not db.commit_called


def test_l1_and_l2_empty_or_not_ready_semantics() -> None:
    target = date(2026, 1, 2)

    coverage = MarketDataAgentAdapter(
        _FakeDb(scalars_values=[[], [], []], scalar_values=[None]), get_settings()
    ).data_coverage(DataCoverageInput(start_date=target, end_date=target))
    assert coverage.status == "DATA_INCOMPLETE"
    assert coverage.readiness.ready is False

    market_db = _FakeDb(scalar_values=[None])
    with pytest.raises(AgentError) as market_error:
        MarketDataAgentAdapter(market_db, get_settings()).market_snapshot(MarketSnapshotInput())
    assert market_error.value.code == "NOT_READY"

    for method_name, request in (
        ("sector_top", SectorTopInput(trade_date=target)),
        ("theme_top", ThemeTopInput(trade_date=target)),
        ("opportunity_list", OpportunityListInput(trade_date=target)),
    ):
        db = _FakeDb(execute_rows=[])
        adapter = MarketDataAgentAdapter(db, get_settings())
        adapter._derived_date = lambda *args, **kwargs: target
        result = getattr(adapter, method_name)(request)
        assert result.status == "EMPTY_RESULT"
        assert result.readiness.ready is True
        assert not db.commit_called


@pytest.mark.parametrize("dataset_count", [33, 100])
def test_data_coverage_rejects_more_than_the_nested_dataset_limit(
    dataset_count: int,
) -> None:
    target = date(2026, 1, 2)
    db = _FakeDb(
        scalars_values=[
            [target],
            [f"dataset_{index:02d}" for index in range(dataset_count)],
        ]
    )
    with pytest.raises(AgentError) as caught:
        MarketDataAgentAdapter(db, get_settings()).data_coverage(
            DataCoverageInput(start_date=target, end_date=target)
        )
    assert caught.value.code == "RESOURCE_LIMIT_EXCEEDED"
    assert not db.commit_called


def test_l3_missing_or_unready_sources_are_explicit() -> None:
    missing = ResearchAgentAdapter(_FakeDb())
    with pytest.raises(AgentError) as backtest_error:
        missing.backtest_summary(
            BacktestSummaryInput(run_id="11111111-1111-1111-1111-111111111111")
        )
    assert backtest_error.value.code == "NOT_FOUND"

    with pytest.raises(AgentError) as performance_error:
        missing.performance_summary(
            PerformanceSummaryInput(report_id="22222222-2222-2222-2222-222222222222")
        )
    assert performance_error.value.code == "NOT_FOUND"

    study = SimpleNamespace(id=UUID("33333333-3333-3333-3333-333333333333"))
    walk_db = _FakeDb(scalar_values=[None], get_values={PortfolioWalkForwardStudy: study})
    with pytest.raises(AgentError) as walk_error:
        ResearchAgentAdapter(walk_db).walk_forward_summary(
            WalkForwardSummaryInput(
                study_id=study.id,
                validation_id="44444444-4444-4444-4444-444444444444",
            )
        )
    assert walk_error.value.code == "NOT_READY"


def test_theme_top_exposes_persisted_pit_snapshot_and_degradation() -> None:
    calculated_at = datetime(2026, 1, 3, tzinfo=UTC)
    factor = SimpleNamespace(
        theme_code="885001.TI",
        heat_score=88.5,
        heat_rank=1,
        heat_momentum1=2.5,
        heat_momentum3=5.5,
        rank_change=3,
        lifecycle="MAIN_UP",
        source_coverage=0.8,
        data_coverage=0.9,
        member_snapshot_date=date(2025, 12, 31),
        calc_version="theme_v1",
        config_hash="a" * 64,
        calculated_at=calculated_at,
    )
    theme = SimpleNamespace(name="测试题材")
    db = _FakeDb(execute_rows=[(factor, theme)])
    adapter = MarketDataAgentAdapter(db, get_settings())
    adapter._derived_date = lambda *args, **kwargs: date(2026, 1, 2)
    result = adapter.theme_top(ThemeTopInput(trade_date=date(2026, 1, 2), limit=1))
    assert result.status == "SOURCE_DEGRADED"
    assert result.records[0]["member_snapshot_date"] == date(2025, 12, 31)
    assert result.records[0]["quality_warnings"] == ["SOURCE_DEGRADED"]
    assert result.evidence[0].trade_date == date(2026, 1, 2)
    assert "member_snapshot_date=2025-12-31" in result.evidence[0].limitations
    assert result.evidence[0].evidence_version == "v2"
    assert result.evidence[0].content_hash
    assert not db.commit_called


def test_l1_and_l2_handlers_return_bounded_dto_results_without_writes() -> None:
    target = date(2026, 1, 2)
    checked_at = datetime(2026, 1, 3, tzinfo=UTC)
    quality = SimpleNamespace(
        dataset="stock_daily",
        expected_rows=10,
        actual_rows=10,
        status="PASS",
        trade_date=target,
        checked_at=checked_at,
    )
    coverage_db = _FakeDb(
        scalars_values=[[target], ["stock_daily"], [quality]],
        scalar_values=[target],
    )
    coverage = MarketDataAgentAdapter(coverage_db, get_settings()).data_coverage(
        DataCoverageInput(start_date=target, end_date=target)
    )
    assert coverage.status == "READY"
    assert coverage.records[0]["quality_status"] == "PASS"
    assert coverage.records[0]["dataset_coverage"][0]["coverage_rate"] == 1
    assert coverage.evidence[0].evidence_version == "v2"
    assert coverage.evidence[0].content_hash

    market_row = SimpleNamespace(
        regime="RISK_ON",
        market_score=80.5,
        breadth20=0.7,
        breadth60=0.6,
        up_count=3000,
        down_count=1200,
        up_rate=0.7,
        total_amount=1_000_000.5,
        amount_ratio20=1.1,
        liquidity_score=75.0,
        calc_version="market_v1",
        config_hash="a" * 64,
        calculated_at=checked_at,
    )
    market_db = _FakeDb(scalar_values=[target, market_row])
    market = MarketDataAgentAdapter(market_db, get_settings()).market_snapshot(
        MarketSnapshotInput()
    )
    assert market.status == "READY"
    assert market.records[0]["regime"] == "RISK_ON"
    assert market.evidence[0].entity_id == "market"
    assert market.evidence[0].content_hash

    sector_factor = SimpleNamespace(
        sector_id=1,
        heat_score=90.0,
        heat_rank=1,
        heat_momentum1=2.0,
        heat_momentum3=4.0,
        rank_change=1,
        lifecycle="MAIN_UP",
        member_count=20,
        calc_version="sector_v1",
        config_hash="a" * 64,
        calculated_at=checked_at,
    )
    sector = SimpleNamespace(source_code="801010.SI", name="行业")
    sector_db = _FakeDb(execute_rows=[(sector_factor, sector)])
    sector_adapter = MarketDataAgentAdapter(sector_db, get_settings())
    sector_adapter._derived_date = lambda *args, **kwargs: target
    sector_result = sector_adapter.sector_top(SectorTopInput(limit=1))
    assert sector_result.records[0]["sector_name"] == "行业"
    assert len(sector_result.evidence) == 1
    assert sector_result.evidence[0].content_hash

    opportunity = SimpleNamespace(
        ts_code="000001.SZ",
        state="S4",
        opportunity_stage="TREND",
        opportunity_score=88.0,
        left_reversal_score=20.0,
        right_side_score=70.0,
        trend_score=90.0,
        reason_codes=["TREND_OK"],
        algo_version="v1.0",
        calc_version="opportunity_v1",
        config_hash="b" * 64,
        source_strategy_config_hash="a" * 64,
        calculated_at=checked_at,
    )
    opportunity_db = _FakeDb(execute_rows=[(opportunity, "平安银行")])
    opportunity_adapter = MarketDataAgentAdapter(opportunity_db, get_settings())
    opportunity_adapter._derived_date = lambda *args, **kwargs: target
    opportunity_result = opportunity_adapter.opportunity_list(
        OpportunityListInput(stage="TREND", limit=1)
    )
    assert opportunity_result.records[0]["ts_code"] == "000001.SZ"
    assert "ret5" not in opportunity_result.records[0]
    assert opportunity_result.evidence[0].content_hash
    assert all(not db.commit_called for db in (coverage_db, market_db, sector_db, opportunity_db))


def test_l3_handlers_use_exact_persisted_report_identity() -> None:
    run_id = UUID("11111111-1111-1111-1111-111111111111")
    performance_id = UUID("22222222-2222-2222-2222-222222222222")
    risk_id = UUID("33333333-3333-3333-3333-333333333333")
    trade_id = UUID("44444444-4444-4444-4444-444444444444")
    period_id = UUID("55555555-5555-5555-5555-555555555555")
    study_id = UUID("66666666-6666-6666-6666-666666666666")
    validation_id = UUID("77777777-7777-7777-7777-777777777777")
    target = date(2026, 1, 30)
    observed = datetime(2026, 2, 1, tzinfo=UTC)
    run = SimpleNamespace(
        id=run_id,
        account_mode="BACKTEST",
        status="SUCCESS",
        start_date=date(2026, 1, 2),
        end_date=target,
        initial_cash=Decimal("1000000"),
        result_summary={},
        finished_at=observed,
        algo_version="v1.0",
        source_strategy_config_hash="a" * 64,
        opportunity_calc_version="opportunity_v1",
        opportunity_config_hash="b" * 64,
        portfolio_version="portfolio_v3",
        portfolio_config_hash="c" * 64,
        execution_version="execution_v3",
        execution_config_hash="d" * 64,
        accounting_version="accounting_v3",
        accounting_config_hash="e" * 64,
        backtest_engine_version="backtest_v7",
    )
    nav = SimpleNamespace(
        trade_date=target,
        nav=Decimal("1.05"),
        total_assets=Decimal("1050000"),
    )
    backtest_db = _FakeDb(scalar_values=[nav], get_values={PortfolioBacktestRun: run})
    backtest = ResearchAgentAdapter(backtest_db).backtest_summary(
        BacktestSummaryInput(run_id=run_id)
    )
    assert backtest.records[0]["latest_nav"] == Decimal("1.05")
    assert backtest.evidence[0].calc_run_id == str(run_id)
    assert backtest.evidence[0].content_hash

    performance = SimpleNamespace(
        id=performance_id,
        run_id=run_id,
        performance_version="performance_v1",
        performance_config_hash="f" * 64,
        source_hash="1" * 64,
        status="SUCCESS",
        start_date=date(2026, 1, 2),
        end_date=target,
        trade_days=20,
        final_nav=Decimal("1.05"),
        cumulative_return=Decimal("0.05"),
        annualized_return=Decimal("0.8"),
        max_drawdown=Decimal("-0.02"),
        warnings=[],
        calculated_at=observed,
    )
    risk_hash = risk_source_hash(
        performance_id=performance_id,
        performance_version="performance_v1",
        performance_config_hash="f" * 64,
        performance_source_hash="1" * 64,
        risk_version="risk_v1",
        risk_config_hash="2" * 64,
        benchmark_code="000300.SH",
        benchmark_hash="8" * 64,
    )
    risk = SimpleNamespace(
        id=risk_id,
        run_id=run_id,
        performance_id=performance_id,
        risk_version="risk_v1",
        risk_config_hash="2" * 64,
        benchmark_source_hash="8" * 64,
        risk_source_hash=risk_hash,
        status="SUCCESS",
        start_date=date(2026, 1, 2),
        end_date=target,
        trade_days=20,
        benchmark_code="000300.SH",
        benchmark_cumulative_return=Decimal("0.02"),
        excess_cumulative_return=Decimal("0.03"),
        sharpe_ratio=Decimal("1.2"),
        sortino_ratio=Decimal("1.5"),
        calmar_ratio=Decimal("2.0"),
        warnings=[],
        calculated_at=observed,
    )
    trade = SimpleNamespace(
        id=trade_id,
        run_id=run_id,
        performance_id=performance_id,
        trade_version="trade_v1",
        trade_config_hash="4" * 64,
        trade_source_hash="5" * 64,
        status="SUCCESS",
        start_date=date(2026, 1, 2),
        end_date=target,
        trade_days=20,
        total_turnover=Decimal("2.0"),
        total_execution_cost=Decimal("500"),
        closed_episode_count=8,
        open_episode_count=1,
        win_rate=Decimal("0.625"),
        profit_factor=Decimal("1.8"),
        warnings=[],
        calculated_at=observed,
    )
    period_hash = period_identity_hash(
        run_id=run_id,
        performance_id=performance_id,
        performance_version="performance_v1",
        performance_config_hash="f" * 64,
        performance_source_hash="1" * 64,
        risk_id=risk_id,
        risk_version="risk_v1",
        risk_config_hash="2" * 64,
        risk_source_hash=risk_hash,
        benchmark_source_hash="8" * 64,
        trade_id=trade_id,
        trade_version="trade_v1",
        trade_config_hash="4" * 64,
        trade_source_hash="5" * 64,
        period_version="period_v1",
        period_config_hash="6" * 64,
    )
    period = SimpleNamespace(
        id=period_id,
        run_id=run_id,
        performance_id=performance_id,
        risk_id=risk_id,
        trade_id=trade_id,
        period_version="period_v1",
        period_config_hash="6" * 64,
        period_source_hash=period_hash,
        status="SUCCESS",
        start_date=date(2026, 1, 2),
        end_date=target,
        trade_days=20,
        month_count=1,
        year_count=1,
        warnings=[],
        calculated_at=observed,
    )
    performance_db = _FakeDb(
        scalars_values=[[risk], [trade], [period]],
        get_values={PortfolioPerformanceReport: performance, PortfolioBacktestRun: run},
    )
    performance_result = ResearchAgentAdapter(performance_db).performance_summary(
        PerformanceSummaryInput(report_id=performance_id)
    )
    assert performance_result.identity["performance_id"] == performance_id
    assert performance_result.identity["period_id"] == period_id
    assert len(performance_result.evidence) == 4
    assert all(item.evidence_version == "v2" for item in performance_result.evidence)
    assert all(item.calc_run_id == str(run_id) for item in performance_result.evidence)
    assert all(item.content_hash for item in performance_result.evidence)

    missing_period_db = _FakeDb(
        scalars_values=[[risk], [trade], []],
        get_values={PortfolioPerformanceReport: performance, PortfolioBacktestRun: run},
    )
    missing_period = ResearchAgentAdapter(missing_period_db).performance_summary(
        PerformanceSummaryInput(report_id=performance_id)
    )
    assert missing_period.status == "READY"
    assert "DATA_UNAVAILABLE:period_report" in missing_period.warnings

    risk.run_id = UUID("99999999-9999-9999-9999-999999999999")
    cross_run_db = _FakeDb(
        scalars_values=[[risk], [trade], [period]],
        get_values={PortfolioPerformanceReport: performance, PortfolioBacktestRun: run},
    )
    with pytest.raises(AgentError) as cross_run:
        ResearchAgentAdapter(cross_run_db).performance_summary(
            PerformanceSummaryInput(report_id=performance_id)
        )
    assert cross_run.value.code == "SOURCE_IDENTITY_MISMATCH"
    risk.run_id = run_id

    risk.status = "FAILED"
    failed_risk_db = _FakeDb(
        scalars_values=[[risk]],
        get_values={PortfolioPerformanceReport: performance, PortfolioBacktestRun: run},
    )
    with pytest.raises(AgentError) as failed_risk:
        ResearchAgentAdapter(failed_risk_db).performance_summary(
            PerformanceSummaryInput(report_id=performance_id)
        )
    assert failed_risk.value.code == "NOT_READY"
    risk.status = "SUCCESS"

    duplicate_period_db = _FakeDb(
        scalars_values=[[risk], [trade], [period, period]],
        get_values={PortfolioPerformanceReport: performance, PortfolioBacktestRun: run},
    )
    with pytest.raises(AgentError) as duplicate_period:
        ResearchAgentAdapter(duplicate_period_db).performance_summary(
            PerformanceSummaryInput(report_id=performance_id)
        )
    assert duplicate_period.value.code == "SOURCE_IDENTITY_MISMATCH"

    period.status = "FAILED"
    failed_period_db = _FakeDb(
        scalars_values=[[risk], [trade], [period]],
        get_values={PortfolioPerformanceReport: performance, PortfolioBacktestRun: run},
    )
    with pytest.raises(AgentError) as failed_period:
        ResearchAgentAdapter(failed_period_db).performance_summary(
            PerformanceSummaryInput(report_id=performance_id)
        )
    assert failed_period.value.code == "NOT_READY"
    period.status = "SUCCESS"

    duplicate_performance_db = _FakeDb(scalars_values=[[performance, performance]])
    with pytest.raises(AgentError) as duplicate_performance:
        ResearchAgentAdapter(duplicate_performance_db).performance_summary(
            PerformanceSummaryInput(run_id=run_id)
        )
    assert duplicate_performance.value.code == "INVALID_ARGUMENT"

    study = SimpleNamespace(
        id=study_id,
        requested_end_date=target,
        definition_hash="8" * 64,
    )
    validation = SimpleNamespace(
        id=validation_id,
        study_id=study_id,
        status="SUCCESS",
        walk_forward_version="walk_forward_v1",
        walk_forward_config_hash="9" * 64,
        policy_identity_version="policy_v1",
        validation_policy_hash="a" * 64,
        source_hash="b" * 64,
        window_count=3,
        total_oos_trade_days=60,
        positive_oos_window_count=2,
        positive_oos_window_rate=Decimal("0.666666"),
        stitched_oos_final_nav=Decimal("1.08"),
        stitched_oos_cumulative_return=Decimal("0.08"),
        stitched_oos_annualized_return=Decimal("0.35"),
        stitched_oos_max_drawdown=Decimal("-0.04"),
        stitched_excess_cumulative_return=Decimal("0.03"),
        unique_selected_parameter_hash_count=2,
        dominant_parameter_hash="c" * 64,
        dominant_parameter_hash_rate=Decimal("0.666666"),
        transition_count=2,
        switch_count=1,
        switch_rate=Decimal("0.5"),
        mean_return_degradation=Decimal("-0.10"),
        median_return_degradation=Decimal("-0.08"),
        mean_drawdown_worsening=Decimal("0.02"),
        median_drawdown_worsening=Decimal("0.01"),
        warnings=[],
        calculated_at=observed,
    )
    walk_db = _FakeDb(scalar_values=[validation], get_values={PortfolioWalkForwardStudy: study})
    walk = ResearchAgentAdapter(walk_db).walk_forward_summary(
        WalkForwardSummaryInput(study_id=study_id, validation_id=validation_id)
    )
    assert walk.identity["validation_id"] == validation_id
    assert walk.records[0]["oos_sample"]["total_oos_trade_days"] == 60
    assert walk.records[0]["result_stage"] == "OOS"
    assert walk.evidence[0].evidence_version == "v2"
    assert walk.evidence[0].content_hash
    assert all(not db.commit_called for db in (backtest_db, performance_db, walk_db))
