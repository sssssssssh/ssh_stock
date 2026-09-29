from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.portfolio_config import PortfolioConfig
from app.domain.portfolio import CandidateSourceIdentity, SignalCandidate
from app.models.market_data import StockOpportunityDaily, StockStateDaily
from app.services.analysis_filters import opportunity_identity_filters
from app.services.analysis_identity import TREND_CALC_VERSION, analysis_strategy_hash
from app.services.portfolio.contracts import CandidateBatch, SourceReadinessStatus
from app.services.quality.analysis_readiness import is_core_analysis_complete


class OpportunityCandidateProvider:
    """Read-only adapter over the current StockOpportunityDaily identity."""

    _RANKING_FIELDS = {"opportunity_score": StockOpportunityDaily.opportunity_score}

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def list_candidates(self, trade_date: date, config: PortfolioConfig) -> CandidateBatch:
        ranking_column = self._RANKING_FIELDS.get(config.candidate.ranking_field)
        if ranking_column is None:
            raise ValueError("unsupported portfolio candidate ranking field")
        identity = opportunity_identity_filters(self.settings)
        strategy_hash = analysis_strategy_hash(self.settings.strategy)
        state_codes = set(
            self.db.execute(
                select(StockStateDaily.ts_code).where(
                    StockStateDaily.trade_date == trade_date,
                    StockStateDaily.algo_version == self.settings.algo_version,
                    StockStateDaily.calc_version == TREND_CALC_VERSION,
                    StockStateDaily.config_hash == strategy_hash,
                )
            )
            .scalars()
            .all()
        )
        opportunity_codes = set(
            self.db.execute(
                select(StockOpportunityDaily.ts_code).where(
                    StockOpportunityDaily.trade_date == trade_date,
                    *identity,
                )
            )
            .scalars()
            .all()
        )
        source_status, source_reason = self._source_readiness(
            trade_date,
            state_codes=state_codes,
            opportunity_codes=opportunity_codes,
        )
        rows = (
            self.db.execute(
                select(StockOpportunityDaily)
                .where(
                    StockOpportunityDaily.trade_date == trade_date,
                    *identity,
                    StockOpportunityDaily.opportunity_stage.in_(
                        config.candidate.allowed_stages
                    ),
                    ranking_column >= config.candidate.min_score,
                )
                .order_by(ranking_column.desc(), StockOpportunityDaily.ts_code.asc())
            )
            .scalars()
            .all()
        )
        candidates = tuple(
            SignalCandidate(
                trade_date=row.trade_date,
                ts_code=row.ts_code,
                stage=row.opportunity_stage,
                state=row.state,
                score=Decimal(str(getattr(row, config.candidate.ranking_field))),
                rank_score=Decimal(
                    str(row.trend_rank_score)
                    if row.trend_rank_score is not None
                    else str(getattr(row, config.candidate.ranking_field))
                ),
                extension_risk=row.extension_risk,
                industry_sector_id=row.industry_sector_id,
                primary_theme_code=row.primary_theme_code,
                source_identity=CandidateSourceIdentity(
                    algo_version=row.algo_version,
                    opportunity_calc_version=row.calc_version,
                    opportunity_config_hash=row.config_hash,
                    source_strategy_config_hash=row.source_strategy_config_hash,
                ),
                reason_codes=_reason_codes(row.reason_codes),
            )
            for row in rows
        )
        return CandidateBatch(
            trade_date=trade_date,
            candidates=candidates,
            source_status=source_status,
            source_reason=source_reason,
            state_count=len(state_codes),
            opportunity_count=len(opportunity_codes),
        )

    def _source_readiness(
        self,
        trade_date: date,
        *,
        state_codes: set[str],
        opportunity_codes: set[str],
    ) -> tuple[SourceReadinessStatus, str | None]:
        if not state_codes and not opportunity_codes:
            return (
                SourceReadinessStatus.UNAVAILABLE,
                "CURRENT_STATE_AND_OPPORTUNITY_UNAVAILABLE",
            )
        if not is_core_analysis_complete(
            self.db,
            trade_date,
            strategy=self.settings.strategy,
            algo_version=self.settings.algo_version,
        ):
            return SourceReadinessStatus.INCOMPLETE, "CORE_ANALYSIS_INCOMPLETE"
        if not state_codes:
            return SourceReadinessStatus.INCOMPLETE, "CURRENT_STATE_UNAVAILABLE"
        if not opportunity_codes:
            return SourceReadinessStatus.INCOMPLETE, "CURRENT_OPPORTUNITY_UNAVAILABLE"
        if state_codes != opportunity_codes:
            return SourceReadinessStatus.INCOMPLETE, "STATE_OPPORTUNITY_SET_MISMATCH"
        return SourceReadinessStatus.READY, None


def _reason_codes(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted(str(key) for key, enabled in value.items() if enabled))
    return ()
