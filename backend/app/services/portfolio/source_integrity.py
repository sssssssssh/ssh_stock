from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.market_data import (
    StockDaily,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
)
from app.services.analysis_filters import opportunity_identity_filters
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.portfolio.contracts import SourceReadinessStatus
from app.services.quality.analysis_readiness import is_core_analysis_complete
from app.services.quality.daily_quality import expected_stock_daily_codes

_SAMPLE_LIMIT = 20


@dataclass(frozen=True)
class PortfolioSourceIntegrityResult:
    trade_date: date
    status: SourceReadinessStatus
    reason: str | None
    expected_count: int
    stock_daily_count: int
    factor_count: int
    state_count: int
    opportunity_count: int
    mismatch_layers: tuple[str, ...]
    missing_code_samples: dict[str, tuple[str, ...]]
    extra_code_samples: dict[str, tuple[str, ...]]

    @property
    def is_ready(self) -> bool:
        return self.status == SourceReadinessStatus.READY


def check_portfolio_source_integrity(
    db: Session,
    trade_date: date,
    *,
    settings: Settings,
) -> PortfolioSourceIntegrityResult:
    strategy_hash = analysis_strategy_hash(settings.strategy)
    expected_codes = expected_stock_daily_codes(db, trade_date)
    stock_daily_codes = _code_set(
        db,
        select(StockDaily.ts_code).where(StockDaily.trade_date == trade_date),
    )
    factor_codes = _code_set(
        db,
        select(StockFactorDaily.ts_code).where(
            StockFactorDaily.trade_date == trade_date,
            StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
            StockFactorDaily.config_hash == strategy_hash,
        ),
    )
    state_codes = _code_set(
        db,
        select(StockStateDaily.ts_code).where(
            StockStateDaily.trade_date == trade_date,
            StockStateDaily.algo_version == settings.algo_version,
            StockStateDaily.calc_version == TREND_CALC_VERSION,
            StockStateDaily.config_hash == strategy_hash,
        ),
    )
    opportunity_codes = _code_set(
        db,
        select(StockOpportunityDaily.ts_code).where(
            StockOpportunityDaily.trade_date == trade_date,
            *opportunity_identity_filters(settings),
        ),
    )
    all_empty = not any(
        (
            expected_codes,
            stock_daily_codes,
            factor_codes,
            state_codes,
            opportunity_codes,
        )
    )
    context_ready = False
    if not all_empty:
        context_ready = is_core_analysis_complete(
            db,
            trade_date,
            strategy=settings.strategy,
            algo_version=settings.algo_version,
        )
    return evaluate_portfolio_source_integrity(
        trade_date,
        expected_codes=expected_codes,
        stock_daily_codes=stock_daily_codes,
        factor_codes=factor_codes,
        state_codes=state_codes,
        opportunity_codes=opportunity_codes,
        context_ready=context_ready,
    )


def evaluate_portfolio_source_integrity(
    trade_date: date,
    *,
    expected_codes: set[str],
    stock_daily_codes: set[str],
    factor_codes: set[str],
    state_codes: set[str],
    opportunity_codes: set[str],
    context_ready: bool,
) -> PortfolioSourceIntegrityResult:
    code_sets = (
        expected_codes,
        stock_daily_codes,
        factor_codes,
        state_codes,
        opportunity_codes,
    )
    counts = tuple(len(codes) for codes in code_sets)
    if not any(code_sets):
        return PortfolioSourceIntegrityResult(
            trade_date=trade_date,
            status=SourceReadinessStatus.UNAVAILABLE,
            reason="CURRENT_PORTFOLIO_SOURCE_UNAVAILABLE",
            expected_count=0,
            stock_daily_count=0,
            factor_count=0,
            state_count=0,
            opportunity_count=0,
            mismatch_layers=(),
            missing_code_samples={},
            extra_code_samples={},
        )

    comparisons = (
        (
            "stock_daily",
            expected_codes,
            stock_daily_codes,
            "RAW_UNIVERSE_SET_MISMATCH",
        ),
        ("factor", stock_daily_codes, factor_codes, "RAW_FACTOR_SET_MISMATCH"),
        ("state", factor_codes, state_codes, "FACTOR_STATE_SET_MISMATCH"),
        (
            "opportunity",
            state_codes,
            opportunity_codes,
            "STATE_OPPORTUNITY_SET_MISMATCH",
        ),
    )
    mismatch_layers: list[str] = []
    reasons: list[str] = []
    missing_samples: dict[str, tuple[str, ...]] = {}
    extra_samples: dict[str, tuple[str, ...]] = {}

    if not expected_codes:
        mismatch_layers.append("expected_universe")
        reasons.append("EXPECTED_UNIVERSE_UNAVAILABLE_OR_MISMATCH")
    for layer, expected, actual, reason in comparisons:
        if expected == actual:
            continue
        mismatch_layers.append(layer)
        reasons.append(reason)
        missing = tuple(sorted(expected - actual)[:_SAMPLE_LIMIT])
        extra = tuple(sorted(actual - expected)[:_SAMPLE_LIMIT])
        if missing:
            missing_samples[layer] = missing
        if extra:
            extra_samples[layer] = extra
    if not context_ready:
        mismatch_layers.append("core_context")
        reasons.append("CORE_CONTEXT_INCOMPLETE")

    status = (
        SourceReadinessStatus.INCOMPLETE
        if reasons
        else SourceReadinessStatus.READY
    )
    return PortfolioSourceIntegrityResult(
        trade_date=trade_date,
        status=status,
        reason=reasons[0] if reasons else None,
        expected_count=counts[0],
        stock_daily_count=counts[1],
        factor_count=counts[2],
        state_count=counts[3],
        opportunity_count=counts[4],
        mismatch_layers=tuple(mismatch_layers),
        missing_code_samples=missing_samples,
        extra_code_samples=extra_samples,
    )


def _code_set(db: Session, statement) -> set[str]:
    return set(db.execute(statement).scalars().all())
