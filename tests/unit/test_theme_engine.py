from datetime import date, timedelta

import pandas as pd
from app.services.theme.engine import ThemeConfig, calculate_theme_factors


def test_theme_heat_renormalizes_missing_optional_component() -> None:
    start = date(2026, 8, 1)
    dates = [start + timedelta(days=index) for index in range(8)]
    daily = pd.DataFrame(
        [
            {
                "trade_date": current,
                "theme_code": code,
                "close": 100 + index * multiplier,
                "turnover_rate": 1,
            }
            for index, current in enumerate(dates)
            for code, multiplier in (("A", 2), ("B", 1))
        ]
    )
    config = ThemeConfig(
        benchmark_code="000300.SH",
        min_member_count=1,
        weights={"excess_return5": 0.5, "moneyflow_score": 0.5},
    )
    index_daily = pd.DataFrame(
        [{"trade_date": current, "ts_code": "000300.SH", "close": 100} for current in dates]
    )

    result = calculate_theme_factors(
        theme_daily=daily,
        members=pd.DataFrame(),
        factors=pd.DataFrame(),
        index_daily=index_daily,
        moneyflow=pd.DataFrame(),
        limits=pd.DataFrame(),
        membership_context_by_date={},
        moneyflow_pass_dates=set(),
        limit_pass_dates=set(),
        start=dates[-1],
        end=dates[-1],
        config=config,
    )

    assert set(result["data_coverage"]) == {0.5}
    assert result["moneyflow_score"].isna().all()
    assert result["heat_score"].notna().all()


def test_theme_heat_is_null_below_half_coverage() -> None:
    target = date(2026, 9, 1)
    config = ThemeConfig(
        benchmark_code="000300.SH",
        min_member_count=1,
        weights={"turnover_ratio20": 0.49, "moneyflow_score": 0.51},
    )
    daily = pd.DataFrame(
        [{"trade_date": target, "theme_code": "A", "close": 100, "turnover_rate": 1}]
    )

    result = calculate_theme_factors(
        daily,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        {},
        {},
        {},
        target,
        target,
        config,
    )

    assert result.iloc[0]["data_coverage"] == 0
    assert result.iloc[0]["heat_score"] is None


def test_theme_heat_uses_all_available_optional_sources() -> None:
    target = date(2026, 9, 1)
    daily = pd.DataFrame(
        [
            {"trade_date": target, "theme_code": "A", "close": 100, "turnover_rate": 1},
            {"trade_date": target, "theme_code": "B", "close": 100, "turnover_rate": 1},
        ]
    )
    moneyflow = pd.DataFrame(
        [
            {"trade_date": target, "theme_code": "A", "net_amount": 20, "company_num": 10},
            {"trade_date": target, "theme_code": "B", "net_amount": 10, "company_num": 10},
        ]
    )
    limits = pd.DataFrame(
        [
            {
                "trade_date": target,
                "theme_code": "A",
                "up_nums": 2,
                "cons_nums": 1,
                "days": 2,
                "hot_rank": 1,
            }
        ]
    )
    config = ThemeConfig(
        benchmark_code="000300.SH",
        min_member_count=1,
        weights={"moneyflow_score": 0.5, "limit_strength_score": 0.5},
    )

    result = calculate_theme_factors(
        daily,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        moneyflow,
        limits,
        {},
        {target},
        {target},
        target,
        target,
        config,
    ).set_index("theme_code")

    assert result["heat_score"].notna().all()
    assert set(result["data_coverage"]) == {1.0}
    assert result.loc["B", "limit_up_count"] == 0
    assert result.loc["B", "continuous_limit_count"] == 0


def test_theme_heat_degrades_when_limit_source_is_unavailable() -> None:
    target = date(2026, 9, 1)
    daily = pd.DataFrame(
        [
            {"trade_date": target, "theme_code": "A", "close": 100, "turnover_rate": 1},
            {"trade_date": target, "theme_code": "B", "close": 100, "turnover_rate": 1},
        ]
    )
    moneyflow = pd.DataFrame(
        [
            {"trade_date": target, "theme_code": "A", "net_amount": 20, "company_num": 10},
            {"trade_date": target, "theme_code": "B", "net_amount": 10, "company_num": 10},
        ]
    )
    config = ThemeConfig(
        benchmark_code="000300.SH",
        min_member_count=1,
        weights={"moneyflow_score": 0.5, "limit_strength_score": 0.5},
    )

    result = calculate_theme_factors(
        daily,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        moneyflow,
        pd.DataFrame(),
        {},
        {target},
        set(),
        target,
        target,
        config,
    )

    assert result["limit_strength_score"].isna().all()
    assert set(result["data_coverage"]) == {0.5}
    assert result["heat_score"].notna().all()


def test_theme_heat_degrades_when_member_snapshot_is_unavailable() -> None:
    start = date(2026, 8, 1)
    dates = [start + timedelta(days=index) for index in range(5)]
    daily = pd.DataFrame(
        [
            {
                "trade_date": current,
                "theme_code": code,
                "close": 100,
                "turnover_rate": index + multiplier,
            }
            for index, current in enumerate(dates)
            for code, multiplier in (("A", 1), ("B", 2))
        ]
    )
    config = ThemeConfig(
        benchmark_code="000300.SH",
        min_member_count=1,
        weights={"turnover_ratio20": 0.5, "breadth20": 0.5},
    )

    result = calculate_theme_factors(
        daily,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        {},
        set(),
        set(),
        dates[-1],
        dates[-1],
        config,
    )

    assert result["member_snapshot_date"].isna().all()
    assert result["breadth20"].isna().all()
    assert set(result["data_coverage"]) == {0.5}
    assert result["heat_score"].notna().all()


def test_partial_snapshot_keeps_missing_theme_member_metrics_null() -> None:
    target = date(2026, 9, 23)
    daily = pd.DataFrame([
        {"trade_date": target, "theme_code": code, "close": 100, "turnover_rate": 1}
        for code in ("A.TI", "B.TI")
    ])
    members = pd.DataFrame([
        {"trade_date": target, "theme_code": "A.TI", "ts_code": "000001.SZ"}
    ])
    factors = pd.DataFrame([{
        "trade_date": target,
        "ts_code": "000001.SZ",
        "eligible": True,
        "adj_close": 11,
        "ma20": 10,
        "ma60": 9,
        "return1": 0.01,
        "breakout20": True,
        "rps60": 80,
    }])
    result = calculate_theme_factors(
        daily,
        members,
        factors,
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        {
            target: {
                "source_snapshot_date": target,
                "mode": "SNAPSHOT",
                "available": True,
                "coverage": 1.0,
            }
        },
        set(),
        set(),
        target,
        target,
        ThemeConfig("000300.SH", 1, {"breadth20": 1.0}),
    ).set_index("theme_code")

    assert result.loc["A.TI", "member_count"] == 1
    assert result.loc["A.TI", "breadth20"] == 1
    assert result.loc["B.TI", "member_snapshot_date"] == target
    for column in (
        "member_count",
        "eligible_member_count",
        "breadth20",
        "breadth60",
        "up_rate",
        "new_high20_rate",
        "rps60_median",
    ):
        assert pd.isna(result.loc["B.TI", column])
