from datetime import date

import pandas as pd
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    DataQualityDaily,
    Theme,
    ThemeDaily,
    ThemeFactorDaily,
    ThemeMemberInterval,
    ThemeMemberSnapshot,
)


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
    expected_present = round(int(quality.expected_rows or 0) * float(quality.coverage_rate or 0))
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


def theme_factor_member_snapshot(
    db: Session,
    trade_date: date,
    *,
    calc_version: str,
    config_hash: str,
    theme_code: str | None = None,
) -> date | None:
    filters = [
        ThemeFactorDaily.trade_date == trade_date,
        ThemeFactorDaily.calc_version == calc_version,
        ThemeFactorDaily.config_hash == config_hash,
    ]
    if theme_code is not None:
        filters.append(ThemeFactorDaily.theme_code == theme_code)
    return db.execute(
        select(ThemeFactorDaily.member_snapshot_date)
        .where(*filters, ThemeFactorDaily.member_snapshot_date.is_not(None))
        .order_by(ThemeFactorDaily.member_snapshot_date.desc())
        .limit(1)
    ).scalar_one_or_none()


def theme_member_snapshot_meta(db: Session, snapshot_date: date | None) -> dict[str, object]:
    if snapshot_date is None:
        return {
            "member_snapshot_date": None,
            "member_snapshot_status": None,
            "member_snapshot_coverage": None,
            "member_snapshot_mode": None,
        }
    quality = db.execute(
        select(DataQualityDaily.status, DataQualityDaily.coverage_rate).where(
            DataQualityDaily.trade_date == snapshot_date,
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
        )
    ).first()
    status = str(quality.status) if quality else None
    return {
        "member_snapshot_date": snapshot_date.isoformat(),
        "member_snapshot_status": status,
        "member_snapshot_coverage": float(quality.coverage_rate)
        if quality and quality.coverage_rate is not None
        else None,
        "member_snapshot_mode": {"PASS": "FULL", "WARNING": "PARTIAL"}.get(status),
    }


def theme_source_status(db: Session, trade_date: date, dataset: str) -> str | None:
    return db.execute(
        select(DataQualityDaily.status).where(
            DataQualityDaily.trade_date == trade_date,
            DataQualityDaily.dataset == dataset,
        )
    ).scalar_one_or_none()


def historical_theme_members(
    db: Session, trade_dates: list[date]
) -> tuple[pd.DataFrame, set[date], dict[date, dict[str, object]]]:
    dates = sorted(set(trade_dates))
    if not dates:
        return pd.DataFrame(), set(), {}
    interval_rows = (
        db.execute(
            select(ThemeMemberInterval).where(
                ThemeMemberInterval.quality_flag == "RELIABLE",
                ThemeMemberInterval.valid_from <= dates[-1],
            )
        )
        .scalars()
        .all()
    )
    quality_rows = db.execute(
        select(
            DataQualityDaily.trade_date,
            DataQualityDaily.status,
            DataQualityDaily.coverage_rate,
        ).where(
            DataQualityDaily.trade_date <= dates[-1],
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
            _member_snapshot_status_filter(False),
        )
    ).all()
    quality = {
        row.trade_date: (row.status, row.coverage_rate) for row in quality_rows
    }
    snapshots = (
        db.execute(
            select(ThemeMemberSnapshot).where(
                ThemeMemberSnapshot.snapshot_date.in_(sorted(quality))
            )
        )
        .scalars()
        .all()
        if quality
        else []
    )
    snapshots_by_date: dict[date, list[ThemeMemberSnapshot]] = {}
    for row in snapshots:
        snapshots_by_date.setdefault(row.snapshot_date, []).append(row)

    payload: list[dict[str, object]] = []
    valid_dates: set[date] = set()
    context: dict[date, dict[str, object]] = {}
    for trade_date in dates:
        known_interval_pairs = {
            (row.theme_code, row.ts_code)
            for row in interval_rows
            if row.valid_from <= trade_date
        }
        active = [
            row
            for row in interval_rows
            if row.valid_from <= trade_date
            and (row.valid_to is None or row.valid_to >= trade_date)
        ]
        available_snapshots = [item for item in quality if item <= trade_date]
        snapshot_date = max(available_snapshots) if available_snapshots else None
        fallback_rows = [
            row
            for row in snapshots_by_date.get(snapshot_date, [])
            if (row.theme_code, row.ts_code) not in known_interval_pairs
        ]
        current_rows = [
            {
                "snapshot_date": trade_date,
                "theme_code": row.theme_code,
                "ts_code": row.ts_code,
                "source": row.source,
            }
            for row in active
        ]
        current_rows.extend(
            {
                "snapshot_date": trade_date,
                "theme_code": row.theme_code,
                "ts_code": row.ts_code,
                "stock_name": row.stock_name,
                "source": row.source,
            }
            for row in fallback_rows
        )
        if not current_rows:
            context[trade_date] = {
                "available": False,
                "coverage": None,
                "mode": "UNAVAILABLE",
            }
            continue
        payload.extend(current_rows)
        valid_dates.add(trade_date)
        if active and fallback_rows:
            mode = "INTERVAL_SNAPSHOT"
        elif active:
            mode = "INTERVAL"
        else:
            mode = "SNAPSHOT"
        context[trade_date] = {
            "available": True,
            "coverage": float(quality[snapshot_date][1])
            if fallback_rows
            and snapshot_date is not None
            and quality[snapshot_date][1] is not None
            else 1.0 if active else None,
            "mode": mode,
        }
        if fallback_rows:
            context[trade_date]["source_snapshot_date"] = snapshot_date
    frame = pd.DataFrame(payload)
    if not frame.empty:
        frame = frame.drop_duplicates(["snapshot_date", "theme_code", "ts_code"])
    return frame, valid_dates, context


def theme_context_availability(
    db: Session, trade_dates: list[date]
) -> dict[date, dict[str, object]]:
    try:
        return historical_theme_members(db, trade_dates)[2]
    except (AttributeError, TypeError):
        return {
            item: {"available": False, "coverage": None, "mode": "UNAVAILABLE"}
            for item in trade_dates
        }


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
