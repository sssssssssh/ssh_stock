from datetime import date

import pytest
from app.models.market_data import OpportunityForwardEval, ResearchTransitionEval, ThemeForwardEval
from app.repositories.replace_slice import replace_slice_rows_with_stats
from app.services.research.opportunity_eval import OPPORTUNITY_KEY
from app.services.research.theme_eval import THEME_KEY
from app.services.research.transition_eval import TRANSITION_KEY
from sqlalchemy.dialects import postgresql


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _Db:
    def __init__(self, existing):
        self.existing = existing
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.existing if statement.is_select else [])


def _sql(statement):
    return str(statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))


def _row(model, code, *, event_key="LEFT_75", strategy="strategy-B"):
    common = {
        "strategy_config_hash": strategy,
        "opportunity_config_hash": "opportunity-B",
        "research_version": "research_v1",
        "research_config_hash": "research-B",
    }
    if model is OpportunityForwardEval:
        return {
            "trade_date": date(2026, 5, 10), "ts_code": code,
            "algo_version": "v1.1", "opportunity_calc_version": "opportunity_v1",
            "eval_version": "research_eval_v1", "entry_basis": "NEXT_OPEN", **common,
        }
    if model is ThemeForwardEval:
        return {
            "trade_date": date(2026, 5, 10), "theme_code": code,
            "theme_calc_version": "theme_v1", "eval_version": "research_eval_v1",
            "entry_basis": "NEXT_OPEN", **common,
        }
    return {
        "event_trade_date": date(2026, 5, 10), "ts_code": code,
        "event_key": event_key, "algo_version": "v1.1", **common,
    }


def _scope(model):
    date_column = (
        model.event_trade_date if model is ResearchTransitionEval else model.trade_date
    )
    filters = [
        date_column == date(2026, 5, 10),
        model.strategy_config_hash == "strategy-B",
        model.opportunity_config_hash == "opportunity-B",
        model.research_config_hash == "research-B",
        model.research_version == "research_v1",
    ]
    if model is not ThemeForwardEval:
        filters.append(model.algo_version == "v1.1")
    if model is OpportunityForwardEval:
        filters.extend((
            model.opportunity_calc_version == "opportunity_v1",
            model.eval_version == "research_eval_v1", model.entry_basis == "NEXT_OPEN",
        ))
    if model is ThemeForwardEval:
        filters.extend((
            model.theme_calc_version == "theme_v1",
            model.eval_version == "research_eval_v1", model.entry_basis == "NEXT_OPEN",
        ))
    return filters


@pytest.mark.parametrize(
    ("model", "keys"),
    (
        (OpportunityForwardEval, OPPORTUNITY_KEY),
        (ThemeForwardEval, THEME_KEY),
        (ResearchTransitionEval, TRANSITION_KEY),
    ),
)
def test_research_slice_upserts_survivors_and_deletes_only_stale(model, keys) -> None:
    surviving = _row(model, "A")
    stale = _row(model, "B", event_key="RIGHT_SIDE_NEW")
    later_batch = _row(model, "C", event_key="LEFT_80")
    db = _Db([tuple(row[key] for key in keys) for row in (surviving, stale)])

    result = replace_slice_rows_with_stats(
        db, model, ([surviving], [later_batch]),
        scope_filters=_scope(model), key_columns=keys,
    )

    assert result == {"upserted": 2, "deleted": 1}
    select_sql, delete_sql = _sql(db.statements[0]), _sql(db.statements[-1])
    assert "strategy-B" in select_sql and "opportunity-B" in select_sql
    assert "research-B" in select_sql
    assert "strategy-B" in delete_sql and "opportunity-B" in delete_sql
    assert "research-B" in delete_sql
    assert "'B'" in delete_sql
    assert "'A'" not in delete_sql and "'C'" not in delete_sql


@pytest.mark.parametrize(
    ("model", "keys"),
    (
        (OpportunityForwardEval, OPPORTUNITY_KEY),
        (ThemeForwardEval, THEME_KEY),
        (ResearchTransitionEval, TRANSITION_KEY),
    ),
)
def test_empty_research_slice_deletes_all_current_identity_rows(model, keys) -> None:
    existing = [_row(model, "A"), _row(model, "B")]
    db = _Db([tuple(row[key] for key in keys) for row in existing])

    result = replace_slice_rows_with_stats(
        db, model, (), scope_filters=_scope(model), key_columns=keys,
    )

    assert result == {"upserted": 0, "deleted": 2}
    assert len(db.statements) == 2
    assert "'A'" in _sql(db.statements[-1])
    assert "'B'" in _sql(db.statements[-1])


def test_transition_research_removes_obsolete_threshold_and_right_event() -> None:
    rows = [
        _row(ResearchTransitionEval, "A", event_key="LEFT_75"),
        _row(ResearchTransitionEval, "A", event_key="LEFT_80"),
        _row(ResearchTransitionEval, "B", event_key="RIGHT_SIDE_NEW"),
    ]
    db = _Db([tuple(row[key] for key in TRANSITION_KEY) for row in rows])

    result = replace_slice_rows_with_stats(
        db, ResearchTransitionEval, ([rows[1]],),
        scope_filters=_scope(ResearchTransitionEval), key_columns=TRANSITION_KEY,
    )

    delete_sql = _sql(db.statements[-1])
    assert result == {"upserted": 1, "deleted": 2}
    assert "LEFT_75" in delete_sql and "RIGHT_SIDE_NEW" in delete_sql
    assert "LEFT_80" not in delete_sql
