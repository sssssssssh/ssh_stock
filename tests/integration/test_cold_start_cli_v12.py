"""Valid PG17 connections prove CLI refusal is zero-write, with and without queued work."""

import app.cli as cli_module
import pytest
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services.analysis_filters import opportunity_identity_filters
from app.services.job_guard import create_queued_ingestion_job, data_queue_identity
from app.services.job_worker import claim_next_job
from sqlalchemy import func, select, text
from typer.testing import CliRunner

from tests.integration.test_data_publication import DAY, MODELS, m, publication_db, seed_published
from tests.unit.test_cli_derived_safety import COMMANDS

__all__ = ["publication_db"]


def snapshot(factory):
    with factory() as db:
        return {
            table: db.scalar(
                text(
                    "SELECT md5(coalesce("
                    "jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text)::text,'[]')) "
                    f'FROM public."{table}" t'
                )
            )
            for table in [model.__tablename__ for model in MODELS]
            + [
                "job_run",
                "data_publication",
                "data_publication_row",
                "data_publication_source",
                "data_publication_scope",
                "data_publication_preimage",
            ]
        }


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("active", [False, True])
def test_unsafe_cli_with_valid_database_is_zero_write(publication_db, monkeypatch, command, active):
    factory, _ = publication_db
    seed_published(factory)
    if active:
        with factory() as db:
            create_queued_ingestion_job(
                db,
                "recalculate",
                DAY,
                step="queued",
                metadata={
                    "start": DAY.isoformat(),
                    "end": DAY.isoformat(),
                },
            )
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    before = snapshot(factory)
    result = CliRunner().invoke(cli_module.cli, command)
    assert result.exit_code == 1
    assert "UNSAFE_DIRECT_DERIVED_WRITE_DISABLED" in result.output
    assert snapshot(factory) == before


def test_explicit_full_cli_is_deduplicated_and_cancelable(publication_db, monkeypatch):
    from app.api.v1.jobs import cancel_job

    factory, _ = publication_db
    monkeypatch.setattr(cli_module, "SessionLocal", factory)
    command = [
        "recalculate",
        "--start",
        DAY.isoformat(),
        "--end",
        DAY.isoformat(),
        "--no-evaluate-signals",
    ]
    for _ in range(2):
        assert CliRunner().invoke(cli_module.cli, command).exit_code == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(JobRun)) == 1
        job = db.scalar(select(JobRun))
        assert (
            job.status == "QUEUED" and job.job_metadata["queue_identity"] == data_queue_identity()
        )
        cancel_job(job.id, db)
        assert db.get(JobRun, job.id).status == "CANCELLED"
        assert db.scalar(select(func.count()).select_from(DataPublication)) == 0


def test_old_identity_stays_readable_but_never_counts_as_current(publication_db):
    from app.core.config import get_settings
    from app.services.analysis_identity import FACTOR_CALC_VERSION, OPPORTUNITY_CALC_VERSION

    factory, _ = publication_db
    old = seed_published(factory)
    with factory() as db:
        for model in MODELS[:8]:
            if model is not m.StockTradeStatusDaily:
                db.execute(
                    model.__table__.update().values(
                        calc_version=model.__tablename__.split("_daily")[0] + "_legacy_v1"
                    )
                )
        db.execute(m.StockFactorDaily.__table__.update().values(calc_version="factor_v1"))
        db.execute(m.StockOpportunityDaily.__table__.update().values(calc_version="opportunity_v1"))
        db.commit()
        before = snapshot(factory)
        assert db.scalar(select(m.StockFactorDaily.calc_run_id)) == old
        assert db.scalar(select(m.StockFactorDaily.calc_version)) == "factor_v1"
        assert FACTOR_CALC_VERSION != "factor_v1" and OPPORTUNITY_CALC_VERSION != "opportunity_v1"
        identity = data_queue_identity()
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.StockFactorDaily)
                .where(
                    m.StockFactorDaily.calc_version == FACTOR_CALC_VERSION,
                    m.StockFactorDaily.config_hash == identity["analysis"],
                )
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.StockOpportunityDaily)
                .where(
                    *opportunity_identity_filters(
                        algo_version=get_settings().algo_version,
                        strategy_hash=identity["analysis"],
                        opportunity_hash=identity["opportunity"],
                    )
                )
            )
            == 0
        )
        assert snapshot(factory) == before


def test_pre_upgrade_queue_identity_is_rejected_not_replayed(publication_db):
    factory, _ = publication_db
    with factory() as db:
        job = create_queued_ingestion_job(
            db,
            "recalculate",
            DAY,
            step="queued",
            metadata={
                "start": DAY.isoformat(),
                "end": DAY.isoformat(),
            },
        )
        job.job_metadata = {
            **job.job_metadata,
            "queue_identity": {
                **data_queue_identity(),
                "factor": "factor_v1",
            },
        }
        db.commit()
        assert claim_next_job(db, "version-worker") is None
        db.refresh(job)
        assert job.status == "FAILED" and "JOB_CONFIG_CHANGED" in job.error_message
        assert db.scalar(select(func.count()).select_from(DataPublication)) == 0
