"""BIZ-POLICY-01 real Worker/PG17 calculations, never a business connection."""

import json
import subprocess
import threading
import time
from copy import deepcopy
from datetime import date
from types import SimpleNamespace as NS

import pandas as pd
import pytest
from app.core.config import get_settings
from app.models import market_data as m
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from app.repositories.upsert import upsert_rows
from app.services import calculation_policy as cp
from app.services import job_worker as worker
from app.services.data_publication import MODELS
from app.services.factors.service import FactorService
from app.services.job_guard import create_queued_ingestion_job
from app.services.recalculation import create_recalculation_job
from sqlalchemy import select, update

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_business_recalc_performance import seed
from tests.integration.test_data_publication import sample_row


@pytest.fixture
def repository(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True,
                              capture_output=True).stdout

    git("init")
    git("config", "user.name", "Policy Test")
    git("config", "user.email", "policy-test@example.invalid")
    for path in ("backend/module.py", "config/policy.yaml", "docs/note.md"):
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("initial\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "isolated source")
    monkeypatch.setattr(cp, "ROOT_DIR", tmp_path)
    return tmp_path, git


class StopIsolatedWorker(BaseException):
    pass


def run_until_idle(factory, monkeypatch):
    def idle(_):
        raise StopIsolatedWorker

    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker, "time", NS(monotonic=time.monotonic, sleep=idle))
    # Only the unrelated service liveness publisher is disabled. Claim, dispatch,
    # job heartbeat, calculators, quality, CAS and publication are production code.
    monkeypatch.setattr(worker, "start_service_heartbeat", lambda _: (
        threading.Event(), NS(join=lambda **_: None)))
    with pytest.raises(StopIsolatedWorker):
        worker.run_worker()
    assert cp.worker_source.get() is None
    assert cp.active_policy.get() is None


def published(factory):
    with factory() as db:
        return {model.__tablename__: sorted(json.dumps(dict(row), default=str, sort_keys=True)
            for row in db.execute(select(model.__table__)).mappings()) for model in MODELS}


@pytest.mark.parametrize("change", ["head", "dirty", "backend", "config", *cp.FLAGS])
def test_resident_worker_git_only_continues_but_real_drift_aborts_a_unchanged(
    repository, monkeypatch, change,
):
    root, git = repository
    with isolated_v14_database(monkeypatch) as (factory, engine):
        days = seed(factory, include_closed=False, history_days=420)
        settings = get_settings()
        for flag in cp.FLAGS:
            monkeypatch.setattr(settings, flag, True)
        with factory() as db:
            old = JobRun(job_type="recalculate", status="SUCCESS", job_metadata={})
            db.add(old)
            db.flush()
            payload = sample_row(m.StockFactorDaily, old.id, value=123, day=days[-1])
            payload["ts_code"] = "000001.SZ"
            upsert_rows(db, m.StockFactorDaily, [payload], ["trade_date", "ts_code"])
            db.commit()
            job = create_recalculation_job(db, start=days[-2], end=days[-1],
                                          evaluate_signals=False, mode="manual")
            key = job.id
            next_key = None
            if change in {"head", "dirty", "backend", "config"}:
                next_key = create_recalculation_job(db, start=days[-3], end=days[-1],
                    evaluate_signals=False, mode="manual").id
                assert next_key != key
        before, original_source = published(factory), cp.runtime_source()
        original, changed = FactorService.recalc, []

        def drift(service, start, end, calc_run_id=None):
            count = original(service, start, end, calc_run_id=calc_run_id)
            if not changed:
                changed.append(True)
                if change == "head":
                    (root / "docs/note.md").write_text("unrelated\n", encoding="utf-8")
                    git("add", ".")
                    git("commit", "-m", "unrelated docs")
                elif change == "dirty":
                    (root / ".codex_tmp").mkdir()
                    (root / ".codex_tmp/progress.log").write_text("audit\n", encoding="utf-8")
                elif change in {"backend", "config"}:
                    file = "backend/module.py" if change == "backend" else "config/policy.yaml"
                    (root / file).write_text("real source drift\n", encoding="utf-8")
                else:
                    monkeypatch.setattr(settings, change, False)
            return count

        monkeypatch.setattr(FactorService, "recalc", drift)
        run_until_idle(factory, monkeypatch)
        assert changed
        with factory() as db:
            job, ledger = db.get(JobRun, key), db.get(DataPublication, key)
            evidence = job.job_metadata["calculation_execution"]
            assert evidence["source"] == original_source
            assert evidence["root_job_id"] == evidence["job_id"] == str(key)
            assert evidence["flags"] == dict.fromkeys(cp.FLAGS, True)
            assert evidence["reads"]["factors.stock_daily"]["rows"] > 0
            assert evidence["stages"] and evidence["sql"]
            if change in {"head", "dirty"}:
                assert job.status == "SUCCESS" and ledger.state == "PUBLISHED"
                assert evidence["source_diagnostics"]["git_metadata_changed"]
                assert evidence["source_diagnostics"]["observed_source"] != original_source
                assert job.job_metadata.get("policy_change") is None
            else:
                reason = "BUSINESS_SOURCE_CHANGED" if change in {"backend", "config"} \
                    else "OPTIMIZATION_FLAGS_CHANGED"
                assert job.status == "FAILED" and ledger.state == "ABORTED"
                assert reason in job.error_message
                assert "CALCULATION_POLICY_CHANGED" in job.error_message
                assert job.job_metadata["policy_change"]["policy_change_reason"] == reason
                assert published(factory) == before
            if next_key is not None:
                following = db.get(JobRun, next_key)
                if change in {"head", "dirty"}:
                    assert following.status == "SUCCESS"
                    assert db.get(DataPublication, next_key).state == "PUBLISHED"
                    execution = following.job_metadata["calculation_execution"]
                    assert execution["source"] == original_source
                else:
                    assert following.status == "FAILED"
                    assert "BUSINESS_SOURCE_CHANGED" in following.error_message
                    assert db.get(DataPublication, next_key) is None


