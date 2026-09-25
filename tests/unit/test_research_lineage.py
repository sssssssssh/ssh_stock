from datetime import date
from types import SimpleNamespace

import app.services.opportunity.service as opportunity_service_module
import app.services.research.opportunity_eval as opportunity_eval
import app.services.research.theme_eval as theme_eval
import app.services.research.transition_eval as transition_eval
import app.services.theme.service as theme_service_module
import pandas as pd
import pytest
from app.core.config import get_settings
from app.models.market_data import (
    StockOpportunityDaily,
    ThemeFactorDaily,
    ThemeForwardEval,
)
from app.services.analysis_identity import (
    RESEARCH_EVAL_VERSION,
    RESEARCH_VERSION,
    THEME_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session


class _Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _ResearchDb:
    def __init__(self, base=None):
        self.base = base
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        sql = str(statement)
        if self.base is not None and (
            "FROM stock_opportunity_daily" in sql or "FROM theme_factor_daily" in sql
        ):
            return _Rows([self.base])
        return _Rows()

    def scalar(self, statement):
        return None


def _sql(statement):
    return str(statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))


@pytest.mark.parametrize(
    ("module", "source_table"),
    (
        (opportunity_eval, "stock_opportunity_daily"),
        (theme_eval, "theme_factor_daily"),
        (transition_eval, "stock_opportunity_daily"),
    ),
)
def test_research_filters_unverified_or_old_source_lineage(
    monkeypatch, module, source_table
) -> None:
    calls = []
    monkeypatch.setattr(
        module, "replace_slice_rows_with_stats",
        lambda db, model, batches, **kwargs: calls.append(kwargs) or {"upserted": 0, "deleted": 1},
    )
    settings = get_settings()
    db = _ResearchDb()
    if module is theme_eval:
        monkeypatch.setattr(
            module, "theme_research_ready_dates", lambda db, dates, settings: (dates, [])
        )
    result = {
        opportunity_eval: opportunity_eval.evaluate_opportunity_batch,
        theme_eval: theme_eval.evaluate_theme_batch,
        transition_eval: transition_eval.evaluate_transition_batch,
    }[module](db, [date(2026, 5, 10)], settings)

    source_sql = next(
        _sql(stmt) for stmt in db.statements if f"FROM {source_table}" in str(stmt)
    )
    assert f"{source_table}.source_strategy_config_hash" in source_sql
    assert analysis_strategy_hash(settings.strategy) in source_sql
    assert "legacy-unverified" != analysis_strategy_hash(settings.strategy)
    assert result["base_rows"] == 0
    assert result["deleted_rows"] == 1
    assert calls
    scope_sql = _sql(select(1).where(*calls[0]["scope_filters"]))
    assert analysis_strategy_hash(settings.strategy) in scope_sql
    assert config_hash(settings.opportunity_config) in scope_sql
    assert config_hash(settings.research_config) in scope_sql


