from types import SimpleNamespace

from app.models.market_data import StockOpportunityDaily, ThemeFactorDaily
from app.services.analysis_filters import (
    opportunity_identity_filters,
    theme_factor_identity_filters,
)
from app.services.analysis_identity import analysis_strategy_config, analysis_strategy_hash
from sqlalchemy import select
from sqlalchemy.dialects import postgresql


def test_analysis_hash_ignores_quality_and_provider_settings() -> None:
    base = {
        "universe": {"exclude_st": True},
        "benchmark": {"primary": "000300.SH"},
        "factor": {"rps_windows": [20, 60]},
        "trend": {"minimum_days": 3},
        "raw_quality": {"stock_daily": {"warning_coverage_rate": 0.98}},
        "provider": {"safe_limits": {"ths_member": 500}},
    }
    changed = {
        **base,
        "raw_quality": {"stock_daily": {"warning_coverage_rate": 0.99}},
        "provider": {"safe_limits": {"ths_member": 2000}},
    }

    assert analysis_strategy_hash(base) == analysis_strategy_hash(changed)
    assert "raw_quality" not in analysis_strategy_config(base)
    assert "provider" not in analysis_strategy_config(base)


def test_analysis_hash_changes_for_factor_or_trend_settings() -> None:
    base = {"factor": {"rps_windows": [20, 60]}, "trend": {"minimum_days": 3}}

    assert analysis_strategy_hash(base) != analysis_strategy_hash(
        {**base, "factor": {"rps_windows": [20, 120]}}
    )
    assert analysis_strategy_hash(base) != analysis_strategy_hash(
        {**base, "trend": {"minimum_days": 4}}
    )


def test_theme_and_opportunity_filters_include_strategy_lineage() -> None:
    settings = SimpleNamespace(
        algo_version="v1",
        strategy={"factor": {"rps_windows": [20, 60]}},
        opportunity_config={"theme": {"min_member_count": 5}},
    )
    theme_sql = str(
        select(ThemeFactorDaily).where(*theme_factor_identity_filters(settings)).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    opportunity_sql = str(
        select(StockOpportunityDaily)
        .where(*opportunity_identity_filters(settings))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "theme_factor_daily.source_strategy_config_hash" in theme_sql
    assert "stock_opportunity_daily.source_strategy_config_hash" in opportunity_sql
    assert "stock_opportunity_daily.algo_version = 'v1'" in opportunity_sql
