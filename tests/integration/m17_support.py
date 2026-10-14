import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.core.config import get_settings
from app.core.paper_config import PaperRuntimeConfig
from app.domain.decision.contracts import content_hash
from app.models.auth import AppUser
from app.models.job import JobRun
from app.models.market_data import (
    DataQualityDaily,
    IndexDaily,
    MarketDaily,
    Sector,
    SectorFactorDaily,
    SectorMember,
    StockAdjFactor,
    StockBasic,
    StockDaily,
    StockDailyBasic,
    StockFactorDaily,
    StockLimitDaily,
    StockOpportunityDaily,
    StockStateDaily,
    StockTradeStatusDaily,
    TradeCalendar,
)
from app.models.paper import PaperAccount, PaperLedgerEntry
from app.services.analysis_identity import (
    FACTOR_CALC_VERSION,
    MARKET_CALC_VERSION,
    OPPORTUNITY_CALC_VERSION,
    SECTOR_CALC_VERSION,
    TRADE_STATUS_CALC_VERSION,
    TREND_CALC_VERSION,
    analysis_strategy_hash,
)
from app.services.calc_metadata import config_hash
from app.services.paper.records import make_record

DAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 10, tzinfo=UTC)
CODES = ("000001.SZ", "600000.SH")


def settings():
    return get_settings().model_copy(update={"paper_config": PaperRuntimeConfig(enabled=True)})


