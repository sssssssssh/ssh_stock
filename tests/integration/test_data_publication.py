"""Publication isolation regressions against explicitly isolated PostgreSQL 17."""

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.core.config import get_settings
from app.core.published_db import published_snapshot
from app.models import market_data as m
from app.models.data_publication import DataPublication, DataPublicationPreimage, DataPublicationRow
from app.models.job import JobRun
from app.models.market_data import StockFactorDaily
from app.repositories.job_run import update_job
from app.repositories.replace_slice import replace_slice_rows
from app.repositories.upsert import upsert_rows
from app.services.data_publication import (
    CORE,
    KEYS,
    MODELS,
    PublicationWorkspace,
    record_validation,
)
from app.services.job_execution import Execution, current_execution
from app.services.job_guard import create_queued_ingestion_job, data_queue_identity
from app.services.job_worker import claim_next_job, execute_claimed_job
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from tests.integration.m16_6_support import isolated_contract_database

DAY = date(2026, 9, 1)


@pytest.fixture
def publication_db(monkeypatch):
    with isolated_contract_database(monkeypatch) as database:
        yield database


def sample_row(model, source, value=10, day=DAY):
    from app.services.analysis_identity import (
        FACTOR_CALC_VERSION,
        MARKET_CALC_VERSION,
        OPPORTUNITY_CALC_VERSION,
        SECTOR_CALC_VERSION,
        SIGNAL_CALC_VERSION,
        THEME_CALC_VERSION,
        TRADE_STATUS_CALC_VERSION,
        TREND_CALC_VERSION,
    )

    versions = (
        TRADE_STATUS_CALC_VERSION,
        FACTOR_CALC_VERSION,
        MARKET_CALC_VERSION,
        SECTOR_CALC_VERSION,
        THEME_CALC_VERSION,
        TREND_CALC_VERSION,
        OPPORTUNITY_CALC_VERSION,
        SIGNAL_CALC_VERSION,
    )
    identity = data_queue_identity()
    name = model.__tablename__
    values = dict(
        trade_date=day,
        ts_code="TEST.SZ",
        sector_id=101,
        theme_code="TEST",
        algo_version=get_settings().algo_version,
        signal_type="RIGHT_SIDE_NEW",
        state="S4",
        opportunity_stage="TREND",
        eligible=True,
        is_active=True,
        is_suspended=False,
        tradable=True,
        strategy_eligible=True,
        calculated_at=datetime.now(UTC),
        calc_run_id=source,
        source_strategy_config_hash=identity["analysis"],
        config_hash=identity["opportunity"]
        if name in {"theme_factor_daily", "stock_opportunity_daily"}
        else identity["analysis"],
        calc_version=versions[MODELS.index(model)],
        adj_close=value,
        market_score=value,
        opportunity_score=value,
        heat_score=value,
    )
    return {key: value for key, value in values.items() if key in model.__table__.c}


def seed_published(factory, *, legacy_null=False):
    with factory() as db:
        old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
        db.add(old)
        db.add(
            m.Sector(sector_id=101, source="SW", source_code="TEST", name="synthetic", level="L1")
        )
        db.add(m.Theme(theme_code="TEST", source="THS", name="synthetic", theme_type="N"))
        db.add(m.TradeCalendar(cal_date=DAY, is_open=True))
        db.flush()
        for model in MODELS[:8]:
            payload = sample_row(model, None if legacy_null else old.id)
            # PostgreSQL JSON timestamps trim trailing fractional zeroes; the
            # preimage comparison must use PostgreSQL's canonical representation.
            payload["calculated_at"] = datetime.now(UTC).replace(microsecond=123450)
            upsert_rows(
                db,
                model,
                [payload],
                KEYS[model.__tablename__],
            )
        db.commit()
        return old.id


@contextmanager
def candidate(factory, engine, *, kind="recalculate"):
    with factory() as db:
        job = create_queued_ingestion_job(
            db,
            kind,
            DAY,
            step="queued",
            metadata={"start": DAY.isoformat(), "end": DAY.isoformat(), "evaluate_signals": False},
        )
        assert claim_next_job(db, "publication-test") == job.id
        db.refresh(job)
        token = current_execution.set(Execution(job.id, job.worker_id, job.execution_token, engine))
        ws = PublicationWorkspace(db, job)
        try:
            ws.open()
            db.refresh(job)
            yield db, job
        finally:
            ws.close()
            current_execution.reset(token)


