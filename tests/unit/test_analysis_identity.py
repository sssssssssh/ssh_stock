from app.services.analysis_identity import analysis_strategy_config, analysis_strategy_hash


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
