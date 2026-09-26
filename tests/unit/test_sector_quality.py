from datetime import date, timedelta

import pytest
from app.core.config import get_settings
from app.models.market_data import SectorFactorDaily, SectorMember, StockFactorDaily
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    SECTOR_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.quality.sector_quality import check_sector_factor_coverage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        StockFactorDaily.__table__,
        SectorMember.__table__,
        SectorFactorDaily.__table__,
    ):
        table.create(engine)
    return Session(engine)


def _seed_expected(
    db: Session,
    day: date,
    strategy_hash: str,
    count: int,
    *,
    eligible_count: int | None = None,
) -> None:
    eligible_count = count if eligible_count is None else eligible_count
    db.execute(
        StockFactorDaily.__table__.insert(),
        [
            {
                "trade_date": day,
                "ts_code": f"{index:06d}.SZ",
                "eligible": index < eligible_count,
                "calc_version": FACTOR_CALC_VERSION,
                "config_hash": strategy_hash,
            }
            for index in range(count)
        ],
    )
    db.execute(
        SectorMember.__table__.insert(),
        [
            {
                "sector_id": index + 1,
                "ts_code": f"{index:06d}.SZ",
                "valid_from": day,
                "is_latest": True,
            }
            for index in range(count)
        ],
    )


def _seed_actual(
    db: Session,
    day: date,
    strategy_hash: str,
    sector_ids: range | list[int],
    *,
    calc_version: str = SECTOR_CALC_VERSION,
) -> None:
    db.execute(
        SectorFactorDaily.__table__.insert(),
        [
            {
                "trade_date": day,
                "sector_id": sector_id,
                "calc_version": calc_version,
                "config_hash": strategy_hash,
            }
            for sector_id in sector_ids
        ],
    )


@pytest.mark.parametrize(
    ("actual_count", "status"),
    ((30, "PASS"), (1, "ERROR"), (29, "WARNING")),
)
def test_sector_coverage_uses_expected_set(actual_count, status) -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 26)
    with _db() as db:
        _seed_expected(db, day, strategy_hash, 30)
        _seed_actual(db, day, strategy_hash, range(1, actual_count + 1))
        db.commit()

        result = check_sector_factor_coverage(
            db, day, strategy=settings.strategy, strategy_hash=strategy_hash
        )

    assert result.expected_count == 30
    assert result.actual_count == actual_count
    assert result.matched_count == actual_count
    assert result.status == status


def test_sector_coverage_fails_closed_for_empty_expected_set() -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 26)
    with _db() as db:
        db.execute(
            StockFactorDaily.__table__.insert(),
            [{
                "trade_date": day,
                "ts_code": "000001.SZ",
                "eligible": True,
                "calc_version": FACTOR_CALC_VERSION,
                "config_hash": strategy_hash,
            }],
        )
        db.commit()
        result = check_sector_factor_coverage(
            db, day, strategy=settings.strategy, strategy_hash=strategy_hash
        )

    assert result.expected_count == 0
    assert result.coverage_rate is None
    assert result.status == "ERROR"


def test_sector_expected_set_only_includes_eligible_members() -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 26)
    with _db() as db:
        _seed_expected(db, day, strategy_hash, 40, eligible_count=30)
        _seed_actual(db, day, strategy_hash, range(1, 31))
        db.commit()
        result = check_sector_factor_coverage(
            db, day, strategy=settings.strategy, strategy_hash=strategy_hash
        )

    assert result.expected_count == 30
    assert result.status == "PASS"


def test_sector_expected_set_honors_membership_validity_interval() -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 26)
    with _db() as db:
        db.execute(
            StockFactorDaily.__table__.insert(),
            [
                {
                    "trade_date": day,
                    "ts_code": f"00000{index}.SZ",
                    "eligible": True,
                    "calc_version": FACTOR_CALC_VERSION,
                    "config_hash": strategy_hash,
                }
                for index in range(3)
            ],
        )
        db.execute(
            SectorMember.__table__.insert(),
            [
                {
                    "sector_id": 1,
                    "ts_code": "000000.SZ",
                    "valid_from": day,
                    "valid_to": None,
                },
                {
                    "sector_id": 2,
                    "ts_code": "000001.SZ",
                    "valid_from": day - timedelta(days=10),
                    "valid_to": day - timedelta(days=1),
                },
                {
                    "sector_id": 3,
                    "ts_code": "000002.SZ",
                    "valid_from": day + timedelta(days=1),
                    "valid_to": None,
                },
            ],
        )
        _seed_actual(db, day, strategy_hash, [1])
        db.commit()
        result = check_sector_factor_coverage(
            db, day, strategy=settings.strategy, strategy_hash=strategy_hash
        )

    assert result.expected_count == 1
    assert result.status == "PASS"


@pytest.mark.parametrize(
    ("actual_hash", "actual_version"),
    (("old-hash", SECTOR_CALC_VERSION), ("current", "sector_old")),
)
def test_sector_actual_set_rejects_old_identity(actual_hash, actual_version) -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 26)
    resolved_hash = strategy_hash if actual_hash == "current" else actual_hash
    with _db() as db:
        _seed_expected(db, day, strategy_hash, 1)
        _seed_actual(
            db,
            day,
            resolved_hash,
            [1],
            calc_version=actual_version,
        )
        db.commit()
        result = check_sector_factor_coverage(
            db, day, strategy=settings.strategy, strategy_hash=strategy_hash
        )

    assert result.actual_count == 0
    assert result.status == "ERROR"