def stage_all(db, job, value=20, *, approve=True):
    for model in MODELS[:8]:
        replace_slice_rows(
            db,
            model,
            [sample_row(model, job.id, value)],
            scope_filters=[model.trade_date == DAY],
            key_columns=KEYS[model.__tablename__],
        )
        db.commit()
    if approve:
        # A synthetic certificate for publication-layer tests only; the real
        # quality service is covered separately and is the production caller.
        record_validation(db, job.id, DAY, SimpleNamespace(has_error=False))
        db.commit()


def test_successful_candidate_publishes_all_tables_and_stable_signal_id(publication_db):
    factory, engine = publication_db
    old = seed_published(factory)
    with factory() as db:
        signal_id = db.scalar(select(m.StrategySignal.id))
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        assert db.scalar(select(m.StockFactorDaily.adj_close)) == 20
        with factory() as reader:
            assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) == old
            assert reader.scalar(select(m.StockStateDaily.calc_run_id)) == old
        update_job(db, job, status="SUCCESS")
        key = job.id
    with factory() as reader:
        for model in MODELS[:8]:
            assert reader.scalar(select(model.calc_run_id)) == key
        assert reader.scalar(select(m.StrategySignal.id)) == signal_id
        assert reader.get(DataPublication, key).state == "PUBLISHED"
        assert len(list(reader.scalars(select(DataPublicationPreimage)))) == len(CORE)


@pytest.mark.parametrize(
    "history, failure",
    [
        ("complete", None),
        ("partial", None),
        ("absent", None),
        ("absent", "cancel"),
        ("absent", "quality"),
    ],
)
def test_real_recalculation_and_quality_publish_without_synthetic_certificate(
    publication_db, monkeypatch, history, failure
):

    factory, engine = publication_db
    old = seed_published(factory)
    with factory() as db:
        if history == "absent":
            # Genuine v1 A remains untouched until the corrected v2 root commits.
            for model in MODELS[:8]:
                previous_version = sample_row(model, old)["calc_version"].replace("_v2", "_v1")
                db.execute(model.__table__.update().values(calc_version=previous_version))
        db.add(
            m.StockBasic(
                ts_code="TEST.SZ", name="synthetic", list_status="L", list_date=date(2020, 1, 1)
            )
        )
        db.add(m.SectorMember(sector_id=101, ts_code="TEST.SZ", valid_from=date(2020, 1, 1)))
        days = sorted(
            DAY - timedelta(days=n) for n in range(410) if (DAY - timedelta(days=n)).weekday() < 5
        )
        for day in days:
            if day != DAY:
                db.add(m.TradeCalendar(cal_date=day, is_open=True))
            db.add(
                m.StockDaily(
                    trade_date=day,
                    ts_code="TEST.SZ",
                    open=20,
                    high=20.1,
                    low=19.9,
                    close=20,
                    pre_close=20,
                    pct_chg=0,
                    vol=100000,
                    amount=1000000,
                )
            )
            db.add(m.StockAdjFactor(trade_date=day, ts_code="TEST.SZ", adj_factor=1))
            db.add(
                m.StockDailyBasic(
                    trade_date=day,
                    ts_code="TEST.SZ",
                    close=20,
                    turnover_rate=1,
                    volume_ratio=1,
                    total_mv=1000000,
                    circ_mv=1000000,
                )
            )
            db.add(
                m.StockLimitDaily(
                    trade_date=day, ts_code="TEST.SZ", pre_close=20, up_limit=22, down_limit=18
                )
            )
            for code in get_settings().strategy["benchmark"]["market_indices"]:
                db.add(
                    m.IndexDaily(
                        trade_date=day,
                        ts_code=code,
                        open=4000,
                        high=4001,
                        low=3999,
                        close=4000,
                        pre_close=4000,
                        pct_chg=0,
                        vol=100000,
                        amount=1000000,
                    )
                )
            for dataset in ("stock_st", "suspend_d"):
                db.add(
                    m.DataQualityDaily(
                        trade_date=day,
                        dataset=dataset,
                        status="PASS",
                        expected_rows=0,
                        actual_rows=0,
                        job_id=old,
                    )
                )
        # A is an existing successful historical baseline, including the older
        # trade-status dependencies read by the unchanged factor warm-up.
        upsert_rows(
            db,
            m.StockTradeStatusDaily,
            [
                {
                    **sample_row(m.StockTradeStatusDaily, old, day=day),
                    "is_st": False,
                    "st_status_unknown": False,
                }
                for day in days
                if history == "complete" or (history == "partial" and day.day % 2 == 0)
            ],
            KEYS["stock_trade_status_daily"],
        )
        db.commit()
    if failure:
        from app.api.v1.jobs import cancel_job
        from app.services.factors import FactorService

        from tests.integration.test_cold_start_cli_v12 import snapshot

        baseline = snapshot(factory)
        original = FactorService.recalc

        def interrupt_after_real_calculation(service, start, end, **kwargs):
            rows = original(service, start, end, **kwargs)
            if end == DAY:
                if failure == "cancel":
                    with factory() as external:
                        cancel_job(kwargs["calc_run_id"], external)
                else:
                    service.db.info["publication_workspace"].delete_keys(
                        m.StockFactorDaily, [(DAY, "TEST.SZ")]
                    )
                    service.db.commit()
            return rows

        monkeypatch.setattr(FactorService, "recalc", interrupt_after_real_calculation)
    # Actual Worker owns candidate setup, computation, quality and publication;
    # no calculator/quality/Provider mocks and no fabricated certificate.
    with factory() as db:
        job = create_queued_ingestion_job(
            db,
            "recalculate",
            DAY,
            step="queued",
            metadata={
                "start": DAY.isoformat(),
                "end": DAY.isoformat(),
                "evaluate_signals": False,
            },
        )
        assert claim_next_job(db, "cold-start-worker") == job.id
        db.refresh(job)
        key, worker_id, token = job.id, job.worker_id, job.execution_token
    with factory() as db:
        execute_claimed_job(db, key, expected_worker=worker_id, expected_token=token)
    with factory() as reader:
        if failure:
            assert reader.get(JobRun, key).status == (
                "CANCELLED" if failure == "cancel" else "FAILED"
            )
            assert reader.get(DataPublication, key).state == "ABORTED"
            after = snapshot(factory)
            for model in MODELS:
                # Raw quality facts retain their independent evidence policy.
                if model is not m.DataQualityDaily:
                    assert after[model.__tablename__] == baseline[model.__tablename__]
            return
        assert reader.get(JobRun, key).status == "SUCCESS"
        assert reader.get(DataPublication, key).state == "PUBLISHED"
        if history == "absent":
            for table, version in (
                ("stock_factor_daily", "factor_v1"),
                ("strategy_signal", "signal_v1"),
            ):
                prior = reader.scalar(
                    select(DataPublicationPreimage.row_data).where(
                        DataPublicationPreimage.publication_id == key,
                        DataPublicationPreimage.table_name == table,
                    )
                )
                assert prior["calc_version"] == version
                assert prior["calc_run_id"] == str(old)
        for model in (m.StockFactorDaily, m.StockStateDaily, m.StockOpportunityDaily):
            assert reader.scalar(select(model.calc_run_id)) == key
            assert (
                reader.scalar(select(model.calc_version)) == sample_row(model, key)["calc_version"]
            )
            assert reader.scalar(select(func.min(model.trade_date))) == DAY
        quality = reader.scalar(
            select(m.DataQualityDaily).where(
                m.DataQualityDaily.trade_date == DAY,
                m.DataQualityDaily.dataset == "factor_vs_daily",
            )
        )
        assert quality.status == "PASS" and quality.job_id == key


