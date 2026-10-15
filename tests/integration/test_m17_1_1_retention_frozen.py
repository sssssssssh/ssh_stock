import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
import sqlalchemy as sa
from app.models import Base
from app.models.auth import AppUser
from app.models.job import JobRun
from app.models.paper import DecisionObservation
from app.services.decision.application import DecisionApplication
from app.services.paper.records import make_record
from app.services.retention import run_retention
from app.services.retention_lineage import JOB_REFERENCES
from sqlalchemy.exc import IntegrityError

from tests.integration.m17_1_support import dirty_paper as dirty_paper
from tests.integration.m17_support import DAY, NOW, settings
from tests.integration.test_m17_1_1_retention import ENABLED, migrate, old_job
from tests.integration.test_m17_1_1_retention import retention_db as retention_db
from tests.integration.test_m17_1_paper_continuity import corrected_and_recomputed_source


def snapshot(db, source_id):
    owner = AppUser(username=uuid.uuid4().hex, password_hash="synthetic", is_active=True)
    db.add(owner)
    db.flush()
    key = uuid.uuid4().hex
    row = make_record(
        DecisionObservation, owner.id, key, now=NOW,
        signal_date=DAY, source_status="READY", asof_cutoff=NOW, ready_at=NOW,
        strategy_identity_hash="a" * 64, request_id=key, request_hash="b" * 64,
        data={"candidates": [{"calc_run_id": str(source_id)}]},
    )
    db.add(row)
    db.flush()
    return row.id


def raw_snapshot(db, identity):
    return db.execute(sa.select(
        DecisionObservation.record_hash, sa.cast(DecisionObservation.record_json, sa.Text),
    ).where(DecisionObservation.id == identity)).one()


def test_real_frozen_observation_keeps_job_after_all_typed_source_rows_are_replaced(dirty_paper):
    from app.domain.decision.requests import CreateObservation

    factory, _, owner, _, _ = dirty_paper
    with factory() as db:
        row = DecisionApplication(db, settings(), clock=lambda: NOW).observe(
            owner, CreateObservation(request_id="frozen-lineage", signal_date=DAY),
        )
        old = uuid.UUID(row.record_json["data"]["candidates"][0]["calc_run_id"])
        frozen = raw_snapshot(db, row.id)
        corrected_and_recomputed_source(db, DAY)
        new_id = db.scalar(sa.select(Base.metadata.tables["stock_factor_daily"].c.calc_run_id)
                           .where(Base.metadata.tables["stock_factor_daily"].c.trade_date == DAY)
                           .limit(1))
        # Replace the old quality producer too, so no typed reference masks this regression.
        quality = Base.metadata.tables["data_quality_daily"]
        db.execute(sa.update(quality).where(quality.c.job_id == old).values(job_id=new_id))
        db.commit()
        for table, column in JOB_REFERENCES:
            source = Base.metadata.tables[table]
            assert db.scalar(sa.select(sa.func.count()).select_from(source).where(
                source.c[column] == old,
            )) == 0
        result = run_retention(db, now=NOW + timedelta(days=400), policy=ENABLED)
        assert not result["blocked"] and db.get(JobRun, old) is not None
        assert raw_snapshot(db, row.id) == frozen


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED", "PARTIAL", "CANCELLED"])
def test_frozen_only_reference_protects_all_statuses_without_granting_validity(
    retention_db, status,
):
    factory, _ = retention_db
    with factory() as db:
        identity = old_job(db, age=400, status=status)
        row_id = snapshot(db, identity)
        db.commit()
        before = raw_snapshot(db, row_id)
        result = run_retention(db, now=NOW, policy=ENABLED)
        assert not result["blocked"] and result["protected_referenced_jobs"] == 1
        assert result["successful_jobs"] == result["failed_jobs"] == 0
        assert db.get(JobRun, identity).status == status
        assert raw_snapshot(db, row_id) == before


def test_frozen_writer_first_key_share_blocks_concurrent_retention(retention_db):
    factory, _ = retention_db
    with factory() as db:
        identity = old_job(db)
    with factory() as writer:
        row_id = snapshot(writer, identity)

        def clean():
            with factory() as db:
                return run_retention(db, now=NOW, policy=ENABLED)

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(clean).result(timeout=20)
        assert not result["blocked"] and result["successful_jobs"] == 0
        writer.commit()
    with factory() as db:
        assert db.get(JobRun, identity) is not None
        assert db.get(DecisionObservation, row_id) is not None


def test_new_frozen_reference_cannot_point_to_a_deleted_job(retention_db):
    factory, _ = retention_db
    with factory() as db:
        identity = old_job(db)
        assert run_retention(db, now=NOW, policy=ENABLED)["successful_jobs"] == 1
        with pytest.raises(IntegrityError) as error:
            snapshot(db, identity)
        assert error.value.orig.sqlstate == "23503"
        db.rollback()
        assert db.scalar(sa.select(sa.func.count()).select_from(DecisionObservation)) == 0


@pytest.mark.parametrize("invalid", [False, True])
def test_legacy_frozen_loss_or_invalid_uuid_is_diagnosed_without_snapshot_rewrite(
    retention_db, invalid,
):
    factory, engine = retention_db
    migrate(engine, "0054_retention_lineage", downgrade=True)
    lost = uuid.uuid4()
    with factory() as db:
        identity = snapshot(db, "private-text-must-not-be-projected" if invalid else lost)
        db.commit()
        before = raw_snapshot(db, identity)
    migrate(engine, "head")
    with factory() as db:
        result = run_retention(db, now=NOW, dry_run=True, include_diagnostics=True)
        if invalid:
            assert result["error_code"] == "RETENTION_INVALID_FROZEN_PROVENANCE"
            assert "private-text-must-not-be-projected" not in str(result)
        else:
            assert not result["blocked"] and result["missing_provenance_references"] == 1
            assert result["missing_reference_samples"][0]["job_id"] == str(lost)
        assert raw_snapshot(db, identity) == before
        assert db.get(JobRun, lost) is None


def test_source_disappears_between_capture_and_freeze_returns_existing_fail_closed_error(
    dirty_paper,
):
    from types import SimpleNamespace

    from app.domain.decision.contracts import PaperError
    from app.domain.decision.requests import CreateObservation

    factory, _, owner, _, _ = dirty_paper
    with factory() as db:
        service = DecisionApplication(db, settings(), clock=lambda: NOW)
        reader = service.source

        def race(*args, **kwargs):
            captured = reader.capture(*args, **kwargs)
            old = uuid.UUID(str(captured["candidates"][0]["calc_run_id"]))
            with factory() as repair:
                corrected_and_recomputed_source(repair, DAY)
                factor = Base.metadata.tables["stock_factor_daily"]
                current = repair.scalar(sa.select(factor.c.calc_run_id).where(
                    factor.c.trade_date == DAY,
                ).limit(1))
                quality = Base.metadata.tables["data_quality_daily"]
                repair.execute(sa.update(quality).where(quality.c.job_id == old)
                               .values(job_id=current))
                repair.commit()
                result = run_retention(repair, now=NOW + timedelta(days=400), policy=ENABLED)
                assert not result["blocked"] and repair.get(JobRun, old) is None
            return captured

        service.source = SimpleNamespace(capture=race)
        with pytest.raises(PaperError, match="SOURCE_CALC_LINEAGE_UNAVAILABLE"):
            service.observe(owner, CreateObservation(request_id="freeze-race", signal_date=DAY))
        assert db.scalar(sa.select(sa.func.count()).select_from(DecisionObservation)) == 0