def seed(db, *, days=(DAY,), account=True):
    config = settings()
    strategy = analysis_strategy_hash(config.strategy)
    opportunity_hash = config_hash(config.opportunity_config)
    owner = AppUser(
        id=uuid.uuid4(),
        username=uuid.uuid4().hex,
        password_hash="synthetic",
        is_active=True,
        must_change_password=False,
    )
    other = AppUser(
        id=uuid.uuid4(),
        username=uuid.uuid4().hex,
        password_hash="synthetic",
        is_active=True,
        must_change_password=False,
    )
    db.add_all([owner, other])
    sector = Sector(
        source="SW", source_code="M17-TEST", name="synthetic", level="L1", is_active=True
    )
    db.add(sector)
    db.flush()
    for code in CODES:
        db.add(
            StockBasic(
                ts_code=code,
                name="synthetic",
                market="主板",
                exchange="SZSE" if code.endswith("SZ") else "SSE",
                list_status="L",
                list_date=date(2000, 1, 1),
            )
        )
        db.add(
            SectorMember(
                sector_id=sector.sector_id,
                ts_code=code,
                valid_from=date(2000, 1, 1),
                is_latest=True,
            )
        )
    for index, day in enumerate(days):
        stamp = NOW - timedelta(minutes=2)
        job = JobRun(
            id=uuid.uuid4(),
            job_type="recalculate",
            target_trade_date=day,
            started_at=stamp - timedelta(minutes=5),
            finished_at=NOW - timedelta(minutes=1),
            status="SUCCESS",
            row_count=2,
            cancel_requested=False,
            job_metadata={},
        )
        db.add(job)
        db.add(
            TradeCalendar(
                cal_date=day,
                exchange="SSE",
                is_open=True,
                pretrade_date=days[index - 1] if index else day - timedelta(days=1),
            )
        )
        db.add(
            MarketDaily(
                trade_date=day,
                calc_version=MARKET_CALC_VERSION,
                config_hash=strategy,
                calc_run_id=job.id,
                calculated_at=stamp,
            )
        )
        db.add(
            SectorFactorDaily(
                trade_date=day,
                sector_id=sector.sector_id,
                member_count=2,
                eligible_member_count=2,
                calc_version=SECTOR_CALC_VERSION,
                config_hash=strategy,
                calc_run_id=job.id,
                calculated_at=stamp,
            )
        )
        for code in CODES:
            db.add_all(
                [
                    StockDaily(
                        trade_date=day,
                        ts_code=code,
                        open=10,
                        high=11,
                        low=9,
                        close=10,
                        pre_close=10,
                        vol=1000,
                        source_updated_at=stamp - timedelta(minutes=1),
                    ),
                    StockAdjFactor(trade_date=day, ts_code=code, adj_factor=1),
                    StockDailyBasic(
                        trade_date=day, ts_code=code, close=10, total_mv=10000, circ_mv=9000
                    ),
                    StockLimitDaily(
                        trade_date=day, ts_code=code, pre_close=10, up_limit=11, down_limit=9
                    ),
                    StockFactorDaily(
                        trade_date=day,
                        ts_code=code,
                        eligible=True,
                        calc_version=FACTOR_CALC_VERSION,
                        config_hash=strategy,
                        calc_run_id=job.id,
                        calculated_at=stamp,
                    ),
                    StockStateDaily(
                        trade_date=day,
                        ts_code=code,
                        algo_version=config.algo_version,
                        state="S4",
                        calc_version=TREND_CALC_VERSION,
                        config_hash=strategy,
                        calc_run_id=job.id,
                        calculated_at=stamp,
                    ),
                    StockOpportunityDaily(
                        trade_date=day,
                        ts_code=code,
                        algo_version=config.algo_version,
                        state="S4",
                        opportunity_stage="TREND",
                        opportunity_score=85,
                        extension_risk="LOW",
                        industry_sector_id=sector.sector_id,
                        reason_codes=["TREND", "SOURCE_READY"],
                        calc_version=OPPORTUNITY_CALC_VERSION,
                        config_hash=opportunity_hash,
                        source_strategy_config_hash=strategy,
                        calc_run_id=job.id,
                        calculated_at=stamp,
                    ),
                    StockTradeStatusDaily(
                        trade_date=day,
                        ts_code=code,
                        is_active=True,
                        is_suspended=False,
                        is_st=False,
                        st_status_unknown=False,
                        tradable=True,
                        strategy_eligible=True,
                        calc_version=TRADE_STATUS_CALC_VERSION,
                        config_hash=strategy,
                        calc_run_id=job.id,
                        calculated_at=stamp,
                    ),
                ]
            )
        for dataset in ("stock_st", "suspend_d"):
            db.add(
                DataQualityDaily(
                    trade_date=day,
                    dataset=dataset,
                    expected_rows=0,
                    actual_rows=0,
                    coverage_rate=1,
                    status="PASS",
                    checked_at=stamp,
                    job_id=job.id,
                )
            )
        for code in config.strategy["benchmark"]["market_indices"]:
            db.add(
                IndexDaily(
                    trade_date=day,
                    ts_code=code,
                    open=100,
                    close=100 + index,
                    pre_close=100,
                    high=101 + index,
                    low=99,
                )
            )
    if db.get(TradeCalendar, days[-1] + timedelta(days=1)) is None:
        db.add(
            TradeCalendar(
                cal_date=days[-1] + timedelta(days=1),
                exchange="SSE",
                is_open=True,
                pretrade_date=days[-1],
            )
        )
    row = None
    if account:
        snapshot = {
            "schema_version": "m17-account-config-v1",
            "paper": config.paper_config.policy.model_dump(mode="json"),
            "execution": config.execution_config.model_dump(mode="json"),
            "accounting": config.accounting_config.model_dump(mode="json"),
            "decision": config.paper_config.decision.model_dump(mode="json"),
        }
        row = make_record(
            PaperAccount,
            owner.id,
            "seed",
            now=NOW - timedelta(days=1),
            name="synthetic",
            mode="PAPER",
            state="PAUSED",
            initial_cash=Decimal("1000000"),
            benchmark_code="000300.SH",
            first_trade_date=days[0] + timedelta(days=1),
            config_version=config.paper_config.policy.version,
            config_snapshot_json=snapshot,
            config_hash=content_hash(snapshot),
            version=1,
            request_id="seed",
            request_hash="a" * 64,
        )
        db.add(row)
        db.flush()
        db.add(
            make_record(
                PaperLedgerEntry,
                owner.id,
                "initial",
                now=NOW - timedelta(days=1),
                account_id=row.id,
                trade_date=row.first_trade_date,
                business_key="initial",
                entry_type="INITIAL_CASH",
                cash_delta=row.initial_cash,
                quantity_delta=0,
            )
        )
    db.commit()
    return owner.id, other.id, row.id if row else None
