from collections.abc import Callable
from datetime import date
from time import perf_counter
from typing import TypeVar

import pandas as pd
from sqlalchemy.orm import Session

from app.providers.base import MarketDataProvider
from app.repositories.job_run import log_provider_call

T = TypeVar("T")


class LoggingMarketDataProvider:
    def __init__(
        self, db: Session, inner: MarketDataProvider, provider_name: str = "tushare"
    ) -> None:
        self.db = db
        self.inner = inner
        self.provider_name = provider_name

    def _logged(
        self,
        api_name: str,
        trade_date: date | None,
        fn: Callable[..., pd.DataFrame],
        *args: object,
        **kwargs: object,
    ) -> pd.DataFrame:
        started = perf_counter()
        try:
            df = fn(*args, **kwargs)
        except Exception as exc:
            elapsed_ms = int((perf_counter() - started) * 1000)
            log_provider_call(
                self.db,
                provider=self.provider_name,
                api_name=api_name,
                trade_date=trade_date,
                elapsed_ms=elapsed_ms,
                row_count=None,
                status="FAILED",
                error_type=type(exc).__name__,
            )
            self.db.commit()
            raise

        elapsed_ms = int((perf_counter() - started) * 1000)
        log_provider_call(
            self.db,
            provider=self.provider_name,
            api_name=api_name,
            trade_date=trade_date,
            elapsed_ms=elapsed_ms,
            row_count=len(df.index),
            status="SUCCESS",
        )
        self.db.commit()
        return df

    def get_trade_calendar(self, start: date, end: date) -> pd.DataFrame:
        return self._logged("trade_cal", None, self.inner.get_trade_calendar, start, end)

    def get_stock_basic(self) -> pd.DataFrame:
        return self._logged("stock_basic", None, self.inner.get_stock_basic)

    def get_daily(self, trade_date: date) -> pd.DataFrame:
        return self._logged("daily", trade_date, self.inner.get_daily, trade_date)

    def get_adj_factor(self, trade_date: date) -> pd.DataFrame:
        return self._logged("adj_factor", trade_date, self.inner.get_adj_factor, trade_date)

    def get_daily_basic(self, trade_date: date) -> pd.DataFrame:
        return self._logged("daily_basic", trade_date, self.inner.get_daily_basic, trade_date)

    def get_index_daily(self, trade_date: date, codes: list[str]) -> pd.DataFrame:
        return self._logged(
            "index_daily", trade_date, self.inner.get_index_daily, trade_date, codes
        )

    def get_sector_classification(self) -> pd.DataFrame:
        return self._logged("index_classify", None, self.inner.get_sector_classification)

    def get_sector_members(self) -> pd.DataFrame:
        return self._logged("index_member_all", None, self.inner.get_sector_members)
