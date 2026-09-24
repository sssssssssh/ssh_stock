from datetime import date
from types import SimpleNamespace

import app.jobs.catchup_job as catchup_module
import app.services.ingestion.service as ingestion_module
import pandas as pd
import pytest
from app.jobs.catchup_job import is_analysis_complete
from app.models.market_data import ThemeLimitDaily, ThemeMoneyflowDaily
from app.services.ingestion.service import IngestionService, ThemeDailyQualityError
from app.services.opportunity.engine import (
    OpportunityConfig,
    PositionConfig,
    _extension_risk,
    _opportunity_score,
)
from app.services.theme.engine import ThemeConfig, _lifecycle, calculate_theme_factors
from app.services.theme.service import ThemeFactorService


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Db:
    def __init__(self, values=("A.TI", "B.TI")):
        self.values = list(values)
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement):
        return _ScalarResult(self.values)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_theme_lifecycle_and_position_thresholds_are_config_driven() -> None:
    row = pd.Series({"heat_score": 65, "heat_momentum3": 6, "prev_heat": 50})
    default = ThemeConfig("000300.SH", 1, {"turnover_ratio20": 1.0})
    raised = ThemeConfig(
        "000300.SH",
        1,
        {"turnover_ratio20": 1.0},
        lifecycle_heating=70,
    )

    assert _lifecycle(row, default) == "HEATING"
    assert _lifecycle(row, raised) != "HEATING"
    stock = pd.Series(
        {"state": "S5", "adj_close": 12.2, "ma20": 10.0, "ma60": 9.0, "amount_ratio20": 1}
    )
    assert _extension_risk(stock, PositionConfig(ma20_extreme=0.20)) == "EXTREME"
    assert _extension_risk(stock, PositionConfig(ma20_extreme=0.25)) == "EXTENDED"


def test_opportunity_combination_weights_are_config_driven() -> None:
    row = pd.Series(
        {
            "opportunity_stage": "LEFT_REVERSAL",
            "left_reversal_score": 80.0,
            "context_score": 20.0,
        }
    )
    first = OpportunityConfig({}, {}, 60, 75, left_structure_weight=0.8)
    second = OpportunityConfig(
        {}, {}, 60, 75, left_structure_weight=0.5, left_context_weight=0.5
    )

    assert _opportunity_score(row, first) == 68
    assert _opportunity_score(row, second) == 50


def test_hot_rank_one_scores_above_lower_ranks_and_single_rank_is_nonzero() -> None:
    target = date(2026, 9, 17)
    daily = pd.DataFrame(
        [
            {"trade_date": target, "theme_code": code, "close": 100, "turnover_rate": 1}
            for code in ("A", "B", "C")
        ]
    )
    limits = pd.DataFrame(
        [
            {
                "trade_date": target,
                "theme_code": code,
                "up_nums": 1,
                "cons_nums": 1,
                "days": 1,
                "hot_rank": rank,
            }
            for code, rank in (("A", 1), ("B", 2), ("C", 3))
        ]
    )
    moneyflow = pd.DataFrame(
        [
            {
                "trade_date": target,
                "theme_code": code,
                "net_amount": 1,
                "company_num": 10,
            }
            for code in ("A", "B", "C")
        ]
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
        ThemeConfig("000300.SH", 1, {"limit_strength_score": 1.0}),
    ).set_index("theme_code")

    assert result.loc["A", "limit_strength_score"] > result.loc["B", "limit_strength_score"]
    assert result.loc["B", "limit_strength_score"] > result.loc["C", "limit_strength_score"]
    assert result.loc["A", "data_coverage"] == 1.0


def test_theme_daily_error_preserves_raw_and_does_not_reconcile(monkeypatch) -> None:
    target = date(2026, 9, 17)
    provider = SimpleNamespace(
        get_ths_daily=lambda value: pd.DataFrame(
            [{"ts_code": "A.TI", "trade_date": "20260917", "close": 10}]
        )
    )
    reconciled = []
    monkeypatch.setattr(ingestion_module, "persist_coverage_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ingestion_module,
        "reconcile_daily_snapshot",
        lambda *args, **kwargs: reconciled.append(True),
    )

    with pytest.raises(ThemeDailyQualityError):
        IngestionService(_Db(), provider).sync_theme_daily(target)

    assert reconciled == []


@pytest.mark.parametrize(
    ("model", "dataset"),
    [
        (ThemeMoneyflowDaily, "theme_moneyflow_daily"),
        (ThemeLimitDaily, "theme_limit_daily"),
    ],
)
def test_successful_optional_snapshot_reconciles_stale_rows(
    monkeypatch, model, dataset
) -> None:
    target = date(2026, 9, 17)
    dirty = []
    monkeypatch.setattr(
        ingestion_module,
        "reconcile_daily_snapshot",
        lambda *args, **kwargs: {target},
    )
    monkeypatch.setattr(ingestion_module, "upsert_rows", lambda *args, **kwargs: 0)
    monkeypatch.setattr(ingestion_module, "_persist_theme_quality", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ingestion_module,
        "record_dirty_range",
        lambda *args, **kwargs: dirty.append(kwargs),
    )
    service = IngestionService(_Db(), SimpleNamespace())

    status = service._sync_optional_theme_source(
        target,
        "ths_theme_moneyflow" if model is ThemeMoneyflowDaily else "ths_theme_limit",
        lambda value: pd.DataFrame(),
        lambda frame: [],
        model,
    )

    assert status == "SOURCE_EMPTY"
    assert dirty[0]["dataset"] == dataset


def test_theme_factor_error_date_does_not_replace_existing_results() -> None:
    service = ThemeFactorService.__new__(ThemeFactorService)
    service._source_quality = lambda start, end: {
        date(2026, 9, 17): {"status": "ERROR", "coverage_rate": 0.4}
    }

    assert service.recalc(date(2026, 9, 17), date(2026, 9, 17)) == 0


def test_catchup_requires_current_opportunity_quality(monkeypatch) -> None:
    monkeypatch.setattr(catchup_module, "is_core_analysis_complete", lambda *args, **kwargs: True)
    monkeypatch.setattr(catchup_module, "config_hash", lambda config: config["hash"])
    captured = {}

    def quality(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(is_complete=False)

    monkeypatch.setattr(catchup_module, "check_opportunity_quality", quality)

    complete = is_analysis_complete(
        object(),
        date(2026, 9, 17),
        strategy={"hash": "strategy"},
        opportunity_config={"hash": "opportunity"},
        algo_version="v1.0",
    )

    assert complete is False
    assert captured["opportunity_hash"] == "opportunity"
