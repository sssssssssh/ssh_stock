from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.portfolio_config import PortfolioConfig
from app.domain.portfolio import CandidateSourceIdentity, SignalCandidate
from app.models.market_data import StockOpportunityDaily
from app.services.analysis_filters import opportunity_identity_filters
from app.services.portfolio.contracts import CandidateBatch
from app.services.portfolio.source_integrity import check_portfolio_source_integrity


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
        integrity = check_portfolio_source_integrity(
            self.db,
            trade_date,
            settings=self.settings,
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
            source_status=integrity.status,
            source_reason=integrity.reason,
            expected_count=integrity.expected_count,
            stock_daily_count=integrity.stock_daily_count,
            factor_count=integrity.factor_count,
            state_count=integrity.state_count,
            opportunity_count=integrity.opportunity_count,
            mismatch_layers=integrity.mismatch_layers,
            missing_code_samples=integrity.missing_code_samples,
            extra_code_samples=integrity.extra_code_samples,
        )


def _reason_codes(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted(str(key) for key, enabled in value.items() if enabled))
    return ()
