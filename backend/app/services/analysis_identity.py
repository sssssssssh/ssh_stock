from dataclasses import dataclass

from app.core.config import get_settings
from app.services.calc_metadata import config_hash

FACTOR_CALC_VERSION = "factor_v1"
MARKET_CALC_VERSION = "market_v1"
SECTOR_CALC_VERSION = "sector_v1"
TREND_CALC_VERSION = "trend_v1"
SIGNAL_CALC_VERSION = "signal_v1"
TRADE_STATUS_CALC_VERSION = "trade_status_v1"
THEME_CALC_VERSION = "theme_v1"
OPPORTUNITY_CALC_VERSION = "opportunity_v1"


@dataclass(frozen=True)
class AnalysisIdentity:
    algo_version: str
    config_hash: str


def current_analysis_identity() -> AnalysisIdentity:
    settings = get_settings()
    return AnalysisIdentity(
        algo_version=settings.algo_version,
        config_hash=config_hash(settings.strategy),
    )