@pytest.mark.parametrize("damage", ["source", "missing_hash", "version", "range", "null"])
def test_bad_old_job_freeze_keeps_old_evidence_and_concurrent_metadata(
    repository, monkeypatch, damage,
):
    with isolated_v14_database(monkeypatch) as (factory, engine):
        days = seed(factory, include_closed=False, history_days=25)
        with factory() as db:
            job = create_recalculation_job(db, start=days[-2], end=days[-1],
                                          evaluate_signals=False, mode="manual")
            cp.ExecutionPolicy.freeze(job, get_settings())
            old = deepcopy(job.job_metadata["calculation_execution"])
            if damage == "source":
                old["source"]["source_sha256"] = "0" * 64
            elif damage == "missing_hash":
                old["source"].pop("source_sha256")
            elif damage == "version":
                old["schema_version"] = "unknown"
            elif damage == "range":
                old["request"]["start"] = "1900-01-01"
            else:
                old = None
            job.job_metadata = {**job.job_metadata, "calculation_execution": old}
            db.commit()
            key = job.id
            assert worker.claim_next_job(db, "isolated-policy") == key
            db.refresh(job)
            # Independent committed telemetry after this Session loaded the Job.
            with factory() as observer:
                observer.execute(update(JobRun).where(JobRun.id == key).values(
                    job_metadata=JobRun.job_metadata.op("||")({
                        "independent_heartbeat": "retained"})))
                observer.commit()
            original_update = worker.update_job

            def concurrent_update(db, row, **kwargs):
                with factory() as observer:
                    observer.execute(update(JobRun).where(JobRun.id == key).values(
                        job_metadata=JobRun.job_metadata.op("||")({"late_heartbeat": "retained"})))
                    observer.commit()
                return original_update(db, row, **kwargs)

            monkeypatch.setattr(worker, "update_job", concurrent_update)
            worker.execute_claimed_job(db, key, expected_worker=job.worker_id,
                                       expected_token=job.execution_token)
            db.expire_all()
            failed = db.get(JobRun, key)
            assert failed.status == "FAILED"
            assert failed.job_metadata["calculation_execution"] == old
            assert failed.job_metadata["independent_heartbeat"] == "retained"
            assert failed.job_metadata["late_heartbeat"] == "retained"
            assert failed.job_metadata["policy_change"]["policy_change_reason"] == \
                "JOB_FROZEN_IDENTITY_MISMATCH"
            assert "JOB_FROZEN_IDENTITY_MISMATCH" in failed.error_message
            assert db.get(DataPublication, key) is None
            assert worker.claim_next_job(db, "no-auto-retry") is None


