from collections.abc import Callable
from datetime import date
from threading import Lock
from time import perf_counter, sleep
from typing import Any

import pandas as pd
from loguru import logger
from requests.exceptions import RequestException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings


def to_tushare_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _compact_error(exc: Exception, max_length: int = 800) -> str:
    message = " ".join(str(exc).split())
    if len(message) <= max_length:
        return message
    return f"{message[:max_length]}..."


class TushareProvider:
    provider_name = "tushare"

    def __init__(
        self,
        token: str | None = None,
        http_url: str | None = None,
        min_interval_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self._token = (token or settings.tushare_token or "").strip().strip("'\"")
        if not self._token or self._token == "replace_me":
            raise RuntimeError("TUSHARE_TOKEN is required and must be provided by environment")
        self._http_url = (http_url or settings.tushare_http_url or "").strip().strip("'\"")
        configured_interval = (
            settings.tushare_min_interval_seconds
            if min_interval_seconds is None
            else min_interval_seconds
        )
        self._min_interval_seconds = max(0.0, float(configured_interval))
        self._rate_limit_lock = Lock()
        self._last_call_started_at = 0.0

        import tushare as ts

        ts.set_token(self._token)
        self._pro = ts.pro_api()
        if self._http_url:
            self._pro._DataApi__http_url = self._http_url

    def _wait_for_rate_limit(self, api_name: str) -> None:
        if self._min_interval_seconds <= 0:
            return

        with self._rate_limit_lock:
            now = perf_counter()
            wait_seconds = self._min_interval_seconds - (now - self._last_call_started_at)
            if wait_seconds > 0:
                logger.debug(
                    "provider rate limit sleep provider={} api={} seconds={:.2f}",
                    self.provider_name,
                    api_name,
                    wait_seconds,
                )
                sleep(wait_seconds)
            self._last_call_started_at = perf_counter()

    @retry(
        retry=retry_if_exception_type((TimeoutError, ConnectionError, RequestException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10),
        reraise=True,
    )
    def _call(
        self, api_name: str, log_trade_date: date | None = None, **kwargs: Any
    ) -> pd.DataFrame:
        api: Callable[..., pd.DataFrame] = getattr(self._pro, api_name)
        self._wait_for_rate_limit(api_name)
        started = perf_counter()
        try:
            df = api(**kwargs)
        except Exception:
            logger.error(
                "provider call failed provider={} api={} trade_date={}",
                self.provider_name,
                api_name,
                log_trade_date,
            )
            raise
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "provider call provider={} api={} trade_date={} rows={} elapsed_ms={}",
            self.provider_name,
            api_name,
            log_trade_date.isoformat() if log_trade_date else None,
            len(df.index) if df is not None else 0,
            elapsed_ms,
        )
        return df if df is not None else pd.DataFrame()

    def get_trade_calendar(self, start: date, end: date) -> pd.DataFrame:
        return self._call(
            "trade_cal",
            start_date=to_tushare_date(start),
            end_date=to_tushare_date(end),
            exchange="SSE",
        )

    def get_stock_basic(self) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        fetched_statuses: set[str] = set()
        source_errors: dict[str, str] = {}
        fields = (
            "ts_code,symbol,name,area,industry,market,exchange,list_status,"
            "list_date,delist_date,is_hs"
        )
        for status in ("L", "D", "P"):
            try:
                df = self._call("stock_basic", list_status=status, fields=fields)
            except Exception as exc:
                source_errors[status] = _compact_error(exc)
                logger.warning("stock_basic status={} failed: {}", status, exc)
                continue
            if not df.empty:
                frames.append(df)
                fetched_statuses.add(status)
        missing_required = {"L", "D"} - fetched_statuses
        if missing_required:
            details = "; ".join(
                f"{status}: {source_errors.get(status, 'empty response')}"
                for status in sorted(missing_required)
            )
            raise RuntimeError(
                f"stock_basic required statuses missing: {sorted(missing_required)}; "
                f"stock_basic source errors: {details}"
            )
        return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["ts_code"])

    def get_daily(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "daily", log_trade_date=trade_date, trade_date=to_tushare_date(trade_date)
        )

    def get_daily_range(self, ts_code: str, start: date, end: date) -> pd.DataFrame:
        return self._call(
            "daily",
            ts_code=ts_code,
            start_date=to_tushare_date(start),
            end_date=to_tushare_date(end),
        )

    def get_adj_factor(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "adj_factor", log_trade_date=trade_date, trade_date=to_tushare_date(trade_date)
        )

    def get_daily_basic(self, trade_date: date) -> pd.DataFrame:
        return self._call(
            "daily_basic", log_trade_date=trade_date, trade_date=to_tushare_date(trade_date)
        )

    def get_index_daily(self, trade_date: date, codes: list[str]) -> pd.DataFrame:
        frames = [
            self._call(
                "index_daily",
                log_trade_date=trade_date,
                ts_code=code,
                trade_date=to_tushare_date(trade_date),
            )
            for code in codes
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_sector_classification(self) -> pd.DataFrame:
        return self._call("index_classify", src="SW2021")

    def get_sector_members(self) -> pd.DataFrame:
        return self._call("index_member_all", src="SW")