def test_signal_delete_archives_evaluation_and_terminal_evidence_is_immutable(publication_db):
    factory, engine = publication_db
    seed_published(factory)
    with factory() as db:
        signal = db.scalar(select(m.StrategySignal))
        db.add(
            m.SignalForwardEval(
                signal_id=signal.id,
                trade_date=DAY,
                ts_code=signal.ts_code,
                signal_type=signal.signal_type,
                algo_version=signal.algo_version,
            )
        )
        db.commit()
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        replace_slice_rows(
            db,
            m.StrategySignal,
            [],
            scope_filters=[m.StrategySignal.trade_date == DAY],
            key_columns=KEYS["strategy_signal"],
        )
        record_validation(db, job.id, DAY, SimpleNamespace(has_error=False))
        db.commit()
        update_job(db, job, status="SUCCESS")
        key = job.id
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.StrategySignal)) == 0
        assert db.scalar(select(func.count()).select_from(m.SignalForwardEval)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(DataPublicationPreimage)
                .where(
                    DataPublicationPreimage.publication_id == key,
                    DataPublicationPreimage.table_name == "signal_forward_eval",
                )
            )
            == 1
        )
        with pytest.raises(DBAPIError, match="PUBLICATION_EVIDENCE_IMMUTABLE"):
            db.execute(
                update(DataPublicationRow)
                .where(DataPublicationRow.publication_id == key)
                .values(is_deleted=True, row_data=None)
            )
            db.commit()
        db.rollback()
        with pytest.raises(DBAPIError, match="PUBLICATION_IMMUTABLE"):
            db.get(DataPublication, key).state = "ABORTED"
            db.commit()
        db.rollback()
        assert db.get(DataPublication, key).state == "PUBLISHED"


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "PARTIAL"])
def test_failed_or_cancelled_candidate_never_replaces_a(publication_db, status):
    factory, engine = publication_db
    old = seed_published(factory)
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        key = job.id
        update_job(db, job, status=status)
    with factory() as reader:
        for model in MODELS[:8]:
            assert reader.scalar(select(model.calc_run_id)) == old
        assert reader.get(DataPublication, key).state == "ABORTED"
        assert len(list(reader.scalars(select(DataPublicationRow)))) == 8