@pytest.mark.parametrize(
    ("module", "source_model", "source_code", "code_field"),
    (
        (opportunity_eval, StockOpportunityDaily, "000001.SZ", "ts_code"),
        (theme_eval, ThemeFactorDaily, "885001.TI", "theme_code"),
    ),
)
def test_current_source_lineage_is_copied_into_forward_result(
    monkeypatch, module, source_model, source_code, code_field
) -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    values = {column.name: None for column in source_model.__table__.columns}
    values.update({
        "trade_date": date(2026, 5, 10), code_field: source_code,
        "source_strategy_config_hash": strategy_hash,
        "calc_version": "opportunity_v1" if module is opportunity_eval else "theme_v1",
    })
    if module is opportunity_eval:
        values.update({"algo_version": settings.algo_version, "state": "S4"})
    else:
        values.update({"heat_score": 80, "data_coverage": 0.8})
    base = SimpleNamespace(**values)
    db = _ResearchDb(base)
    captured = []

    def capture(db, model, batches, **kwargs):
        captured.extend(row for batch in batches for row in batch)
        return {"upserted": len(captured), "deleted": 0}

    monkeypatch.setattr(module, "replace_slice_rows_with_stats", capture)
    monkeypatch.setattr(module, "future_dates", lambda *args, **kwargs: [date(2026, 5, 10)])
    monkeypatch.setattr(module, "benchmark_lookup", lambda *args: {})
    if module is opportunity_eval:
        monkeypatch.setattr(module, "_stock_rows", lambda *args: {})
        monkeypatch.setattr(module, "evaluate_stock_forward", lambda *args, **kwargs: {
            "entry_executable": False,
            **{f"ret{h}": None for h in (5, 10, 20, 60)},
            **{f"benchmark_ret{h}": None for h in (5, 10, 20, 60)},
        })
        result = module.evaluate_opportunity_batch(db, [date(2026, 5, 10)], settings)
    else:
        monkeypatch.setattr(
            module, "theme_research_ready_dates", lambda db, dates, settings: (dates, [])
        )
        monkeypatch.setattr(module, "evaluate_theme_forward", lambda *args, **kwargs: {
            **{f"ret{h}": None for h in (5, 10, 20, 60)},
            **{f"benchmark_ret{h}": None for h in (5, 10, 20, 60)},
        })
        result = module.evaluate_theme_batch(db, [date(2026, 5, 10)], settings)
    assert result["eval_rows"] == 1
    assert captured[0]["strategy_config_hash"] == base.source_strategy_config_hash


