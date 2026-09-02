from threading import Lock
from time import perf_counter, sleep

from loguru import logger

_rate_limit_lock = Lock()
_last_call_started_at = 0.0


def wait_for_rate_limit(provider_name: str, api_name: str, min_interval_seconds: float) -> None:
    global _last_call_started_at
    if min_interval_seconds <= 0:
        return

    with _rate_limit_lock:
        now = perf_counter()
        wait_seconds = min_interval_seconds - (now - _last_call_started_at)
        if wait_seconds > 0:
            logger.debug(
                "provider rate limit sleep provider={} api={} seconds={:.2f}",
                provider_name,
                api_name,
                wait_seconds,
            )
            sleep(wait_seconds)
        _last_call_started_at = perf_counter()
