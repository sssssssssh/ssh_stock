import importlib.util
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import app.services.portfolio.candidates as candidate_module
import pytest
from app.core.config import get_settings
from app.core.execution_config import ExecutionConfig
from app.core.portfolio_config import PortfolioConfig
from app.domain.portfolio import (
    AccountState,
    CandidateSourceIdentity,
    DailyPortfolioSnapshot,
    ExecutionDecision,
    OrderIntent,
    SignalCandidate,
)
from app.models.market_data import StockOpportunityDaily, StockStateDaily
from app.services.analysis_identity import (
    OPPORTUNITY_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.portfolio.application import PortfolioApplicationService
from app.services.portfolio.backtest import BacktestEngine
from app.services.portfolio.candidates import CandidateBatch, OpportunityCandidateProvider
from app.services.portfolio.contracts import (
    PortfolioSourceNotReadyError,
    SourceReadinessStatus,
)
from app.services.portfolio.policy import TopNEqualWeightPolicy
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _portfolio_config(**updates) -> PortfolioConfig:
    raw = get_settings().portfolio_config.model_dump(mode="python")
    raw.update(updates)
    return PortfolioConfig.model_validate(raw)


def _candidate(code: str, score: str) -> SignalCandidate:
    return SignalCandidate(
        trade_date=date(2026, 9, 1),
        ts_code=code,
        stage="TREND",
        state="S4",
        score=Decimal(score),
        rank_score=Decimal(score),
        extension_risk=None,
        industry_sector_id=None,
        primary_theme_code=None,
        source_identity=CandidateSourceIdentity(
            algo_version="v1.1",
            opportunity_calc_version="opportunity_v1",
            opportunity_config_hash="opportunity",
            source_strategy_config_hash="strategy",
        ),
    )


def test_portfolio_and_execution_config_are_strict_and_decimal() -> None:
    settings = get_settings()
    assert settings.portfolio_config.version == "portfolio_v1"
    assert settings.execution_config.version == "execution_v1"
    assert settings.portfolio_config.initial_cash_cny == Decimal("1000000")
    assert settings.execution_config.trading_cost.commission_rate == Decimal("0.0003")

    raw = settings.portfolio_config.model_dump(mode="python")
    raw["unknown"] = True
    with pytest.raises(ValidationError, match="unknown"):
        PortfolioConfig.model_validate(raw)

    execution = settings.execution_config.model_dump(mode="python")
    execution["board_lot"] = 0
    with pytest.raises(ValidationError, match="board_lot"):
        ExecutionConfig.model_validate(execution)


def test_m13_application_service_rejects_non_backtest_mode() -> None:
    settings = get_settings()
    raw = settings.portfolio_config.model_dump(mode="python")
    raw["account_mode"] = "PAPER"
    paper_settings = settings.model_copy(
        update={"portfolio_config": PortfolioConfig.model_validate(raw)}
    )
    with pytest.raises(ValueError, match="BACKTEST"):
        PortfolioApplicationService(object(), paper_settings)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("initial_cash_cny",), 0),
        (("candidate", "allowed_stages"), []),
        (("candidate", "top_n"), 0),
        (("construction", "max_positions"), 0),
        (("construction", "max_new_positions_per_day"), 0),
        (("construction", "max_single_position_weight"), Decimal("1.1")),
        (("construction", "min_cash_ratio"), Decimal("1")),
    ],
)
def test_portfolio_config_rejects_invalid_boundaries(path, value) -> None:
    raw = get_settings().portfolio_config.model_dump(mode="python")
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        PortfolioConfig.model_validate(raw)


@pytest.mark.parametrize(
    "stages",
    [["TREND", "TREND"], ["NOT_A_STAGE"]],
)
def test_portfolio_config_rejects_duplicate_or_unknown_stages(stages) -> None:
    raw = get_settings().portfolio_config.model_dump(mode="python")
    raw["candidate"]["allowed_stages"] = stages
    with pytest.raises(ValidationError):
        PortfolioConfig.model_validate(raw)


