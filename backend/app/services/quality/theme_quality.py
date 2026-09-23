from datetime import date

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import DataQualityDaily, Theme, ThemeDaily


def expected_theme_codes_on_date(db: Session, trade_date: date) -> set[str]:
    lower_bound = func.coalesce(Theme.list_date, Theme.first_seen_date)
    return set(
        db.execute(
            select(Theme.theme_code).where(
                Theme.source == "THS",
                Theme.theme_type == "CONCEPT",
                or_(lower_bound.is_(None), lower_bound <= trade_date),
                or_(Theme.last_seen_date.is_(None), Theme.last_seen_date >= trade_date),
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


def _member_snapshot_status_filter(strict: bool):
    if strict:
        return DataQualityDaily.status == "PASS"
    threshold = float(
        get_settings()
        .opportunity_config.get("theme_quality", {})
        .get("member_snapshot", {})
        .get("error_coverage_rate", 0.90)
    )
    return or_(
        DataQualityDaily.status == "PASS",
        and_(
            DataQualityDaily.status == "WARNING",
            DataQualityDaily.coverage_rate >= threshold,
        ),
    )


def latest_strict_theme_member_snapshot(db: Session, trade_date: date) -> date | None:
    return db.execute(
        select(func.max(DataQualityDaily.trade_date)).where(
            DataQualityDaily.trade_date <= trade_date,
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
            _member_snapshot_status_filter(True),
        )
    ).scalar_one_or_none()


def latest_usable_theme_member_snapshot(db: Session, trade_date: date) -> date | None:
    return db.execute(
        select(func.max(DataQualityDaily.trade_date)).where(
            DataQualityDaily.trade_date <= trade_date,
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
            _member_snapshot_status_filter(False),
        )
    ).scalar_one_or_none()


def latest_valid_theme_member_snapshot(db: Session, trade_date: date) -> date | None:
    return latest_strict_theme_member_snapshot(db, trade_date)


def theme_source_status(db: Session, trade_date: date, dataset: str) -> str | None:
    return db.execute(
        select(DataQualityDaily.status).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == dataset,
        )
    ).scalar_one_or_none()


def required_theme_snapshot_dates(
    db: Session, start: date, end: date, strict: bool = True
) -> list[date]:
    status_filter = _member_snapshot_status_filter(strict)
    prior = db.execute(
        select(func.max(DataQualityDaily.trade_date)).where(
            DataQualityDaily.trade_date < start,
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
            status_filter,
        )
    ).scalar_one_or_none()
    dates = list(
        db.execute(
            select(DataQualityDaily.trade_date)
            .where(
                DataQualityDaily.trade_date >= start,
                DataQualityDaily.trade_date <= end,
                DataQualityDaily.dataset == "ths_theme_member_snapshot",
                status_filter,
            )
            .order_by(DataQualityDaily.trade_date)
        )
        .scalars()
        .all()
    )
    if prior is not None:
        dates.insert(0, prior)
    return dates


def required_strict_theme_snapshot_dates(db: Session, start: date, end: date) -> list[date]:
    return required_theme_snapshot_dates(db, start, end, True)


def required_usable_theme_snapshot_dates(db: Session, start: date, end: date) -> list[date]:
    return required_theme_snapshot_dates(db, start, end, False)
