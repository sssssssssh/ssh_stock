from typing import Any

from app.core.config import get_settings
from app.models.market_data import StockOpportunityDaily, ThemeFactorDaily
from app.services.analysis_identity import (
    OPPORTUNITY_CALC_VERSION,
    THEME_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash


def theme_factor_identity_filters(
    settings: Any | None = None,
    *,
    strategy_hash: str | None = None,
    opportunity_hash: str | None = None,
) -> tuple[Any, ...]:
    settings = settings or get_settings()
    return (
        ThemeFactorDaily.calc_version == THEME_CALC_VERSION,
        ThemeFactorDaily.config_hash
        == (opportunity_hash or config_hash(settings.opportunity_config)),
        ThemeFactorDaily.source_strategy_config_hash
        == (strategy_hash or analysis_strategy_hash(settings.strategy)),
    )


def opportunity_identity_filters(
    settings: Any | None = None,
    *,
    algo_version: str | None = None,
    strategy_hash: str | None = None,
    opportunity_hash: str | None = None,
) -> tuple[Any, ...]:
    settings = settings or get_settings()
    return (
        StockOpportunityDaily.algo_version == (algo_version or settings.algo_version),
        StockOpportunityDaily.calc_version == OPPORTUNITY_CALC_VERSION,
        StockOpportunityDaily.config_hash
        == (opportunity_hash or config_hash(settings.opportunity_config)),
        StockOpportunityDaily.source_strategy_config_hash
        == (strategy_hash or analysis_strategy_hash(settings.strategy)),
    )
