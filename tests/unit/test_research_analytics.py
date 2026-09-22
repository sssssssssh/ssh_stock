from datetime import date
from types import SimpleNamespace

import pytest
from app.core.config import get_settings
from app.models.market_data import OpportunityForwardEval, ThemeForwardEval
from app.services.analysis_identity import RESEARCH_EVAL_VERSION, RESEARCH_VERSION
from app.services.calc_metadata import config_hash
from app.services.research.analytics import (
    Cohort,
    _quantile,
    grouped_stats,
    research_status,
    topn_stats,
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
