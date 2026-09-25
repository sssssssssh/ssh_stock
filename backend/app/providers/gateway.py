from sqlalchemy.orm import Session

from app.providers.logging_provider import LoggingMarketDataProvider
from app.providers.tushare_provider import TushareProvider


def market_data_gateway(db: Session) -> LoggingMarketDataProvider:
    """Build the common rate-limited Tushare provider with durable call logging."""
    return LoggingMarketDataProvider(db, TushareProvider())
