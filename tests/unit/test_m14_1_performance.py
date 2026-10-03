import importlib.util
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.core.performance_config import PerformanceConfig
from app.domain.performance import (
    PerformanceEngine,
    PerformanceSourceRow,
    PerformanceSourceSnapshot,
)
from app.services.performance.identity import performance_source_hash
from app.services.performance.source import PerformanceSourceError, PerformanceSourceProvider
from pydantic import ValidationError


def _config(**overrides) -> PerformanceConfig:
    values = {
        "version": "performance_v1",
        "annualization_trade_days": 252,
        "short_sample_warning_trade_days": 20,
        "zero_return_epsilon": Decimal("0"),
    }
    values.update(overrides)
    return PerformanceConfig.model_validate(values)


def _rows(*navs: str) -> tuple[PerformanceSourceRow, ...]:
    start = date(2026, 1, 5)
    return tuple(
        PerformanceSourceRow(
            trade_date=start + timedelta(days=index),
            nav=Decimal(nav),
            total_assets=Decimal(nav) * Decimal("1000000"),
            cash=Decimal(nav) * Decimal("500000"),
            market_value=Decimal(nav) * Decimal("500000"),
            gross_exposure=Decimal("0.5"),
            net_exposure=Decimal("0.5"),
            position_count=1,
            trading_cost=Decimal(index),
        )
        for index, nav in enumerate(navs)
    )


def _snapshot(*navs: str) -> PerformanceSourceSnapshot:
    rows = _rows(*navs)
    return PerformanceSourceSnapshot(
        run_id=uuid.uuid4(),
        start_date=rows[0].trade_date,
        end_date=rows[-1].trade_date,
        initial_cash=Decimal("1000000"),
        backtest_engine_version="backtest_v3",
        portfolio_version="portfolio_v3",
        execution_version="execution_v3",
        accounting_version="accounting_v3",
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
        source_hash="b" * 64,
        rows=rows,
    )


def _validation_run(*, final_nav: str = "1") -> SimpleNamespace:
    return SimpleNamespace(
        initial_cash=Decimal("1000000"),
        result_summary={"final_nav": final_nav},
    )


def _validation_row(
    *,
    nav: str = "1",
    total_assets: str = "1000000",
    cash: str = "400000",
    market_value: str = "600000",
    position_count: int = 1,
    gross_exposure: str = "0.6",
    net_exposure: str = "0.6",
    trading_cost: str = "0",
) -> SimpleNamespace:
    return SimpleNamespace(
        trade_date=date(2026, 1, 5),
        nav=Decimal(nav),
        total_assets=Decimal(total_assets),
        cash=Decimal(cash),
        market_value=Decimal(market_value),
        position_count=position_count,
        gross_exposure=Decimal(gross_exposure),
        net_exposure=Decimal(net_exposure),
        trading_cost=Decimal(trading_cost),
    )


def test_performance_config_is_strict_and_positive() -> None:
    with pytest.raises(ValidationError):
        _config(benchmark_code="000300.SH")
    with pytest.raises(ValidationError):
        _config(annualization_trade_days=0)
    with pytest.raises(ValidationError):
        _config(version="performance_v2")


def test_five_day_all_cash_nav_is_flat() -> None:
    result = PerformanceEngine().calculate(
        _snapshot("1", "1", "1", "1", "1"), _config()
    )
    assert result.final_nav == Decimal("1")
    assert result.cumulative_return == Decimal("0")
    assert result.annualized_return == Decimal("0")
    assert result.max_drawdown == Decimal("0")
    assert (result.positive_days, result.negative_days, result.flat_days) == (0, 0, 5)


@pytest.mark.parametrize(
    ("nav", "expected_return", "counts"),
    [
        ("1.10", Decimal("0.10"), (1, 0, 0)),
        ("0.90", Decimal("-0.10"), (0, 1, 0)),
    ],
)
def test_first_day_return_uses_initial_nav_one(nav, expected_return, counts) -> None:
    result = PerformanceEngine().calculate(_snapshot(nav), _config())
    assert result.daily[0].daily_return == expected_return
    assert (result.positive_days, result.negative_days, result.flat_days) == counts


