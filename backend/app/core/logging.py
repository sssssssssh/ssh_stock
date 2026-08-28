import sys

from loguru import logger

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level.upper(),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )

