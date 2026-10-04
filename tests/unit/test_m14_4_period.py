import importlib.util
import inspect
import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from app.core.performance_period_config import PerformancePeriodConfig
from app.domain.performance import period_engine
from app.domain.performance.period_contracts import (
    PeriodSourceDaily,
    PeriodSourceEpisode,
    PeriodSourceSnapshot,
)
from app.domain.performance.period_engine import PeriodEngine
from app.services.performance.period_identity import period_source_hash
from pydantic import ValidationError


def _config(**overrides) -> PerformancePeriodConfig:
    values = {
        "version": "period_v1",
        "period_types": ["MONTH", "YEAR"],
        "excess_return_method": "RELATIVE",
        "closed_episode_attribution": "EXIT_DATE",
    }
    values.update(overrides)
    return PerformancePeriodConfig.model_validate(values)


def _daily(trade_date: date, strategy: str, benchmark: str, turnover: str):
    amount = Decimal("100")
    return PeriodSourceDaily(
        trade_date=trade_date,
        strategy_daily_return=Decimal(strategy),
        benchmark_daily_return=Decimal(benchmark),
        daily_turnover=Decimal(turnover),
        traded_gross_amount=amount,
        commission=Decimal("1"),
        stamp_tax=Decimal("2"),
        transfer_fee=Decimal("3"),
        cash_fee_total=Decimal("6"),
        slippage_cost=Decimal("4"),
        total_execution_cost=Decimal("10"),
    )


def _source() -> PeriodSourceSnapshot:
    return PeriodSourceSnapshot(
        run_id=uuid.UUID(int=1),
        performance_id=uuid.UUID(int=2),
        risk_id=uuid.UUID(int=3),
        trade_id=uuid.UUID(int=4),
        performance_version="performance_v1",
        performance_config_hash="a" * 64,
        performance_source_hash="b" * 64,
        risk_version="risk_v1",
        risk_config_hash="c" * 64,
        risk_source_hash="d" * 64,
        benchmark_source_hash="e" * 64,
        trade_version="trade_v1",
        trade_config_hash="f" * 64,
        trade_source_hash="1" * 64,
        period_version="period_v1",
        period_config_hash="2" * 64,
        period_source_hash="",
        start_date=date(2025, 12, 31),
        end_date=date(2026, 2, 2),
        trade_days=4,
        daily=(
            _daily(date(2025, 12, 31), "0.10", "0.05", "0.1"),
            _daily(date(2026, 1, 2), "-0.05", "0.02", "0.2"),
            _daily(date(2026, 1, 30), "0.10", "-0.01", "0.3"),
            _daily(date(2026, 2, 2), "0.01", "0.005", "0.4"),
        ),
        closed_episodes=(
            PeriodSourceEpisode(date(2026, 1, 30), "WIN", Decimal("30")),
            PeriodSourceEpisode(date(2026, 1, 30), "BREAKEVEN", Decimal("0")),
            PeriodSourceEpisode(date(2026, 2, 2), "LOSS", Decimal("-10")),
        ),
    )


def test_period_config_is_strict_and_frozen() -> None:
    assert _config().period_types == ("MONTH", "YEAR")
    with pytest.raises(ValidationError):
        _config(period_types=["YEAR", "MONTH"])
    with pytest.raises(ValidationError):
        _config(extra_option=True)
    with pytest.raises(ValidationError):
        _config(excess_return_method="SPREAD")


def test_month_and_year_compounding_relative_trade_and_episode_attribution() -> None:
    result = PeriodEngine().calculate(_source(), _config())
    assert (result.month_count, result.year_count) == (3, 2)
    january = next(row for row in result.periods if row.period_key == "2026-01")
    assert january.strategy_return == Decimal("0.045")
    assert january.benchmark_return == Decimal("0.0098")
    with localcontext() as context:
        context.prec = 60
        assert january.relative_return == Decimal("1.045") / Decimal("1.0098") - 1
    assert january.return_spread == Decimal("0.0352")
    assert january.period_turnover == Decimal("0.5")
    assert january.traded_gross_amount == Decimal("200")
    assert january.total_execution_cost == Decimal("20")
    assert january.closed_episode_count == 2
    assert january.win_count == 1
    assert january.breakeven_count == 1
    assert january.win_rate == Decimal("0.5")
    assert january.closed_realized_pnl == Decimal("30")
    december = next(row for row in result.periods if row.period_key == "2025-12")
    assert december.closed_episode_count == 0
    assert december.win_rate is None
    year = next(
        row for row in result.periods if row.period_type == "YEAR" and row.period_key == "2026"
    )
    assert year.closed_episode_count == 3
    with localcontext() as context:
        context.prec = 60
        assert year.win_rate == Decimal("1") / Decimal("3")


def test_cross_month_episode_uses_exit_date_and_open_episode_is_not_in_source() -> None:
    result = PeriodEngine().calculate(_source(), _config())
    january = next(row for row in result.periods if row.period_key == "2026-01")
    february = next(row for row in result.periods if row.period_key == "2026-02")
    assert january.closed_realized_pnl == Decimal("30")
    assert february.closed_realized_pnl == Decimal("-10")


def test_period_source_hash_is_deterministic_and_binds_every_upstream_identity() -> None:
    source = _source()
    first = period_source_hash(source)
    assert first == period_source_hash(source)
    for field, value in (
        ("performance_source_hash", "9" * 64),
        ("risk_source_hash", "8" * 64),
        ("benchmark_source_hash", "7" * 64),
        ("trade_source_hash", "6" * 64),
        ("period_config_hash", "5" * 64),
    ):
        assert period_source_hash(replace(source, **{field: value})) != first


def test_period_domain_has_no_infrastructure_or_recalculation_dependencies() -> None:
    source = inspect.getsource(period_engine)
    for forbidden in (
        "sqlalchemy",
        "Session",
        "app.models",
        "numpy",
        "pandas",
        "Sharpe",
        "Alpha",
        "PortfolioFill",
    ):
        assert forbidden not in source


def test_migration_0040_downgrade_fails_closed_with_artifacts(monkeypatch) -> None:
    path = (
        Path(__file__).parents[2]
        / "migrations/versions/20261004_0040_m14_4_productization_period.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0040", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Connection:
        @staticmethod
        def scalar(_statement):
            return 1

    monkeypatch.setattr(module.op, "get_bind", lambda: Connection())
    with pytest.raises(RuntimeError, match="cannot downgrade M14.4"):
        module.downgrade()