def test_old_a_does_not_validate_an_incomplete_b(publication_db):
    factory, engine = publication_db
    old = seed_published(factory)
    with candidate(factory, engine) as (db, job):
        stage_all(db, job, approve=False)
        with pytest.raises(ValueError, match="PUBLICATION_QUALITY_NOT_VALIDATED"):
            update_job(db, job, status="SUCCESS")
        db.rollback()
        update_job(db, job, status="FAILED")
    with factory() as reader:
        assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) == old


def test_candidate_indexes_and_public_outer_join_plan_remain_separate(
    publication_db, record_property
):
    import json
    import time

    factory, engine = publication_db
    old = seed_published(factory)
    with candidate(factory, engine) as (db, job):
        payload = [
            {**sample_row(m.StockFactorDaily, job.id, 20), "ts_code": f"T{n:05}.SZ"}
            for n in range(2000)
        ]
        started = time.monotonic()
        upsert_rows(db, m.StockFactorDaily, payload, KEYS["stock_factor_daily"])
        db.commit()
        elapsed = round((time.monotonic() - started) * 1000, 2)
        db.execute(text("ANALYZE public.data_publication_row"))
        plan = db.scalar(
            text(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT adj_close FROM stock_factor_daily "
                "WHERE trade_date=:day AND ts_code='T01000.SZ'"
            ),
            {"day": DAY},
        )
        assert "idx_publication_row_entity" in json.dumps(plan)
        assert db.scalar(select(func.count()).select_from(m.StockFactorDaily)) == 2001
        with factory() as reader:
            public_plan = reader.scalar(
                text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                    "SELECT o.ts_code,f.adj_close FROM stock_opportunity_daily o "
                    "LEFT JOIN stock_factor_daily f USING(trade_date,ts_code) "
                    "WHERE o.trade_date=:day ORDER BY o.ts_code LIMIT 30 OFFSET 0"
                ),
                {"day": DAY},
            )
            assert "data_publication" not in json.dumps(public_plan)
            assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) == old
            assert reader.scalar(select(func.count()).select_from(m.StockFactorDaily)) == 1
        record_property("synthetic_candidate_rows", 2000)
        record_property("candidate_write_ms", elapsed)
        record_property("candidate_plan", json.dumps(plan))
        record_property("public_join_plan", json.dumps(public_plan))
        update_job(db, job, status="CANCELLED")


def test_public_read_snapshot_never_mixes_a_and_b_across_queries(publication_db):
    factory, engine = publication_db
    old = seed_published(factory)
    with candidate(factory, engine) as (db, job), factory() as outer:
        stage_all(db, job)
        with published_snapshot(outer) as reader:
            assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) == old
            update_job(db, job, status="SUCCESS")
            assert reader.scalar(select(m.StockStateDaily.calc_run_id)) == old
        with published_snapshot(outer) as reader:
            assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) == job.id
            assert reader.scalar(select(m.StockStateDaily.calc_run_id)) == job.id


def test_missing_a_is_not_replaced_by_in_progress_b_and_cleanup_does_not_leak(publication_db):
    factory, engine = publication_db
    with candidate(factory, engine) as (db, job):
        replace_slice_rows(
            db,
            m.StockFactorDaily,
            [sample_row(m.StockFactorDaily, job.id)],
            scope_filters=[m.StockFactorDaily.trade_date == DAY],
            key_columns=KEYS["stock_factor_daily"],
        )
        db.commit()
        with factory() as reader:
            assert reader.scalar(select(m.StockFactorDaily.trade_date)) is None
        update_job(db, job, status="CANCELLED")
    # Exercise pooled-connection reuse, not just a newly allocated connection.
    for _ in range(6):
        with factory() as reader:
            assert reader.scalar(select(m.StockFactorDaily.trade_date)) is None