def test_continuous_rise_has_no_drawdown() -> None:
    result = PerformanceEngine().calculate(_snapshot("1.01", "1.05", "1.10"), _config())
    assert result.max_drawdown == 0
    assert all(point.drawdown == 0 for point in result.daily)
    assert result.positive_days == 3
    assert result.max_drawdown_peak_date is None
    assert result.max_drawdown_trough_date is None
    assert result.max_drawdown_recovery_date is None
    assert result.max_drawdown_duration_days == 0


def test_continuous_fall_tracks_baseline_peak_and_duration() -> None:
    result = PerformanceEngine().calculate(_snapshot("0.9", "0.8", "0.7"), _config())
    assert result.max_drawdown == Decimal("-0.3")
    assert result.max_drawdown_peak_date is None
    assert result.max_drawdown_trough_date == date(2026, 1, 7)
    assert result.max_drawdown_recovery_date is None
    assert result.max_drawdown_duration_days == 3


def test_v_shape_drawdown_records_first_recovery() -> None:
    result = PerformanceEngine().calculate(
        _snapshot("1.1", "0.88", "0.99", "1.1", "1.2"), _config()
    )
    assert result.max_drawdown == Decimal("-0.2")
    assert result.max_drawdown_peak_date == date(2026, 1, 5)
    assert result.max_drawdown_trough_date == date(2026, 1, 6)
    assert result.max_drawdown_recovery_date == date(2026, 1, 8)
    assert result.max_drawdown_duration_days == 2


def test_unrecovered_drawdown_has_null_recovery() -> None:
    result = PerformanceEngine().calculate(_snapshot("1.2", "1.0", "1.1"), _config())
    assert result.max_drawdown_recovery_date is None
    assert result.max_drawdown == Decimal("1.0") / Decimal("1.2") - Decimal("1")
    assert result.max_drawdown_duration_days == 2


def test_max_drawdown_duration_belongs_to_deep_episode_not_longer_shallow_one() -> None:
    result = PerformanceEngine().calculate(
        _snapshot("1.2", "0.84", "1.2", "1.15", "1.14", "1.13", "1.12"),
        _config(),
    )
    assert result.max_drawdown == Decimal("-0.3")
    assert result.max_drawdown_peak_date == date(2026, 1, 5)
    assert result.max_drawdown_trough_date == date(2026, 1, 6)
    assert result.max_drawdown_recovery_date == date(2026, 1, 7)
    assert result.max_drawdown_duration_days == 1


def test_single_day_result_is_computed_with_short_sample_warning() -> None:
    result = PerformanceEngine().calculate(_snapshot("1.02"), _config())
    assert result.trade_days == 1
    assert result.annualized_return > Decimal("1")
    assert result.warnings == ("SHORT_SAMPLE_ANNUALIZATION",)


@pytest.mark.parametrize("nav", ["1.10", "1.20", "0.01"])
def test_single_day_extreme_annualized_return_remains_decimal(nav) -> None:
    result = PerformanceEngine().calculate(_snapshot(nav), _config())
    assert result.annualized_return.is_finite()


def test_warning_threshold_does_not_suppress_annualization() -> None:
    result = PerformanceEngine().calculate(
        _snapshot("1.01", "1.02"),
        _config(short_sample_warning_trade_days=2),
    )
    assert result.warnings == ()
    assert result.annualized_return > 0


def test_zero_return_epsilon_classifies_small_moves_as_flat() -> None:
    result = PerformanceEngine().calculate(
        _snapshot("1.0005", "1.002"),
        _config(zero_return_epsilon=Decimal("0.001")),
    )
    assert (result.positive_days, result.negative_days, result.flat_days) == (1, 0, 1)


def test_daily_exposure_and_cash_ratio_are_preserved() -> None:
    result = PerformanceEngine().calculate(_snapshot("1"), _config())
    point = result.daily[0]
    assert point.cash_ratio == Decimal("0.5")
    assert point.gross_exposure == Decimal("0.5")
    assert point.position_count == 1
    assert point.trading_cost == 0