def test_top_n_equal_weight_policy_is_stable_and_respects_caps() -> None:
    config = _portfolio_config()
    candidates = [
        _candidate("B.SZ", "90"),
        _candidate("A.SZ", "90"),
        _candidate("C.SZ", "80"),
    ]
    account = AccountState(date(2026, 9, 1), Decimal("100"))

    target = TopNEqualWeightPolicy().build_target(candidates, account, config)

    assert [item.ts_code for item in target.targets] == ["A.SZ", "B.SZ", "C.SZ"]
    assert all(item.target_weight == Decimal("0.10") for item in target.targets)
    assert sum(item.target_weight for item in target.targets) <= Decimal("0.98")
    assert target.target_cash_ratio == Decimal("0.70")


def test_top_n_equal_weight_policy_handles_empty_unavailable_source() -> None:
    config = _portfolio_config()
    account = AccountState(date(2026, 9, 1), Decimal("100"))
    target = TopNEqualWeightPolicy().build_target(
        [], account, config, source_available=False
    )
    assert target.targets == ()
    assert target.target_cash_ratio == Decimal("1")
    assert target.source_available is False


def test_preview_allows_ready_empty_signal_and_returns_all_cash() -> None:
    settings = get_settings()
    service = PortfolioApplicationService.__new__(PortfolioApplicationService)
    service.portfolio_config = settings.portfolio_config
    service.policy = TopNEqualWeightPolicy()

    class Provider:
        def list_candidates(self, trade_date, config):
            return CandidateBatch(
                trade_date,
                (),
                SourceReadinessStatus.READY,
                None,
                2,
                2,
            )

    service.candidate_provider = Provider()
    target = service.preview_target(date(2026, 9, 1))
    assert target.targets == ()
    assert target.target_cash_ratio == Decimal("1")
    assert target.source_available is True


def test_preview_rejects_unready_source_before_policy_is_called() -> None:
    settings = get_settings()
    service = PortfolioApplicationService.__new__(PortfolioApplicationService)
    service.portfolio_config = settings.portfolio_config

    class Provider:
        def list_candidates(self, trade_date, config):
            return CandidateBatch(
                trade_date,
                (),
                SourceReadinessStatus.INCOMPLETE,
                "STATE_OPPORTUNITY_SET_MISMATCH",
                100,
                99,
            )

    class Policy:
        def build_target(self, *args, **kwargs):
            raise AssertionError("unready source must not reach portfolio policy")

    service.candidate_provider = Provider()
    service.policy = Policy()
    with pytest.raises(PortfolioSourceNotReadyError):
        service.preview_target(date(2026, 9, 1))


def test_same_candidates_with_different_portfolio_config_change_only_target() -> None:
    candidates = [_candidate("A.SZ", "90"), _candidate("B.SZ", "80")]
    original = tuple(candidates)
    account = AccountState(date(2026, 9, 1), Decimal("100"))
    one_raw = get_settings().portfolio_config.model_dump(mode="python")
    one_raw["candidate"]["top_n"] = 1
    two_raw = get_settings().portfolio_config.model_dump(mode="python")
    two_raw["candidate"]["top_n"] = 2
    policy = TopNEqualWeightPolicy()

    one = policy.build_target(candidates, account, PortfolioConfig.model_validate(one_raw))
    two = policy.build_target(candidates, account, PortfolioConfig.model_validate(two_raw))

    assert len(one.targets) == 1
    assert len(two.targets) == 2
    assert tuple(candidates) == original