def test_legacy_null_provenance_survives_cancel(publication_db):
    factory, engine = publication_db
    seed_published(factory, legacy_null=True)
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        update_job(db, job, status="CANCELLED")
    with factory() as reader:
        assert reader.scalar(select(m.StockFactorDaily.adj_close)) == 10
        assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) is None


def test_actual_api_latest_join_count_pagination_and_private_warmup(publication_db):
    from app.api.v1.opportunities import trends

    factory, engine = publication_db
    seed_published(factory)
    with factory() as setup:
        setup.execute(update(m.StockFactorDaily).values(rps20=10))
        setup.commit()
    with candidate(factory, engine) as (db, job), factory() as outer:
        stage_all(db, job)
        # A candidate-only extra date must neither move latest nor be published
        # outside the requested/certified scope (e.g. calculation warm-up rows).
        future = date(2026, 9, 2)
        for model in (m.StockFactorDaily, m.StockOpportunityDaily):
            upsert_rows(
                db, model, [sample_row(model, job.id, 30, future)], KEYS[model.__tablename__]
            )
        db.commit()
        record_validation(db, job.id, DAY, SimpleNamespace(has_error=False))
        db.commit()

        def api(reader, offset=0):
            return trends(None, "S4,S5", None, None, None, None, 1, offset, db=reader)

        with published_snapshot(outer) as reader:
            before = api(reader)
            assert before["meta"]["trade_date"] == DAY.isoformat()
            assert before["meta"]["total"] == 1
            assert len(before["data"]) == 1
            assert before["data"][0]["rps20"] == 10
            assert before["data"][0]["opportunity_score"] == 10
            assert api(reader, 1)["data"] == []
            update_job(db, job, status="SUCCESS")
            assert api(reader)["data"] == before["data"]
        with published_snapshot(outer) as reader:
            after = api(reader)
            assert after["meta"]["trade_date"] == DAY.isoformat()
            assert after["meta"]["total"] == 1
            assert after["data"][0]["opportunity_score"] == 20
            assert after["data"][0]["calc_run_id"] == job.id
            assert reader.scalar(select(func.max(m.StockFactorDaily.trade_date))) == DAY


def test_nonempty_0057_upgrade_preserves_old_rows_and_history(monkeypatch):
    from alembic import command
    from alembic.config import Config

    with isolated_contract_database(monkeypatch, revision="0057_data_queue") as (factory, engine):
        old = seed_published(factory)
        with factory() as db:
            before = db.scalar(text("SELECT jsonb_agg(to_jsonb(t)) FROM stock_factor_daily t"))
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with factory() as db:
            assert (
                db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0058_data_publication"
            )
            assert (
                db.scalar(text("SELECT jsonb_agg(to_jsonb(t)) FROM stock_factor_daily t")) == before
            )
            assert db.get(JobRun, old).status == "SUCCESS"
            assert db.scalar(select(func.count()).select_from(DataPublication)) == 0


@pytest.mark.parametrize(
    "status,dirty_status", [("SUCCESS", "RESOLVED"), ("FAILED", "FAILED"), ("CANCELLED", "OPEN")]
)
def test_catchup_child_dirty_and_raw_refresh_wait_for_root_publication(
    publication_db, monkeypatch, status, dirty_status
):
    from app.jobs.catchup_job import CatchUpJob
    from app.repositories.job_run import start_job
    from app.services.dirty import mark_dirty_ranges_processing, mark_dirty_ranges_resolved

    factory, engine = publication_db
    old = seed_published(factory)
    with candidate(factory, engine, kind="catchup") as (db, root):
        child = start_job(
            db, "recalculate", DAY, metadata={"start": DAY.isoformat(), "end": DAY.isoformat()}
        )
        update_job(db, child, step="starting child")
        dirty = m.DataDirtyRange(
            dataset="stock_daily",
            dirty_start_date=DAY,
            dirty_end_date=DAY,
            reason="synthetic",
            source_job_id=root.id,
            status="OPEN",
            retry_count=0,
        )
        db.add(dirty)
        db.commit()
        mark_dirty_ranges_processing(db, [dirty])
        stage_all(db, child)
        mark_dirty_ranges_resolved(db, [dirty])
        update_job(db, child, status="SUCCESS")
        with factory() as reader:
            assert reader.get(DataPublication, root.id).state == "PREPARING"
            assert reader.get(m.DataDirtyRange, dirty.id).status == "PROCESSING"
            assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) == old
        update_job(db, root, step="refresh raw only")
        catchup = CatchUpJob.__new__(CatchUpJob)
        catchup.db, catchup.settings = db, SimpleNamespace(strategy=get_settings().strategy)
        catchup.ingestion = SimpleNamespace(
            **{
                name: lambda *args, **kwargs: None
                for name in (
                    "sync_stock_st",
                    "sync_suspend_daily",
                    "sync_daily",
                    "sync_adj_factor",
                    "sync_daily_basic",
                    "sync_index_daily",
                    "sync_stock_limit",
                )
            }
        )
        monkeypatch.setattr(
            "app.jobs.catchup_job.check_raw_completeness",
            lambda *args, **kwargs: SimpleNamespace(overall_status="PASS"),
        )
        assert catchup._sync_and_validate_raw_date(DAY)
        assert db.scalar(select(m.StockTradeStatusDaily.calc_run_id)) == child.id
        update_job(db, root, status=status)
        dirty_id, child_id = dirty.id, child.id
    with factory() as reader:
        assert reader.get(m.DataDirtyRange, dirty_id).status == dirty_status
        assert reader.get(m.DataDirtyRange, dirty_id).retry_count == (
            1 if status == "FAILED" else 0
        )
        for model in MODELS[:8]:
            assert reader.scalar(select(model.calc_run_id)) == (
                child_id if status == "SUCCESS" else old
            )


