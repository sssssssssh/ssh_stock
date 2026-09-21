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
    TradeCalendar,
)
from app.repositories.replace_slice import replace_slice_rows
from app.services.analysis_identity import FACTOR_CALC_VERSION, THEME_CALC_VERSION
from app.services.calc_metadata import calculation_metadata, config_hash
from app.services.quality.theme_quality import required_theme_snapshot_dates
from app.services.theme.engine import ThemeConfig, calculate_theme_factors


class ThemeFactorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def recalc(self, start: date, end: date, calc_run_id: uuid.UUID | None = None) -> int:
        lookback_start = start - timedelta(days=150)
        source_quality = self._source_quality(lookback_start, end)
        usable_dates = {
            trade_date
            for trade_date, values in source_quality.items()
            if values["status"] in {"PASS", "WARNING"}
        }
        output_dates = sorted(day for day in usable_dates if start <= day <= end)
        if not output_dates:
            logger.warning(
                "skipped theme factors start={} end={} reason=no usable theme daily quality",
                start,
                end,
            )
            return 0
        theme_daily = self._frame(ThemeDaily, lookback_start, end)
        if not theme_daily.empty:
            theme_daily = theme_daily[theme_daily["trade_date"].isin(usable_dates)]
        snapshot_dates = required_theme_snapshot_dates(self.db, lookback_start, end)
        rows = calculate_theme_factors(
            theme_daily=theme_daily,
            members=self._members(snapshot_dates),
            factors=self._factors(lookback_start, end),
            index_daily=self._frame(IndexDaily, lookback_start, end),
            moneyflow=self._frame(ThemeMoneyflowDaily, lookback_start, end),
            limits=self._frame(ThemeLimitDaily, lookback_start, end),
            valid_snapshots=set(snapshot_dates),
            moneyflow_pass_dates=self._pass_dates("ths_theme_moneyflow", end, allow_empty=False),
            limit_pass_dates=self._pass_dates("ths_theme_limit", end),
            start=start,
            end=end,
            config=ThemeConfig.from_configs(
                self.settings.strategy, self.settings.opportunity_config
            ),
            market_trade_dates=self._open_trade_dates(lookback_start, end),
        )
        metadata = calculation_metadata(
            config=self.settings.opportunity_config,
            calc_version=THEME_CALC_VERSION,
            calc_run_id=calc_run_id,
        )
        payload = []
        for row in rows.to_dict("records"):
            clean_row = _clean(row)
            clean_row["source_coverage"] = source_quality[clean_row["trade_date"]][
                "coverage_rate"
            ]
            payload.append({**clean_row, **metadata})
        count = replace_slice_rows(
            self.db,
            ThemeFactorDaily,
            payload,
            scope_filters=[
                ThemeFactorDaily.trade_date.in_(output_dates),
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

    def _members(self, snapshot_dates: list[date]) -> pd.DataFrame:
        if not snapshot_dates:
            return pd.DataFrame()
        rows = (
            self.db.execute(
                select(ThemeMemberSnapshot).where(
                    ThemeMemberSnapshot.snapshot_date.in_(snapshot_dates)
                )
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

    def _pass_dates(self, dataset: str, end: date, *, allow_empty: bool = True) -> set[date]:
        statuses = ("PASS", "WARNING", "SOURCE_EMPTY") if allow_empty else ("PASS", "WARNING")
        return set(
            self.db.execute(
                select(DataQualityDaily.trade_date).where(
                    DataQualityDaily.trade_date <= end,
                    DataQualityDaily.dataset == dataset,
                    DataQualityDaily.status.in_(statuses),
                )
            )
            .scalars()
            .all()
        )

    def _open_trade_dates(self, start: date, end: date) -> list[date]:
        return list(
            self.db.execute(
                select(TradeCalendar.cal_date)
                .where(
                    TradeCalendar.cal_date >= start,
                    TradeCalendar.cal_date <= end,
                    TradeCalendar.is_open.is_(True),
                )
                .order_by(TradeCalendar.cal_date)
            )
            .scalars()
            .all()
        )

    def _source_quality(self, start: date, end: date) -> dict[date, dict[str, Any]]:
        rows = self.db.execute(
            select(
                DataQualityDaily.trade_date,
                DataQualityDaily.status,
                DataQualityDaily.coverage_rate,
            ).where(
                DataQualityDaily.trade_date >= start,
                DataQualityDaily.trade_date <= end,
                DataQualityDaily.dataset == "ths_theme_daily",
            )
        ).all()
        return {
            row.trade_date: {
                "status": row.status,
                "coverage_rate": row.coverage_rate,
            }
            for row in rows
        }


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (None if pd.isna(value) else value.item() if hasattr(value, "item") else value)
        for key, value in row.items()
    }
