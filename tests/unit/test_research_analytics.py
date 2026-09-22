from datetime import date
from types import SimpleNamespace

import pytest
from app.core.config import get_settings
from app.models.market_data import (
    OpportunityForwardEval,
    ResearchTransitionEval,
    ThemeForwardEval,
)
from app.services.analysis_identity import RESEARCH_EVAL_VERSION, RESEARCH_VERSION
from app.services.calc_metadata import config_hash
from app.services.research.analytics import (
    Cohort,
    _quantile,
    bucket_stats,
    context_stats,
    grouped_stats,
    research_status,
    topn_stats,
    transition_stats,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_horizon_stats_separate_event_mature_execution_and_return_denominators() -> None:
    rows = [
        {
            "mature20": True,
            "entry_executable": True,
            "exit_executable20": True,
            "ret20": 0.10,
            "benchmark_ret20": 0.04,
            "excess_ret20": 0.06,
            "mfe20": 0.20,
            "mae20": -0.05,
        },
        {
            "mature20": True,
            "entry_executable": True,
            "exit_executable20": True,
            "ret20": -0.02,
            "benchmark_ret20": None,
            "excess_ret20": None,
            "mfe20": 0.10,
            "mae20": -0.10,
        },
        {"mature20": True, "entry_executable": False, "exit_executable20": True, "ret20": None},
        {"mature20": False, "entry_executable": True, "exit_executable20": None, "ret20": None},
    ]
    cohort = Cohort(min_sample_warning=3)
    for row in rows:
        cohort.add(row)
    result = cohort.horizon_result(20)
    assert result["event_count"] == 4
    assert result["mature_count"] == 3
    assert result["entry_executable_count"] == 2
    assert result["return_sample_count"] == 2
    assert result["excess_sample_count"] == 1
    assert result["avg_return"] == pytest.approx(0.04)
    assert result["avg_excess_return"] == pytest.approx(0.06)
    assert result["win_rate"] == 0.5
    assert result["avg_mfe20"] == pytest.approx(0.15)
    assert result["sample_warning"] is True


def test_context_null_is_unknown_and_quantile_single_value_is_preserved() -> None:
    rows = [
        {
            "market_regime": None,
            "mature5": True,
            "entry_executable": True,
            "exit_executable5": True,
            "ret5": 0.12,
        }
    ]
    result = grouped_stats(rows, "market_regime", 1)
    assert result[0]["group"] == "UNKNOWN"
    assert result[0]["horizons"][0]["p25_return"] == pytest.approx(0.12)
    assert _quantile([0.12], 0.75) == pytest.approx(0.12)
    assert grouped_stats([], None, 30, all_groups=["ALL"]) == []


def test_topn_ties_are_stable_by_code_for_stock_and_theme() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    OpportunityForwardEval.__table__.create(engine)
    ThemeForwardEval.__table__.create(engine)
    settings = get_settings().model_copy(deep=True)
    settings.research_config["trend_topn"] = [1]
    settings.research_config["theme_topn"] = [1]
    research_hash = config_hash(settings.research_config)
    opportunity_hash = config_hash(settings.opportunity_config)
    day = date(2026, 1, 5)
    common = {
        "trade_date": day,
        "opportunity_config_hash": opportunity_hash,
        "strategy_config_hash": config_hash(settings.strategy),
        "research_version": RESEARCH_VERSION,
        "research_config_hash": research_hash,
        "eval_version": RESEARCH_EVAL_VERSION,
        "benchmark_code": "000300.SH",
        "entry_executable": True,
        "mature5": True,
        "mature10": False,
        "mature20": False,
        "mature60": False,
        "exit_executable5": True,
    }
    with Session(engine) as db:
        for index, code in enumerate(("A.SZ", "B.SZ"), start=1):
            db.add(
                OpportunityForwardEval(
                    id=index,
                    ts_code=code,
                    algo_version=settings.algo_version,
                    opportunity_calc_version="opportunity_v1",
                    entry_basis="NEXT_OPEN",
                    state="S4",
                    opportunity_stage="TREND",
                    trend_rank_score=80,
                    ret5=0.1 if index == 1 else -0.1,
                    **common,
                )
            )
            db.add(
                ThemeForwardEval(
                    id=index,
                    theme_code=f"{code}.TI",
                    theme_calc_version="theme_v1",
                    entry_basis="NEXT_CLOSE",
                    heat_rank=1,
                    ret5=0.1 if index == 1 else -0.1,
                    **common,
                )
            )
        db.commit()
        stock = topn_stats(db, settings, day, day, theme=False)
        theme = topn_stats(db, settings, day, day, theme=True)
    assert stock[0]["group"] == "TOP1"
    assert stock[0]["horizons"][0]["avg_return"] == pytest.approx(0.1)
    assert theme[0]["group"] == "TOP1"
    assert theme[0]["horizons"][0]["avg_return"] == pytest.approx(0.1)


def test_status_uses_theme_evaluation_date_when_stock_eval_is_empty() -> None:
    class Db:
        def execute(self, statement):
            return SimpleNamespace(one=lambda: (0, None))

        def scalar(self, statement):
            sql = str(statement)
            if "max(theme_forward_eval.evaluated_until_date)" in sql:
                return date(2026, 9, 18)
            return 0 if "count(" in sql else None

    result = research_status(Db(), get_settings())
    assert result["latest_evaluated_market_date"] == date(2026, 9, 18)


def test_strategy_identity_and_context_event_universes_do_not_mix() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    OpportunityForwardEval.__table__.create(engine)
    ResearchTransitionEval.__table__.create(engine)
    settings = get_settings()
    day = date(2026, 1, 5)
    strategy_hash = config_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    research_hash = config_hash(settings.research_config)
    common = {
        "trade_date": day,
        "algo_version": settings.algo_version,
        "opportunity_calc_version": "opportunity_v1",
        "opportunity_config_hash": opportunity_hash,
        "research_version": RESEARCH_VERSION,
        "research_config_hash": research_hash,
        "eval_version": RESEARCH_EVAL_VERSION,
        "entry_basis": "NEXT_OPEN",
        "benchmark_code": "000300.SH",
        "mature5": True,
        "entry_executable": True,
        "exit_executable5": True,
        "ret5": 0.1,
    }
    samples = (
        ("LEFT.SZ", "S2", "LEFT_REVERSAL", "LEFT_ONLY", strategy_hash),
        ("RIGHT.SZ", "S3", "RIGHT_SIDE_NEW", "RIGHT_ONLY", strategy_hash),
        ("TREND.SZ", "S4", "TREND", "TREND_ONLY", strategy_hash),
        ("POSITION.SZ", "S5", "STRONG_TREND", "POSITION_ONLY", strategy_hash),
        ("LEFT.SZ", "S2", "LEFT_REVERSAL", "OLD_STRATEGY", "old-strategy-hash"),
    )
    with Session(engine) as db:
        for index, (code, state, stage, regime, source_hash) in enumerate(samples, start=1):
            db.add(OpportunityForwardEval(
                id=index, ts_code=code, state=state, opportunity_stage=stage,
                market_regime=regime, strategy_config_hash=source_hash, **common,
            ))
        for index, (code, kind, key, state) in enumerate((
            ("LEFT.SZ", "LEFT_THRESHOLD_CROSS", "LEFT_75", "S2"),
            ("RIGHT.SZ", "RIGHT_SIDE_NEW", "RIGHT_SIDE_NEW", "S3"),
        ), start=1):
            db.add(ResearchTransitionEval(
                id=index, event_trade_date=day, ts_code=code, event_type=kind, event_key=key,
                source_state=state, algo_version=settings.algo_version,
                trend_calc_version="trend_v1", opportunity_calc_version="opportunity_v1",
                strategy_config_hash=strategy_hash,
                opportunity_config_hash=opportunity_hash, research_version=RESEARCH_VERSION,
                research_config_hash=research_hash,
            ))
        db.commit()
        assert context_stats(db, settings, day, day, "market_regime", "LEFT")[0][
            "group"
        ] == "LEFT_ONLY"
        assert context_stats(db, settings, day, day, "market_regime", "RIGHT")[0][
            "group"
        ] == "RIGHT_ONLY"
        assert {row["group"] for row in context_stats(
            db, settings, day, day, "market_regime", "TREND"
        )} == {"TREND_ONLY", "POSITION_ONLY"}
        assert {row["group"] for row in context_stats(
            db, settings, day, day, "market_regime", "POSITION"
        )} == {"TREND_ONLY", "POSITION_ONLY"}
        assert sum(row["event_count"] for row in context_stats(
            db, settings, day, day, "market_regime", "ALL"
        )) == 4
        assert next(row for row in transition_stats(
            db, settings, day, day, left=True
        ) if row["group"] == "LEFT_75")["event_count"] == 1


def test_transition_calc_versions_coexist_but_only_current_version_is_read() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    OpportunityForwardEval.__table__.create(engine)
    ResearchTransitionEval.__table__.create(engine)
    settings = get_settings()
    day = date(2026, 1, 5)
    identity = {
        "algo_version": settings.algo_version,
        "strategy_config_hash": config_hash(settings.strategy),
        "opportunity_config_hash": config_hash(settings.opportunity_config),
        "research_version": RESEARCH_VERSION,
        "research_config_hash": config_hash(settings.research_config),
    }
    with Session(engine) as db:
        db.add(OpportunityForwardEval(
            id=1, trade_date=day, ts_code="A.SZ", opportunity_calc_version="opportunity_v1",
            eval_version=RESEARCH_EVAL_VERSION, entry_basis="NEXT_OPEN",
            benchmark_code="000300.SH", state="S2", opportunity_stage="LEFT_REVERSAL",
            mature5=True, entry_executable=True, exit_executable5=True, ret5=0.1,
            **identity,
        ))
        for index, (trend, opportunity) in enumerate((
            ("trend_v1", "opportunity_v1"),
            ("trend_v2", "opportunity_v1"),
            ("trend_v1", "opportunity_v2"),
        ), start=1):
            db.add(ResearchTransitionEval(
                id=index, event_trade_date=day, ts_code="A.SZ",
                event_type="LEFT_THRESHOLD_CROSS", event_key="LEFT_75", source_state="S2",
                trend_calc_version=trend, opportunity_calc_version=opportunity, **identity,
            ))
        db.commit()
        assert db.query(ResearchTransitionEval).count() == 3
        results = transition_stats(db, settings, day, day, left=True)
    assert next(row for row in results if row["group"] == "LEFT_75")["event_count"] == 1


def test_bucket_numeric_order_bounded_100_and_negative_momentum() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    OpportunityForwardEval.__table__.create(engine)
    ThemeForwardEval.__table__.create(engine)
    settings = get_settings()
    day = date(2026, 1, 5)
    common = {
        "trade_date": day,
        "strategy_config_hash": config_hash(settings.strategy),
        "opportunity_config_hash": config_hash(settings.opportunity_config),
        "research_version": RESEARCH_VERSION,
        "research_config_hash": config_hash(settings.research_config),
        "eval_version": RESEARCH_EVAL_VERSION,
        "benchmark_code": "000300.SH",
    }
    with Session(engine) as db:
        for index, score in enumerate((0, 9.9, 10, 99.9, 100, None)):
            db.add(OpportunityForwardEval(
                id=index + 1, ts_code=f"{index}.SZ", algo_version=settings.algo_version,
                opportunity_calc_version="opportunity_v1", entry_basis="NEXT_OPEN",
                state="S4" if index < 5 else "S2", opportunity_stage="TREND",
                trend_rank_score=score, **common,
            ))
        for index, score in enumerate((-15, -5, 5)):
            db.add(ThemeForwardEval(
                id=index + 1, theme_code=f"{index}.TI", theme_calc_version="theme_v1",
                entry_basis="NEXT_CLOSE", heat_momentum3=score, **common,
            ))
        db.commit()
        buckets = bucket_stats(
            db, settings, day, day, model=OpportunityForwardEval,
            field="trend_rank_score", research_type="TREND",
        )
        assert [row["group"] for row in buckets] == [
            "0-10", "10-20", "90-100"
        ]
        assert [row["event_count"] for row in buckets] == [2, 1, 2]
        assert [row["group"] for row in bucket_stats(
            db, settings, day, day, model=OpportunityForwardEval, field="trend_rank_score"
        )] == ["0-10", "10-20", "90-100", "UNKNOWN"]
        assert [row["group"] for row in bucket_stats(
            db, settings, day, day, model=ThemeForwardEval, field="heat_momentum3"
        )] == ["-20--10", "-10-0", "0-10"]