def test_candidate_provider_uses_exact_date_current_identity_and_stable_order(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockStateDaily.__table__.create(engine)
    StockOpportunityDaily.__table__.create(engine)
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    opportunity_hash = config_hash(settings.opportunity_config)
    target = date(2026, 9, 1)
    monkeypatch.setattr(candidate_module, "is_core_analysis_complete", lambda *a, **k: True)

    def row(code: str, *, score: float, algo: str | None = None, day: date = target):
        return StockOpportunityDaily(
            trade_date=day,
            ts_code=code,
            algo_version=algo or settings.algo_version,
            state="S4",
            opportunity_stage="TREND",
            opportunity_score=score,
            reason_codes=["TREND"],
            calc_version=OPPORTUNITY_CALC_VERSION,
            config_hash=opportunity_hash,
            source_strategy_config_hash=strategy_hash,
            calculated_at=datetime(2026, 9, 1),
        )

    with Session(engine) as db:
        db.add_all(
            [
                StockStateDaily(
                    trade_date=target,
                    ts_code="A.SZ",
                    algo_version=settings.algo_version,
                    state="S4",
                    is_new_state=False,
                    fast_transition=False,
                    calc_version=TREND_CALC_VERSION,
                    config_hash=strategy_hash,
                ),
                StockStateDaily(
                    trade_date=target,
                    ts_code="B.SZ",
                    algo_version=settings.algo_version,
                    state="S4",
                    is_new_state=False,
                    fast_transition=False,
                    calc_version=TREND_CALC_VERSION,
                    config_hash=strategy_hash,
                ),
                row("B.SZ", score=90),
                row("A.SZ", score=90),
                row("OLD.SZ", score=100, algo="old"),
                row("PAST.SZ", score=99, day=date(2026, 8, 31)),
            ]
        )
        db.commit()
        batch = OpportunityCandidateProvider(db, settings).list_candidates(
            target, settings.portfolio_config
        )
        missing = OpportunityCandidateProvider(db, settings).list_candidates(
            date(2026, 9, 2), settings.portfolio_config
        )

    assert batch.source_status == SourceReadinessStatus.READY
    assert batch.state_count == batch.opportunity_count == 2
    assert [item.ts_code for item in batch.candidates] == ["A.SZ", "B.SZ"]
    assert missing.candidates == ()
    assert missing.source_status == SourceReadinessStatus.UNAVAILABLE


def test_candidate_source_is_unavailable_when_only_old_identity_exists() -> None:
    class Scalar:
        def scalar_one(self):
            return 0

        def scalars(self):
            return self

        def all(self):
            return []

    class FakeDb:
        def execute(self, _statement):
            return Scalar()

    settings = get_settings()
    result = OpportunityCandidateProvider(FakeDb(), settings).list_candidates(
        date(2026, 9, 1), settings.portfolio_config
    )
    assert result.source_status == SourceReadinessStatus.UNAVAILABLE


@pytest.mark.parametrize(
    ("state_codes", "opportunity_codes", "core_ready", "expected", "reason"),
    [
        ({"A", "B"}, {"A", "B"}, True, SourceReadinessStatus.READY, None),
        (
            {"A", "B"},
            {"A"},
            True,
            SourceReadinessStatus.INCOMPLETE,
            "STATE_OPPORTUNITY_SET_MISMATCH",
        ),
        (
            {"A", "B"},
            {"A", "C"},
            True,
            SourceReadinessStatus.INCOMPLETE,
            "STATE_OPPORTUNITY_SET_MISMATCH",
        ),
        (
            set(),
            set(),
            False,
            SourceReadinessStatus.UNAVAILABLE,
            "CURRENT_STATE_AND_OPPORTUNITY_UNAVAILABLE",
        ),
        (
            {"A"},
            {"A"},
            False,
            SourceReadinessStatus.INCOMPLETE,
            "CORE_ANALYSIS_INCOMPLETE",
        ),
    ],
)
def test_candidate_readiness_requires_core_and_exact_sets(
    monkeypatch, state_codes, opportunity_codes, core_ready, expected, reason
) -> None:
    monkeypatch.setattr(
        candidate_module, "is_core_analysis_complete", lambda *a, **k: core_ready
    )
    provider = OpportunityCandidateProvider(object(), get_settings())
    status, actual_reason = provider._source_readiness(
        date(2026, 9, 1),
        state_codes=state_codes,
        opportunity_codes=opportunity_codes,
    )
    assert status == expected
    assert actual_reason == reason


def test_backtest_engine_uses_open_close_after_close_phases() -> None:
    friday = date(2026, 9, 4)
    monday = date(2026, 9, 7)
    tuesday = date(2026, 9, 8)
    candidate = _candidate("A.SZ", "90")
    events = []

    class Calendar:
        def trade_dates(self, start, end):
            return [friday, monday]

        def next_trade_date(self, day):
            return {friday: monday, monday: tuesday}[day]

    class Candidates:
        def list_candidates(self, requested, config):
            events.append(("candidates", requested))
            return CandidateBatch(
                requested,
                (candidate,),
                SourceReadinessStatus.READY,
                None,
                1,
                1,
            )

    class Resolver:
        def resolve(self, intents, market, account, config):
            events.append(("execute", account.trade_date, tuple(intents)))
            return tuple(
                ExecutionDecision(
                    status="REJECTED",
                    executable=False,
                    fill_quantity=0,
                    fill_price=None,
                    reason_code="NO_MARKET_DATA",
                    intent=intent,
                )
                for intent in intents
            )

    class Ledger:
        def __init__(self):
            self.pending = []

        def account_state(self, requested):
            return AccountState(requested, Decimal("100"))

        def pending_order_intents(self, requested):
            return tuple(
                intent
                for intent in self.pending
                if intent.scheduled_trade_date == requested
            )

        def market_snapshot(self, requested, intents):
            return ()

        def apply_execution(self, requested, decisions):
            events.append(("apply", requested, tuple(decisions)))

        def mark_to_market(self, requested):
            events.append(("mark", requested))
            return DailyPortfolioSnapshot(
                trade_date=requested,
                cash=Decimal("100"),
                total_assets=Decimal("100"),
                nav=Decimal("1"),
                positions=(),
            )

        def create_order_intents(self, target, account, scheduled_trade_date):
            intents = (
                OrderIntent(
                    signal_trade_date=target.signal_trade_date,
                    scheduled_trade_date=scheduled_trade_date,
                    ts_code=target.targets[0].ts_code,
                    side="BUY",
                    order_type="NEXT_OPEN",
                    target_weight=target.targets[0].target_weight,
                ),
            )
            self.pending.extend(intents)
            events.append(("create", target.signal_trade_date, scheduled_trade_date))
            return intents

    settings = get_settings()
    ledger = Ledger()
    result = BacktestEngine(
        calendar=Calendar(),
        candidates=Candidates(),
        policy=TopNEqualWeightPolicy(),
        execution=Resolver(),
        ledger=ledger,
        portfolio_config=settings.portfolio_config,
        execution_config=settings.execution_config,
    ).run(friday, monday)
    assert len(result) == 2
    executions = [event for event in events if event[0] == "execute"]
    assert executions[0] == ("execute", friday, ())
    assert executions[1][1] == monday
    assert executions[1][2][0].signal_trade_date == friday
    assert executions[1][2][0].scheduled_trade_date == monday
    assert ("create", friday, monday) in events
    assert ("create", monday, tuesday) in events
    assert all(event[1] != tuesday for event in executions)
    for day in (friday, monday):
        assert events.index(("mark", day)) < events.index(("candidates", day))


def test_backtest_engine_fails_closed_when_source_is_not_ready() -> None:
    day = date(2026, 9, 1)

    class Calendar:
        def trade_dates(self, start, end):
            return [day]

        def next_trade_date(self, requested):
            return date(2026, 9, 2)

    class Candidates:
        def list_candidates(self, requested, config):
            return CandidateBatch(
                requested,
                (),
                SourceReadinessStatus.INCOMPLETE,
                "CORE_ANALYSIS_INCOMPLETE",
                1,
                1,
            )

    class Resolver:
        def resolve(self, intents, market, account, config):
            return ()

    class Ledger:
        def account_state(self, requested):
            return AccountState(requested, Decimal("100"))

        def pending_order_intents(self, requested):
            return ()

        def market_snapshot(self, requested, intents):
            return ()

        def apply_execution(self, requested, decisions):
            return None

        def mark_to_market(self, requested):
            return DailyPortfolioSnapshot(
                requested, Decimal("100"), Decimal("100"), Decimal("1"), ()
            )

        def create_order_intents(self, target, account, scheduled_trade_date):
            raise AssertionError("not-ready source must not create orders")

    settings = get_settings()
    engine = BacktestEngine(
        calendar=Calendar(),
        candidates=Candidates(),
        policy=TopNEqualWeightPolicy(),
        execution=Resolver(),
        ledger=Ledger(),
        portfolio_config=settings.portfolio_config,
        execution_config=settings.execution_config,
    )
    with pytest.raises(PortfolioSourceNotReadyError):
        engine.run(day, day)


def test_domain_module_has_no_sqlalchemy_dependency() -> None:
    import app.domain.portfolio as domain_module

    assert "sqlalchemy" not in domain_module.__dict__


def test_0030_migration_rejects_historical_cross_run_fills(monkeypatch) -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260929_0030_m13_1_1_portfolio_integrity.py"
    )
    spec = importlib.util.spec_from_file_location("m13_1_1_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class Connection:
        def scalar(self, _statement):
            return 2

    monkeypatch.setattr(migration.op, "get_bind", lambda: Connection())
    with pytest.raises(RuntimeError, match="2 historical cross-run fill"):
        migration.upgrade()
