from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import DataQualityDaily


def latest_valid_theme_member_snapshot(db: Session, trade_date: date) -> date | None:
    return db.execute(
        select(func.max(DataQualityDaily.trade_date)).where(
            DataQualityDaily.trade_date <= trade_date,
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
            DataQualityDaily.status == "PASS",
        )
    ).scalar_one_or_none()


def theme_source_status(db: Session, trade_date: date, dataset: str) -> str | None:
    return db.execute(
        select(DataQualityDaily.status).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == dataset,
        )
    ).scalar_one_or_none()
