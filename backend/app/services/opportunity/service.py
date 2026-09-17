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
    MarketDaily,
    SectorFactorDaily,
    SectorMember,
    StockFactorDaily,
    StockOpportunityDaily,
    StockStateDaily,
    Theme,
    ThemeFactorDaily,
    ThemeMemberSnapshot,
)
from app.repositories.replace_slice import replace_slice_rows
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    SECTOR_CALC_VERSION,
    THEME_CALC_VERSION,
    TREND_CALC_VERSION,
)
from app.services.calc_metadata import calculation_metadata, config_hash
from app.services.opportunity.engine import OpportunityConfig, calculate_opportunities


class OpportunityService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def recalc(
        self,
        start: date,
        end: date,
        algo_version: str | None = None,
        calc_run_id: uuid.UUID | None = None,
    ) -> int:
        version = algo_version or self.settings.algo_version
        lookback_start = start - timedelta(days=190)
        strategy_hash = config_hash(self.settings.strategy)
        opportunity_hash = config_hash(self.settings.opportunity_config)
        frame = calculate_opportunities(
            factors=self._versioned_frame(
                StockFactorDaily, lookback_start, end, FACTOR_CALC_VERSION, strategy_hash
            ),
            states=self._states(lookback_start, end, version, strategy_hash),
            market=self._versioned_frame(
                MarketDaily, lookback_start, end, MARKET_CALC_VERSION, strategy_hash
            ),
            sector_members=self._all_frame(SectorMember),
            sector_factors=self._versioned_frame(
                SectorFactorDaily, lookback_start, end, SECTOR_CALC_VERSION, strategy_hash
            ),
            themes=self._all_frame(Theme),
            theme_members=self._all_frame(ThemeMemberSnapshot),
            theme_factors=self._versioned_frame(
                ThemeFactorDaily,
                lookback_start,
                end,
                THEME_CALC_VERSION,
                opportunity_hash,
            ),
            valid_snapshots=self._valid_snapshots(end),
            start=start,
            end=end,
            algo_version=version,
            config=OpportunityConfig.from_dict(self.settings.opportunity_config),
        )
        metadata = calculation_metadata(
            config=self.settings.opportunity_config,
            calc_version=OPPORTUNITY_CALC_VERSION,
            calc_run_id=calc_run_id,
        )
        rows = [{**_clean(row), **metadata} for row in frame.to_dict("records")]
        count = replace_slice_rows(
            self.db,
            StockOpportunityDaily,
            rows,
            scope_filters=[
                StockOpportunityDaily.trade_date >= start,
                StockOpportunityDaily.trade_date <= end,
                StockOpportunityDaily.algo_version == version,
            ],
            key_columns=["trade_date", "ts_code", "algo_version"],
        )
        self.db.commit()
        logger.info("recalculated opportunities start={} end={} rows={}", start, end, count)
        return count

    def _versioned_frame(
        self,
        model: type,
        start: date,
        end: date,
        calc_version: str,
        hash_value: str,
    ) -> pd.DataFrame:
        rows = (
            self.db.execute(
                select(model).where(
                    model.trade_date >= start,
                    model.trade_date <= end,
                    model.calc_version == calc_version,
                    model.config_hash == hash_value,
                )
            )
            .scalars()
            .all()
        )
        return _models_frame(rows, model)

    def _states(self, start: date, end: date, algo_version: str, hash_value: str) -> pd.DataFrame:
        rows = (
            self.db.execute(
                select(StockStateDaily).where(
                    StockStateDaily.trade_date >= start,
                    StockStateDaily.trade_date <= end,
                    StockStateDaily.algo_version == algo_version,
                    StockStateDaily.calc_version == TREND_CALC_VERSION,
                    StockStateDaily.config_hash == hash_value,
                )
            )
            .scalars()
            .all()
        )
        return _models_frame(rows, StockStateDaily)

    def _all_frame(self, model: type) -> pd.DataFrame:
        return _models_frame(self.db.execute(select(model)).scalars().all(), model)

    def _valid_snapshots(self, end: date) -> set[date]:
        return set(
            self.db.execute(
                select(DataQualityDaily.trade_date).where(
                    DataQualityDaily.trade_date <= end,
                    DataQualityDaily.dataset == "ths_theme_member_snapshot",
                    DataQualityDaily.status == "PASS",
                )
            )
            .scalars()
            .all()
        )


def _models_frame(rows: list[Any], model: type) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {column.name: getattr(row, column.name) for column in model.__table__.columns}
            for row in rows
        ]
    )


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list)):
            cleaned[key] = value
        elif pd.isna(value):
            cleaned[key] = None
        elif hasattr(value, "item"):
            cleaned[key] = value.item()
        else:
            cleaned[key] = value
    return cleaned