@pytest.mark.parametrize("source_status", ("TRANSIENT_ERROR", "PERMISSION_UNAVAILABLE"))
def test_theme_research_skips_incomplete_source_without_deleting_existing_rows(
    monkeypatch, source_status,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ThemeForwardEval.__table__.create(engine)
    settings = get_settings()
    day = date(2026, 5, 10)
    with Session(engine) as db:
        monkeypatch.setattr(theme_eval, "theme_source_status", lambda *args: source_status)
        db.add(
            ThemeForwardEval(
                id=1,
                trade_date=day,
                theme_code="885001.TI",
                strategy_config_hash=analysis_strategy_hash(settings.strategy),
                theme_calc_version=THEME_CALC_VERSION,
                opportunity_config_hash=config_hash(settings.opportunity_config),
                research_version=RESEARCH_VERSION,
                research_config_hash=config_hash(settings.research_config),
                eval_version=RESEARCH_EVAL_VERSION,
                entry_basis="NEXT_CLOSE",
                benchmark_code=settings.research_config["benchmark_code"],
            )
        )
        db.commit()
        result = theme_eval.evaluate_theme_batch(db, [day], settings)
        remaining = db.scalar(select(func.count()).select_from(ThemeForwardEval))
    assert result["theme_skipped_source_dates"] == 1
    assert result["deleted_rows"] == 0
    assert remaining == 1


@pytest.mark.parametrize("source_status", ("PASS", "WARNING"))
def test_theme_research_ready_dates_accepts_usable_source_and_current_factors(
    monkeypatch, source_status
) -> None:
    day = date(2026, 5, 10)

    class Db:
        def scalar(self, statement):
            return 1

    monkeypatch.setattr(theme_eval, "theme_source_status", lambda *args: source_status)
    ready, skipped = theme_eval.theme_research_ready_dates(Db(), [day], get_settings())
    assert ready == [day]
    assert skipped == []


def test_production_services_write_current_strategy_lineage(monkeypatch) -> None:
    settings = get_settings()
    day = date(2026, 5, 10)
    captured = []

    class Db:
        def execute(self, statement):
            return _Rows()

        def commit(self):
            pass

    monkeypatch.setattr(
        opportunity_service_module,
        "resolve_theme_memberships",
        lambda *args: SimpleNamespace(members=pd.DataFrame(), context_by_date={}),
    )
    monkeypatch.setattr(
        opportunity_service_module, "calculate_opportunities",
        lambda **kwargs: pd.DataFrame([{
            "trade_date": day, "ts_code": "000001.SZ", "algo_version": settings.algo_version
        }]),
    )
    monkeypatch.setattr(
        opportunity_service_module, "replace_slice_rows",
        lambda db, model, rows, **kwargs: captured.extend(rows) or len(rows),
    )
    opportunity = opportunity_service_module.OpportunityService(Db())
    monkeypatch.setattr(opportunity, "_versioned_frame", lambda *args: pd.DataFrame())
    monkeypatch.setattr(opportunity, "_states", lambda *args: pd.DataFrame())
    monkeypatch.setattr(opportunity, "_all_frame", lambda *args: pd.DataFrame())
    opportunity.recalc(day, day)
    assert captured[0]["source_strategy_config_hash"] == analysis_strategy_hash(
        settings.strategy
    )

    captured.clear()
    monkeypatch.setattr(
        theme_service_module,
        "resolve_theme_memberships",
        lambda *args: SimpleNamespace(members=pd.DataFrame(), context_by_date={}),
    )
    monkeypatch.setattr(
        theme_service_module, "calculate_theme_factors",
        lambda **kwargs: pd.DataFrame([{"trade_date": day, "theme_code": "885001.TI"}]),
    )
    monkeypatch.setattr(
        theme_service_module, "replace_slice_rows",
        lambda db, model, rows, **kwargs: captured.extend(rows) or len(rows),
    )
    theme = theme_service_module.ThemeFactorService(Db())
    monkeypatch.setattr(theme, "_source_quality", lambda *args: {
        day: {"status": "PASS", "coverage_rate": 1.0}
    })
    monkeypatch.setattr(theme, "_frame", lambda *args: pd.DataFrame())
    monkeypatch.setattr(theme, "_factors", lambda *args: pd.DataFrame())
    monkeypatch.setattr(theme, "_pass_dates", lambda *args, **kwargs: set())
    monkeypatch.setattr(theme, "_open_trade_dates", lambda *args: [day])
    theme.recalc(day, day)
    assert captured[0]["source_strategy_config_hash"] == analysis_strategy_hash(
        settings.strategy
    )


def test_opportunity_reads_only_current_lineage_theme_factors() -> None:
    class Db:
        def __init__(self):
            self.statement = None

        def execute(self, statement):
            self.statement = statement
            return _Rows()

    db = Db()
    service = opportunity_service_module.OpportunityService(db)
    service._versioned_frame(
        ThemeFactorDaily, date(2026, 5, 1), date(2026, 5, 10),
        "theme_v1", config_hash(service.settings.opportunity_config),
    )
    sql = _sql(db.statement)
    assert "theme_factor_daily.source_strategy_config_hash" in sql
    assert analysis_strategy_hash(service.settings.strategy) in sql


def test_transition_prior_day_query_uses_current_source_lineage(monkeypatch) -> None:
    settings = get_settings()
    base = SimpleNamespace(
        trade_date=date(2026, 5, 10), ts_code="000001.SZ",
        state="S2", left_reversal_score=80, opportunity_stage="LEFT_REVERSAL",
        previous_state="S1", right_side_score=None,
        source_strategy_config_hash=analysis_strategy_hash(settings.strategy),
    )
    db = _ResearchDb(base)
    monkeypatch.setattr(
        transition_eval, "future_dates", lambda *args, **kwargs: [base.trade_date]
    )
    monkeypatch.setattr(
        transition_eval, "replace_slice_rows_with_stats",
        lambda db, model, batches, **kwargs: {"upserted": sum(map(len, batches)), "deleted": 0},
    )

    transition_eval.evaluate_transition_batch(db, [base.trade_date], settings)

    source_queries = [
        _sql(stmt) for stmt in db.statements
        if "FROM stock_opportunity_daily" in str(stmt)
    ]
    assert len(source_queries) == 2
    for sql in source_queries:
        assert "stock_opportunity_daily.source_strategy_config_hash" in sql
        assert analysis_strategy_hash(settings.strategy) in sql
