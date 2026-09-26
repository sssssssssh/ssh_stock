from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.market_data import SectorFactorDaily, SectorMember, StockFactorDaily
from app.services.analysis_identity import FACTOR_CALC_VERSION, SECTOR_CALC_VERSION


@dataclass(frozen=True)
class SectorCoverageResult:
    expected_count: int
    actual_count: int
    matched_count: int
    missing_count: int
    extra_count: int
    coverage_rate: float | None
    status: str
    missing_sector_ids: tuple[int, ...] = ()
    extra_sector_ids: tuple[int, ...] = ()


def check_sector_factor_coverage(
    db: Session,
    trade_date: date,
    *,
    strategy: dict[str, Any],
    strategy_hash: str,
) -> SectorCoverageResult:
    expected_ids = set(
        db.execute(
            select(SectorMember.sector_id)
            .join(
                StockFactorDaily,
                and_(
                    StockFactorDaily.ts_code == SectorMember.ts_code,
                    StockFactorDaily.trade_date == trade_date,
                    StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
                    StockFactorDaily.config_hash == strategy_hash,
                    StockFactorDaily.eligible.is_(True),
                ),
            )
            .where(
                SectorMember.valid_from <= trade_date,
                (SectorMember.valid_to.is_(None) | (SectorMember.valid_to >= trade_date)),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    actual_ids = set(
        db.execute(
            select(SectorFactorDaily.sector_id)
            .where(
                SectorFactorDaily.trade_date == trade_date,
                SectorFactorDaily.calc_version == SECTOR_CALC_VERSION,
                SectorFactorDaily.config_hash == strategy_hash,
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    matched_ids = expected_ids & actual_ids
    missing_ids = expected_ids - actual_ids
    extra_ids = actual_ids - expected_ids
    if not expected_ids:
        coverage_rate = None
        status = "ERROR"
    else:
        coverage_rate = len(matched_ids) / len(expected_ids)
        thresholds = (
            strategy.get("data_quality", {})
            .get("cross_table", {})
            .get("sector_factor_vs_expected", {})
        )
        warning_rate = float(thresholds.get("warning_coverage_rate", 0.98))
        error_rate = float(thresholds.get("error_coverage_rate", 0.90))
        if coverage_rate < error_rate:
            status = "ERROR"
        elif coverage_rate < warning_rate:
            status = "WARNING"
        else:
            status = "PASS"
    return SectorCoverageResult(
        expected_count=len(expected_ids),
        actual_count=len(actual_ids),
        matched_count=len(matched_ids),
        missing_count=len(missing_ids),
        extra_count=len(extra_ids),
        coverage_rate=coverage_rate,
        status=status,
        missing_sector_ids=tuple(sorted(missing_ids)),
        extra_sector_ids=tuple(sorted(extra_ids)),
    )
