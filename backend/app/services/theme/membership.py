from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.market_data import (
    DataQualityDaily,
    ThemeMemberInterval,
    ThemeMemberSnapshot,
)


@dataclass(frozen=True)
class ThemeMembershipResolution:
    members: pd.DataFrame
    available_dates: set[date]
    context_by_date: dict[date, dict[str, object]]


MEMBER_COLUMNS = (
    "trade_date",
    "theme_code",
    "ts_code",
    "stock_name",
    "source",
    "membership_source",
)


def resolve_theme_memberships(
    db: Session,
    trade_dates: list[date],
) -> ThemeMembershipResolution:
    dates = sorted(set(trade_dates))
    if not dates:
        return ThemeMembershipResolution(
            members=pd.DataFrame(columns=MEMBER_COLUMNS),
            available_dates=set(),
            context_by_date={},
        )

    intervals = list(
        db.execute(
            select(ThemeMemberInterval).where(
                ThemeMemberInterval.quality_flag == "RELIABLE",
                ThemeMemberInterval.valid_from <= dates[-1],
                or_(
                    ThemeMemberInterval.valid_to.is_not(None),
                    ThemeMemberInterval.source_is_new.is_(True),
                ),
            )
        )
        .scalars()
        .all()
    )
    threshold = float(
        get_settings()
        .opportunity_config.get("theme_quality", {})
        .get("member_snapshot", {})
        .get("error_coverage_rate", 0.90)
    )
    quality_rows = db.execute(
        select(
            DataQualityDaily.trade_date,
            DataQualityDaily.status,
            DataQualityDaily.coverage_rate,
        ).where(
            DataQualityDaily.trade_date <= dates[-1],
            DataQualityDaily.dataset == "ths_theme_member_snapshot",
            or_(
                DataQualityDaily.status == "PASS",
                and_(
                    DataQualityDaily.status == "WARNING",
                    DataQualityDaily.coverage_rate >= threshold,
                ),
            ),
        )
    ).all()
    quality = {
        row.trade_date: {"status": row.status, "coverage": row.coverage_rate}
        for row in quality_rows
    }
    selected_snapshot_dates = {
        max(usable)
        for current in dates
        if (usable := [snapshot for snapshot in quality if snapshot <= current])
    }
    snapshots = (
        list(
            db.execute(
                select(ThemeMemberSnapshot).where(
                    ThemeMemberSnapshot.snapshot_date.in_(selected_snapshot_dates)
                )
            )
            .scalars()
            .all()
        )
        if selected_snapshot_dates
        else []
    )
    snapshots_by_date: dict[date, list[ThemeMemberSnapshot]] = {}
    for row in snapshots:
        snapshots_by_date.setdefault(row.snapshot_date, []).append(row)

    payload: list[dict[str, object]] = []
    available_dates: set[date] = set()
    context_by_date: dict[date, dict[str, object]] = {}
    for current in dates:
        known_interval_pairs = {
            (row.theme_code, row.ts_code)
            for row in intervals
            if row.valid_from <= current
        }
        active_intervals = [
            row
            for row in intervals
            if row.valid_from <= current
            and (row.valid_to is None or row.valid_to >= current)
        ]
        usable_snapshots = [snapshot for snapshot in quality if snapshot <= current]
        snapshot_date = max(usable_snapshots) if usable_snapshots else None
        fallback = [
            row
            for row in snapshots_by_date.get(snapshot_date, [])
            if (row.theme_code, row.ts_code) not in known_interval_pairs
        ]

        payload.extend(
            {
                "trade_date": current,
                "theme_code": row.theme_code,
                "ts_code": row.ts_code,
                "stock_name": None,
                "source": row.source,
                "membership_source": "INTERVAL",
            }
            for row in active_intervals
        )
        payload.extend(
            {
                "trade_date": current,
                "theme_code": row.theme_code,
                "ts_code": row.ts_code,
                "stock_name": row.stock_name,
                "source": row.source,
                "membership_source": "SNAPSHOT",
            }
            for row in fallback
        )

        if active_intervals and fallback:
            mode = "INTERVAL_SNAPSHOT"
        elif active_intervals:
            mode = "INTERVAL"
        elif fallback:
            mode = "SNAPSHOT"
        else:
            mode = "UNAVAILABLE"
        available = mode != "UNAVAILABLE"
        if available:
            available_dates.add(current)
        uses_snapshot = bool(fallback)
        context_by_date[current] = {
            "available": available,
            "coverage": (
                float(quality[snapshot_date]["coverage"])
                if uses_snapshot
                and snapshot_date is not None
                and quality[snapshot_date]["coverage"] is not None
                else 1.0 if active_intervals else None
            ),
            "mode": mode,
            "source_snapshot_date": snapshot_date if uses_snapshot else None,
        }

    members = pd.DataFrame(payload, columns=MEMBER_COLUMNS)
    if not members.empty:
        members = members.drop_duplicates(["trade_date", "theme_code", "ts_code"])
    return ThemeMembershipResolution(members, available_dates, context_by_date)
