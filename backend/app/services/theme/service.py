import uuid
from datetime import date, timedelta
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    DataQualityDaily,
    IndexDaily,
    StockFactorDaily,
    ThemeDaily,
    ThemeFactorDaily,
    ThemeLimitDaily,
    ThemeMemberSnapshot,
    ThemeMoneyflowDaily,
)
from app.repositories.replace_slice import replace_slice_rows
from app.services.analysis_identity import FACTOR_CALC_VERSION, THEME_CALC_VERSION
from app.services.calc_metadata import calculation_metadata, config_hash
from app.services.theme.engine import ThemeConfig, calculate_theme_factors


class ThemeFactorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def recalc(self, start: date, end: date, calc_run_id: uuid.UUID | None = None) -> int:
        lookback_start = start - timedelta(days=150)
        rows = calculate_theme_factors(
            theme_daily=self._frame(ThemeDaily, lookback_start, end),
            members=self._members(end),
            factors=self._factors(lookback_start, end),
            index_daily=self._frame(IndexDaily, lookback_start, end),
            moneyflow=self._frame(ThemeMoneyflowDaily, lookback_start, end),
            limits=self._frame(ThemeLimitDaily, lookback_start, end),
            valid_snapshots=self._pass_dates("ths_theme_member_snapshot", end),
            moneyflow_pass_dates=self._pass_dates("ths_theme_moneyflow", end),
            limit_pass_dates=self._pass_dates("ths_theme_limit", end),
            start=start,
            end=end,
            config=ThemeConfig.from_configs(
                self.settings.strategy, self.settings.opportunity_config
            ),
        )
        metadata = calculation_metadata(
            config=self.settings.opportunity_config,
            calc_version=THEME_CALC_VERSION,
            calc_run_id=calc_run_id,
        )
        payload = [{**_clean(row), **metadata} for row in rows.to_dict("records")]
        count = replace_slice_rows(
            self.db,
            ThemeFactorDaily,
            payload,
            scope_filters=[
                ThemeFactorDaily.trade_date >= start,
                ThemeFactorDaily.trade_date <= end,
            ],
            key_columns=["trade_date", "theme_code"],
        )
        self.db.commit()
        logger.info("recalculated theme factors start={} end={} rows={}", start, end, count)
        return count

    def _frame(self, model: type, start: date, end: date) -> pd.DataFrame:
        rows = (
            self.db.execute(
                select(model)
                .where(model.trade_date >= start, model.trade_date <= end)
                .order_by(model.trade_date)
            )
            .scalars()
            .all()
        )
        return pd.DataFrame(
            [
                {column.name: getattr(row, column.name) for column in model.__table__.columns}
                for row in rows
            ]
        )

    def _members(self, end: date) -> pd.DataFrame:
        rows = (
            self.db.execute(
                select(ThemeMemberSnapshot).where(ThemeMemberSnapshot.snapshot_date <= end)
            )
            .scalars()
            .all()
        )
        return pd.DataFrame(
            [
                {
                    column.name: getattr(row, column.name)
                    for column in ThemeMemberSnapshot.__table__.columns
                }
                for row in rows
            ]
        )

    def _factors(self, start: date, end: date) -> pd.DataFrame:
        hash_value = config_hash(self.settings.strategy)
        rows = (
            self.db.execute(
                select(StockFactorDaily).where(
                    StockFactorDaily.trade_date >= start,
                    StockFactorDaily.trade_date <= end,
                    StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
                    StockFactorDaily.config_hash == hash_value,
                )
            )
            .scalars()
            .all()
        )
        return pd.DataFrame(
            [
                {
                    column.name: getattr(row, column.name)
                    for column in StockFactorDaily.__table__.columns
                }
                for row in rows
            ]
        )

    def _pass_dates(self, dataset: str, end: date) -> set[date]:
        return set(
            self.db.execute(
                select(DataQualityDaily.trade_date).where(
                    DataQualityDaily.trade_date <= end,
                    DataQualityDaily.dataset == dataset,
                    DataQualityDaily.status == "PASS",
                )
            )
            .scalars()
            .all()
        )


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (None if pd.isna(value) else value.item() if hasattr(value, "item") else value)
        for key, value in row.items()
    }