def test_source_validation_rejects_missing_and_extra_dates() -> None:
    run = _validation_run()
    rows = (_validation_row(),)
    with pytest.raises(PerformanceSourceError, match="PERFORMANCE_SOURCE_INCOMPLETE"):
        PerformanceSourceProvider._validate(
            run,
            (date(2026, 1, 5), date(2026, 1, 6)),
            rows,
        )
    with pytest.raises(PerformanceSourceError, match="PERFORMANCE_SOURCE_INCOMPLETE"):
        PerformanceSourceProvider._validate(
            run,
            (date(2026, 1, 6),),
            rows,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"nav": "0"},
        {"total_assets": "0", "cash": "0", "market_value": "0"},
        {"cash": "-1", "market_value": "1000001"},
        {"market_value": "-1", "cash": "1000001"},
        {"position_count": -1},
        {"gross_exposure": "-0.1"},
        {"net_exposure": "-0.1"},
        {"trading_cost": "-0.01"},
    ],
)
def test_source_validation_fails_closed_for_invalid_values(overrides) -> None:
    row = _validation_row(**overrides)
    with pytest.raises(PerformanceSourceError, match="PERFORMANCE_SOURCE_INCOMPLETE"):
        PerformanceSourceProvider._validate(
            _validation_run(), (row.trade_date,), (row,)
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"cash": "399999"},
        {"nav": "1.01"},
    ],
)
def test_source_validation_rejects_ledger_identity_mismatch(overrides) -> None:
    row = _validation_row(**overrides)
    with pytest.raises(
        PerformanceSourceError, match="PERFORMANCE_LEDGER_IDENTITY_MISMATCH"
    ):
        PerformanceSourceProvider._validate(
            _validation_run(final_nav=str(row.nav)), (row.trade_date,), (row,)
        )


def test_source_validation_rejects_final_nav_mismatch() -> None:
    row = _validation_row(
        nav="1.1",
        total_assets="1100000",
        cash="440000",
        market_value="660000",
    )
    with pytest.raises(
        PerformanceSourceError, match="PERFORMANCE_NAV_IDENTITY_MISMATCH"
    ):
        PerformanceSourceProvider._validate(
            _validation_run(), (row.trade_date,), (row,)
        )


def test_source_validation_rejects_empty_calendar_and_missing_final_nav() -> None:
    with pytest.raises(PerformanceSourceError, match="PERFORMANCE_SOURCE_INCOMPLETE"):
        PerformanceSourceProvider._validate(SimpleNamespace(), (), ())
    row = _validation_row()
    with pytest.raises(PerformanceSourceError, match="PERFORMANCE_NAV_IDENTITY_MISMATCH"):
        PerformanceSourceProvider._validate(
            SimpleNamespace(initial_cash=Decimal("1000000"), result_summary={}),
            (row.trade_date,),
            (row,),
        )


def test_source_hash_is_canonical_and_covers_m13_fact_changes() -> None:
    run = SimpleNamespace(
        id=uuid.uuid4(),
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 5),
        initial_cash=Decimal("1000000.0000"),
        backtest_engine_version="backtest_v3",
        portfolio_version="portfolio_v3",
        execution_version="execution_v3",
        accounting_version="accounting_v3",
    )
    first = performance_source_hash(
        run,
        _rows("1.00000000"),
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
    )
    equivalent = performance_source_hash(
        SimpleNamespace(**{**run.__dict__, "initial_cash": Decimal("1000000")}),
        _rows("1"),
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
    )
    changed = performance_source_hash(
        run,
        _rows("1.01"),
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
    )
    assert first == equivalent
    assert first != changed


def test_performance_domain_does_not_import_orm() -> None:
    import inspect

    import app.domain.performance.engine as engine_module

    source = inspect.getsource(engine_module)
    assert "sqlalchemy" not in source.lower()
    assert "app.models" not in source


def test_0037_migration_preflights_cross_run_and_unsafe_downgrade(monkeypatch) -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20261002_0037_m14_1_1_performance_closeout.py"
    )
    spec = importlib.util.spec_from_file_location("m14_1_1_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class Connection:
        def scalar(self, _statement):
            return 1

    monkeypatch.setattr(migration.op, "get_bind", lambda: Connection())
    with pytest.raises(RuntimeError, match="cross-run daily"):
        migration.upgrade()
    with pytest.raises(RuntimeError, match="cannot safely narrow"):
        migration.downgrade()