def test_approved_manual_cas_after_local_execution_exit_preserves_a_and_audit(publication_db):
    from app.services.job_guard import INGESTION_ADVISORY_LOCK_KEY

    factory, engine = publication_db
    old = seed_published(factory)
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        identity = job.id, job.worker_id, job.execution_token
        # Deliberately leave RUNNING: the fixture closes the sole synthetic
        # executor/connection, proving local exit only, not remote production exit.
    with factory() as db:
        waiting = create_queued_ingestion_job(db, "validate_data", DAY, step="waiting", metadata={})
        assert claim_next_job(db, "replacement") is None
        db.rollback()
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": INGESTION_ADVISORY_LOCK_KEY})
        root = db.scalar(
            select(JobRun).where(JobRun.id == identity[0]).with_for_update(key_share=True)
        )
        assert not list(db.scalars(select(JobRun.id).where(JobRun.parent_job_id == root.id)))
        report = {
            "reason": "synthetic approved recovery",
            "operator": "isolated-test",
            "all_executors_and_sql_stopped": True,
            "previous_status": "RUNNING",
            "new_status": "FAILED",
        }
        changed = db.execute(
            update(JobRun)
            .where(
                JobRun.id == identity[0],
                JobRun.status == "RUNNING",
                JobRun.worker_id == identity[1],
                JobRun.execution_token == identity[2],
            )
            .values(
                status="FAILED",
                job_metadata={**root.job_metadata, "manual_reconciliations": [report]},
            )
        )
        assert changed.rowcount == 1
        ledger = db.get(DataPublication, root.id)
        assert ledger.state == "PREPARING"
        ledger.state = "ABORTED"
        db.commit()
        assert db.scalar(select(m.StockFactorDaily.calc_run_id)) == old
        assert db.get(JobRun, root.id).job_metadata["manual_reconciliations"] == [report]
        assert claim_next_job(db, "replacement") == waiting.id


def test_real_quality_cannot_borrow_a_and_keeps_a_quality_published(publication_db):
    from app.services.quality.daily_quality import record_cross_table_quality

    factory, engine = publication_db
    old = seed_published(factory)
    with factory() as db:
        db.add(m.StockBasic(ts_code="TEST.SZ", name="synthetic", list_date=date(2020, 1, 1)))
        db.add(m.StockDaily(trade_date=DAY, ts_code="TEST.SZ", open=10, high=11, low=9, close=10))
        upsert_rows(
            db,
            m.DataQualityDaily,
            [dict(trade_date=DAY, dataset="factor_vs_daily", status="PASS", job_id=old)],
            ["trade_date", "dataset"],
        )
        db.commit()
    with candidate(factory, engine) as (db, job):
        # A has valid current factors and states, but B has not computed either.
        result = record_cross_table_quality(db, DAY, job_id=job.id)
        db.commit()
        assert result.counts["stock_factor_daily"] == 0
        assert result.results["factor_vs_daily"] == "ERROR"
        assert result.has_error
        with factory() as reader:
            assert (
                reader.scalar(
                    select(m.DataQualityDaily.status).where(
                        m.DataQualityDaily.dataset == "factor_vs_daily"
                    )
                )
                == "PASS"
            )
        update_job(db, job, status="FAILED")
        key = job.id
    with factory() as reader:
        evidence = reader.scalar(
            select(DataPublicationRow.row_data).where(
                DataPublicationRow.publication_id == key,
                DataPublicationRow.row_key == [DAY.isoformat(), "factor_vs_daily"],
            )
        )
        assert evidence["status"] == "ERROR" and evidence["job_id"] == str(key)
        assert reader.scalar(select(m.StockFactorDaily.calc_run_id)) == old


