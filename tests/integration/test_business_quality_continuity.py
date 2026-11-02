"""Ten real recalculation roots, with existing switches off, on marked UUID PG17."""

import json
from datetime import timedelta

from app.core.config import get_settings
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.services import job_worker
from app.services.recalculation import create_recalculation_job

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_recalc_performance import seed


def test_ten_different_real_roots_are_fifo_idempotent_and_published(monkeypatch, record_property):
    with isolated_v14_database(monkeypatch) as (factory, engine):
        days = seed(factory, include_closed=False, history_days=420)
        settings = get_settings()
        assert not any(
            getattr(settings, name)
            for name in (
                "factor_input_reuse_enabled",
                "raw_preflight_batch_enabled",
                "factor_cpu_optimization_enabled",
                "ab_merge_read_enabled",
            )
        )
        monkeypatch.setattr(job_worker, "SessionLocal", factory)
        targets = [d for d in days[-20:] if d.weekday() < 5][-10:]
        queued, receipts = [], []
        with factory() as db:
            for day in targets:
                job = create_recalculation_job(
                    db,
                    start=day - timedelta(days=1),
                    end=day,
                    evaluate_signals=False,
                    mode="manual",
                )
                duplicate = create_recalculation_job(
                    db,
                    start=day - timedelta(days=1),
                    end=day,
                    evaluate_signals=False,
                    mode="manual",
                )
                assert duplicate.id == job.id
                queued.append(job.id)
            for identity in queued:
                assert job_worker.claim_next_job(db, "biz02-isolated-continuity") == identity
                db.refresh(db.get(JobRun, identity))
                job = db.get(JobRun, identity)
                job_worker.execute_claimed_job(
                    db, identity, expected_worker=job.worker_id, expected_token=job.execution_token
                )
                db.expire_all()
                result = db.get(JobRun, identity)
                publication = db.get(DataPublication, identity)
                receipts.append(
                    dict(
                        root_id=str(identity),
                        start=str(result.started_at),
                        finished=str(result.finished_at),
                        status=result.status,
                        metadata=result.job_metadata.get("calculation_execution"),
                        publication=publication.state if publication else None,
                        publication_identity=str(publication.job_id) if publication else None,
                    )
                )
                record_property("roots", json.dumps(receipts, default=str))
                assert result.status == "SUCCESS", result.error_message
                assert publication.state == "PUBLISHED"
                assert publication.row_counts["stock_factor_daily"] > 0
            assert job_worker.claim_next_job(db, "biz02-isolated-continuity") is None
        assert len({r["root_id"] for r in receipts}) == 10
        assert (
            len(
                {
                    (r["metadata"]["request"]["start"], r["metadata"]["request"]["end"])
                    for r in receipts
                }
            )
            == 10
        )