class SyntheticReplayProvider:
    """Provider fixture replays only this test's own Raw facts; no network."""

    def __init__(self, factory):
        self.factory = factory

    def rows(self, model, *conditions):
        with self.factory() as db:
            values = [dict(row) for row in db.execute(select(model.__table__).where(*conditions))
                      .mappings()]
        for row in values:
            for key, value in row.items():
                if isinstance(value, date):
                    row[key] = value.strftime("%Y%m%d")
        return pd.DataFrame(values, columns=list(model.__table__.c.keys()))

    def get_trade_calendar(self, start, end):
        return self.rows(m.TradeCalendar, m.TradeCalendar.cal_date.between(start, end))

    def get_stock_basic(self):
        return self.rows(m.StockBasic)

    def get_daily(self, day):
        return self.rows(m.StockDaily, m.StockDaily.trade_date == day)

    def get_adj_factor(self, day):
        return self.rows(m.StockAdjFactor, m.StockAdjFactor.trade_date == day)

    def get_daily_basic(self, day):
        return self.rows(m.StockDailyBasic, m.StockDailyBasic.trade_date == day)

    def get_index_daily(self, day, codes):
        return self.rows(m.IndexDaily, m.IndexDaily.trade_date == day,
                         m.IndexDaily.ts_code.in_(codes))

    def get_stock_st(self, day):
        return pd.DataFrame(columns=["ts_code", "trade_date", "type", "name"])

    def get_suspend_daily(self, day):
        return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_type", "suspend_timing"])

    def get_stock_limit(self, day):
        return self.rows(m.StockLimitDaily, m.StockLimitDaily.trade_date == day)

    def get_ths_concepts(self):
        return pd.DataFrame()

    def get_ths_daily(self, day):
        return pd.DataFrame()

    def get_ths_concept_moneyflow(self, day):
        return pd.DataFrame()

    def get_limit_concept_list(self, day):
        return pd.DataFrame()


@pytest.mark.parametrize("kind", ["daily", "catchup"])
def test_daily_catchup_real_calculators_keep_root_identity_and_git_audit(
    repository, monkeypatch, kind,
):
    root, git = repository
    with isolated_v14_database(monkeypatch) as (factory, engine):
        days = seed(factory, include_closed=False, history_days=420)
        settings = get_settings()
        scheduler = deepcopy(settings.app_config)
        scheduler["app"]["scheduler"].update(max_catchup_trade_days=2, refresh_recent_trade_days=2)
        monkeypatch.setattr(settings, "app_config", scheduler)
        for flag in cp.FLAGS:
            monkeypatch.setattr(settings, flag, False)
        monkeypatch.setattr(worker, "_provider", lambda _: SyntheticReplayProvider(factory))
        with factory() as db:
            key = create_queued_ingestion_job(db, kind, days[-1], metadata={
                "trade_date": days[-1].isoformat(), "evaluate_signals": False,
            }).id
        frozen, original, changed = cp.runtime_source(), FactorService.recalc, []

        def git_drift(service, start, end, calc_run_id=None):
            count = original(service, start, end, calc_run_id=calc_run_id)
            if not changed:
                changed.append(True)
                (root / "docs/note.md").write_text("unrelated\n", encoding="utf-8")
                git("add", ".")
                git("commit", "-m", "unrelated docs")
            return count

        monkeypatch.setattr(FactorService, "recalc", git_drift)
        run_until_idle(factory, monkeypatch)
        with factory() as db:
            job = db.get(JobRun, key)
            assert changed and job.status == "SUCCESS", job.error_message
            assert db.get(DataPublication, key).state == "PUBLISHED"
            children = list(db.scalars(select(JobRun).where(JobRun.parent_job_id == key)))
            if kind == "catchup":
                assert len(children) >= 2
            for row in [job, *children]:
                evidence = row.job_metadata["calculation_execution"]
                assert evidence["source"] == frozen
                assert evidence["root_job_id"] == str(key)
                assert evidence["job_id"] == str(row.id)
                assert evidence["counter_scope"] == "ROOT_CUMULATIVE_INCLUDING_CHILDREN"
                assert row.status == "SUCCESS"
            evidence = job.job_metadata["calculation_execution"]
            assert evidence["reads"]["factors.stock_daily"]["rows"] > 0
