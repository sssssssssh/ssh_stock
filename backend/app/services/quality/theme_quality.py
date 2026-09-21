from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market_data import DataQualityDaily, Theme, ThemeDaily


def expected_theme_codes_on_date(db: Session, trade_date: date) -> set[str]:
    return set(
        db.execute(
            select(Theme.theme_code).where(
                Theme.source == "THS",
                Theme.theme_type == "CONCEPT",
                (Theme.list_date.is_(None)) | (Theme.list_date <= trade_date),
                (Theme.first_seen_date.is_(None)) | (Theme.first_seen_date <= trade_date),
                Theme.last_seen_date >= trade_date,
            )
        )
        .scalars()
        .all()
    )


def theme_raw_needs_repair(db: Session, trade_date: date) -> bool:
    quality = db.execute(
        select(
            DataQualityDaily.status,
            DataQualityDaily.expected_rows,
            DataQualityDaily.coverage_rate,
        ).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == "ths_theme_daily",
        )
    ).first()
    if quality is None:
        return True
    if quality.status == "PERMISSION_UNAVAILABLE":
        return False
    if quality.status not in {"PASS", "WARNING"}:
        return True
    actual_rows = db.execute(
        select(func.count()).select_from(ThemeDaily).where(ThemeDaily.trade_date == trade_date)
    ).scalar_one()
    expected_present = round(
        int(quality.expected_rows or 0) * float(quality.coverage_rate or 0)
    )
    return int(actual_rows) < expected_present


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


def required_theme_snapshot_dates(db: Session, start: date, end: date) -> list[date]:
    prior = db.execute(
        select(func.max(DataQualityDaily.trade_date)).where(
            DataQualityDaily.trade_date < start,
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
            DataQualityDaily.status == "PASS",
        )
    ).scalar_one_or_none()
    dates = list(
        db.execute(
            select(DataQualityDaily.trade_date)
            .where(
                DataQualityDaily.trade_date >= start,
                DataQualityDaily.trade_date <= end,
                DataQualityDaily.dataset == "ths_theme_member_snapshot",
                DataQualityDaily.status == "PASS",
            )
            .order_by(DataQualityDaily.trade_date)
        )
        .scalars()
        .all()
    )
    if prior is not None:
        dates.insert(0, prior)
    return dates