@pytest.mark.parametrize("mode", ["budget", "timeout", "identity", "changed_base", "missing_stage"])
def test_publish_fails_closed_without_changing_a(publication_db, monkeypatch, mode):
    from app.services import data_publication as publication

    factory, engine = publication_db
    old = seed_published(factory)
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        expected = "PUBLICATION_ROW_BUDGET_EXCEEDED"
        if mode == "budget":
            original = publication.scheduler_setting
            monkeypatch.setattr(
                publication,
                "scheduler_setting",
                lambda name, default: (
                    1 if name == "data_publish_max_rows" else original(name, default)
                ),
            )
        elif mode == "timeout":
            ticks = iter([0, 100000])
            monkeypatch.setattr(publication, "monotonic", lambda: next(ticks))
            expected = "PUBLICATION_TIME_BUDGET_EXCEEDED"
        elif mode == "identity":
            db.execute(
                update(DataPublicationRow)
                .where(
                    DataPublicationRow.publication_id == job.id,
                    DataPublicationRow.table_name == "stock_factor_daily",
                )
                .values(row_data=DataPublicationRow.row_data.op("||")({"config_hash": "wrong"}))
            )
            db.commit()
            expected = "PUBLICATION_CANDIDATE_IDENTITY_MISMATCH"
        elif mode == "changed_base":
            with factory() as unsupported_writer:
                unsupported_writer.execute(update(m.StockFactorDaily).values(adj_close=11))
                unsupported_writer.commit()
            expected = "PUBLICATION_BASE_CHANGED"
        else:
            from app.models.data_publication import DataPublicationScope

            db.execute(
                DataPublicationScope.__table__.delete().where(
                    DataPublicationScope.publication_id == job.id,
                    DataPublicationScope.table_name == "stock_opportunity_daily",
                )
            )
            db.commit()
            expected = "PUBLICATION_STAGE_INCOMPLETE"
        with pytest.raises(ValueError, match=expected):
            update_job(db, job, status="SUCCESS")
        db.rollback()
        update_job(db, job, status="FAILED")
    with factory() as reader:
        assert reader.scalar(select(m.StockStateDaily.calc_run_id)) == old
        assert reader.scalar(select(m.StockFactorDaily.adj_close)) == (
            11 if mode == "changed_base" else 10
        )


def test_candidate_mutation_invalidates_its_prior_quality_certificate(publication_db):
    factory, engine = publication_db
    seed_published(factory)
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        replace_slice_rows(
            db,
            m.StockFactorDaily,
            [sample_row(m.StockFactorDaily, job.id, 30)],
            scope_filters=[m.StockFactorDaily.trade_date == DAY],
            key_columns=KEYS["stock_factor_daily"],
        )
        db.commit()
        with pytest.raises(ValueError, match="PUBLICATION_QUALITY_NOT_VALIDATED"):
            update_job(db, job, status="SUCCESS")
        db.rollback()
        update_job(db, job, status="FAILED")


def _execute_synthetic_pipeline(factory, monkeypatch, pipeline):
    import app.services.job_worker as worker

    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker, "run_recalculation", pipeline)
    with factory() as db:
        job = create_queued_ingestion_job(
            db,
            "recalculate",
            DAY,
            step="queued",
            metadata={"start": DAY.isoformat(), "end": DAY.isoformat(), "evaluate_signals": False},
        )
        assert claim_next_job(db, "publication-test") == job.id
        claim = db.info["data_claim"]
    with factory() as db:
        execute_claimed_job(db, claim[0], expected_worker=claim[1], expected_token=claim[2])
    return claim[0]


