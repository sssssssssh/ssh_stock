from datetime import date

import pytest
from app.core.config import get_settings
from app.models.market_data import (
    MarketDaily,
    SectorFactorDaily,
    SectorMember,
    StockDaily,
    StockFactorDaily,
    StockStateDaily,
)
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    SECTOR_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.quality.analysis_readiness import is_core_analysis_complete
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _readiness_db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in (
        StockDaily.__table__,
        StockFactorDaily.__table__,
        MarketDaily.__table__,
        SectorFactorDaily.__table__,
        SectorMember.__table__,
        StockStateDaily.__table__,
    ):
        table.create(engine)
    return Session(engine)


def _insert_identity_dependencies(db: Session, day: date, strategy_hash: str) -> None:
    db.execute(
        SectorMember.__table__.insert(),
        [{
            "sector_id": 1,
            "ts_code": "000000.SZ",
            "valid_from": day,
            "is_latest": True,
        }],
    )
    db.execute(
        MarketDaily.__table__.insert(),
        [{
            "trade_date": day,
            "calc_version": MARKET_CALC_VERSION,
            "config_hash": strategy_hash,
        }],
    )
    db.execute(
        SectorFactorDaily.__table__.insert(),
        [{
            "trade_date": day,
            "sector_id": 1,
            "calc_version": SECTOR_CALC_VERSION,
            "config_hash": strategy_hash,
        }],
    )


def test_core_readiness_rejects_fake_100_percent_opportunity_coverage() -> None:
    """5000 factors / 1000 states must fail even if 1000 opportunities cover states."""
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 24)
    codes = [f"{index:06d}.SZ" for index in range(5000)]
    with _readiness_db() as db:
        db.execute(
            StockDaily.__table__.insert(),
            [{"trade_date": day, "ts_code": code} for code in codes],
        )
        db.execute(
            StockFactorDaily.__table__.insert(),
            [
                {
                    "trade_date": day,
                    "ts_code": code,
                    "eligible": True,
                    "calc_version": FACTOR_CALC_VERSION,
                    "config_hash": strategy_hash,
                }
                for code in codes
            ],
        )
        db.execute(
            StockStateDaily.__table__.insert(),
            [
                {
                    "trade_date": day,
                    "ts_code": code,
                    "algo_version": settings.algo_version,
                    "state": "S4",
                    "is_new_state": False,
                    "fast_transition": False,
                    "calc_version": TREND_CALC_VERSION,
                    "config_hash": strategy_hash,
                }
                for code in codes[:1000]
            ],
        )
        _insert_identity_dependencies(db, day, strategy_hash)
        db.commit()

        assert not is_core_analysis_complete(
            db,
            day,
            strategy=settings.strategy,
            algo_version=settings.algo_version,
        )


def test_core_readiness_fails_closed_when_state_rows_are_empty() -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 25)
    with _readiness_db() as db:
        db.execute(
            StockDaily.__table__.insert(),
            [{"trade_date": day, "ts_code": "000001.SZ"}],
        )
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
        _insert_identity_dependencies(db, day, strategy_hash)
        db.commit()

        assert not is_core_analysis_complete(
            db,
            day,
            strategy=settings.strategy,
            algo_version=settings.algo_version,
        )


@pytest.mark.parametrize(
    ("actual_sector_count", "expected_ready"),
    ((30, True), (29, False), (1, False)),
)
def test_core_readiness_requires_sector_coverage_pass(
    actual_sector_count, expected_ready
) -> None:
    settings = get_settings()
    strategy_hash = analysis_strategy_hash(settings.strategy)
    day = date(2026, 9, 26)
    codes = [f"{index:06d}.SZ" for index in range(30)]
    with _readiness_db() as db:
        db.execute(
            StockDaily.__table__.insert(),
            [{"trade_date": day, "ts_code": code} for code in codes],
        )
        db.execute(
            StockFactorDaily.__table__.insert(),
            [
                {
                    "trade_date": day,
                    "ts_code": code,
                    "eligible": True,
                    "calc_version": FACTOR_CALC_VERSION,
                    "config_hash": strategy_hash,
                }
                for code in codes
            ],
        )
        db.execute(
            StockStateDaily.__table__.insert(),
            [
                {
                    "trade_date": day,
                    "ts_code": code,
                    "algo_version": settings.algo_version,
                    "state": "S4",
                    "is_new_state": False,
                    "fast_transition": False,
                    "calc_version": TREND_CALC_VERSION,
                    "config_hash": strategy_hash,
                }
                for code in codes
            ],
        )
        db.execute(
            SectorMember.__table__.insert(),
            [
                {
                    "sector_id": index + 1,
                    "ts_code": code,
                    "valid_from": day,
                    "is_latest": True,
                }
                for index, code in enumerate(codes)
            ],
        )
        db.execute(
            SectorFactorDaily.__table__.insert(),
            [
                {
                    "trade_date": day,
                    "sector_id": sector_id,
                    "calc_version": SECTOR_CALC_VERSION,
                    "config_hash": strategy_hash,
                }
                for sector_id in range(1, actual_sector_count + 1)
            ],
        )
        db.execute(
            MarketDaily.__table__.insert(),
            [{
                "trade_date": day,
                "calc_version": MARKET_CALC_VERSION,
                "config_hash": strategy_hash,
            }],
        )
        db.commit()

        assert (
            is_core_analysis_complete(
                db,
                day,
                strategy=settings.strategy,
                algo_version=settings.algo_version,
            )
            is expected_ready
        )