def test_disconnect_mid_publication_rolls_back_a_and_holds_slot(publication_db, monkeypatch):
    factory, engine = publication_db
    old = seed_published(factory)
    failed = []

    def disconnect(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO public."stock_factor_daily"') and not failed:
            failed.append(True)
            raise OperationalError(
                "synthetic", {}, OSError("response unknown"), connection_invalidated=True
            )

    def pipeline(db, job, *_args, **_kwargs):
        stage_all(db, job)
        update_job(db, job, status="SUCCESS")

    event.listen(engine, "before_cursor_execute", disconnect)
    try:
        key = _execute_synthetic_pipeline(factory, monkeypatch, pipeline)
    finally:
        event.remove(engine, "before_cursor_execute", disconnect)
    with factory() as db:
        assert failed == [True]
        assert db.get(JobRun, key).status == "RUNNING"
        assert db.get(JobRun, key).job_metadata["execution_unconfirmed"]
        assert db.get(DataPublication, key).state == "PREPARING"
        for model in MODELS[:8]:
            assert db.scalar(select(model.calc_run_id)) == old
        assert claim_next_job(db, "other-worker") is None


def test_committed_publish_response_loss_never_rewrites_success(publication_db, monkeypatch):
    factory, _engine = publication_db
    seed_published(factory)
    original = Session.commit
    lost = []

    def commit(db):
        publishing = any(
            isinstance(row, DataPublication) and row.state == "PUBLISHED" for row in db.dirty
        )
        original(db)
        if publishing and not lost:
            lost.append(True)
            raise OperationalError(
                "synthetic", {}, OSError("commit response lost"), connection_invalidated=True
            )

    monkeypatch.setattr(Session, "commit", commit)

    def pipeline(db, job, *_args, **_kwargs):
        stage_all(db, job)
        update_job(db, job, status="SUCCESS")

    key = _execute_synthetic_pipeline(factory, monkeypatch, pipeline)
    with factory() as db:
        assert lost == [True]
        assert db.get(JobRun, key).status == "SUCCESS"
        assert db.get(DataPublication, key).state == "PUBLISHED"
        assert db.scalar(select(func.count()).select_from(DataPublicationPreimage)) == 8
        assert db.scalar(select(m.StockFactorDaily.calc_run_id)) == key


def test_diagnostic_is_read_only_and_never_proves_remote_process_exit(publication_db):
    from app.services.data_job_diagnostics import diagnose_data_job

    factory, engine = publication_db
    with candidate(factory, engine) as (db, job):
        stage_all(db, job)
        token = str(job.execution_token)
        with factory() as incident:
            report = diagnose_data_job(incident, job.id)
            assert report["blocks_data_lane"] and report["process_exit_proven"] is False
            assert token not in str(report)
            assert report["publication"]["state"] == "PREPARING"
            assert len(report["candidates"]) == 8
            assert incident.scalar(text("SHOW transaction_read_only")) == "on"
        assert db.get(JobRun, job.id).status == "RUNNING"
        update_job(db, job, status="CANCELLED")


def test_cancelled_recalculation_keeps_previously_published_same_key(publication_db, monkeypatch):
    factory, _engine = publication_db
    with factory() as db:
        old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
        db.add(old)
        db.flush()
        db.add(
            StockFactorDaily(
                trade_date=DAY,
                ts_code="TEST.SZ",
                adj_close=10,
                eligible=True,
                calc_run_id=old.id,
                calculated_at=datetime.now(UTC),
            )
        )
        db.commit()
        old_id = old.id
        job = create_queued_ingestion_job(
            db,
            "recalculate",
            DAY,
            step="queued",
            metadata={"start": DAY.isoformat(), "end": DAY.isoformat(), "evaluate_signals": False},
        )
        key = claim_next_job(db, "publication-test")
        assert key == job.id
        claim = db.info["data_claim"]

    import app.services.job_worker as worker

    monkeypatch.setattr(worker, "SessionLocal", factory)

    def cancelled_run(db, job, *_args, **_kwargs):
        replace_slice_rows(
            db,
            StockFactorDaily,
            [
                {
                    "trade_date": DAY,
                    "ts_code": "TEST.SZ",
                    "adj_close": 20,
                    "eligible": True,
                    "calc_run_id": job.id,
                    "calculated_at": datetime.now(UTC),
                }
            ],
            scope_filters=[StockFactorDaily.trade_date == DAY],
            key_columns=["trade_date", "ts_code"],
        )
        db.commit()
        # This separate public reader must still see A at a committed B checkpoint.
        with factory() as reader:
            row = reader.scalar(select(StockFactorDaily))
            assert (row.adj_close, row.calc_run_id) == (10, old_id)
        update_job(db, job, status="CANCELLED")

    monkeypatch.setattr(worker, "run_recalculation", cancelled_run)
    with factory() as db:
        execute_claimed_job(db, key, expected_worker=claim[1], expected_token=claim[2])
    with factory() as reader:
        row = reader.scalar(select(StockFactorDaily))
        assert (row.adj_close, row.calc_run_id) == (10, old_id)
        assert reader.get(JobRun, key).status == "CANCELLED"
