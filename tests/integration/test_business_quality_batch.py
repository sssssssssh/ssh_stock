"""Retained rejected-candidate proofs, plus separate current-code safety checks.

The six candidate cases explicitly load the immutable measured implementation;
they are not evidence that batching is enabled in current production code.
"""

import hashlib
import importlib.util
import subprocess
import sys
from copy import deepcopy

import pytest
from app.core.config import get_settings
from app.models import market_data as m
from app.models.data_publication import DataPublicationRow
from app.repositories.upsert import upsert_rows
from app.services.data_publication import PublicationWorkspace
from sqlalchemy import select, text

from scripts.v14_test_database import isolated_v14_database
from tests.integration.test_data_publication import DAY, candidate, seed_published

DATASETS = (
    "stock_daily_vs_expected",
    "adj_vs_daily",
    "basic_vs_daily",
    "factor_vs_daily",
    "state_vs_factor",
    "sector_factor_vs_expected",
)
REJECTED_SHA = "6c4096e5de77368c67ff1c2cff7ddd3285a8e56e"


@pytest.fixture
def quality(tmp_path, monkeypatch, request):
    source = subprocess.check_output(
        ["git", "show", REJECTED_SHA + ":backend/app/services/quality/daily_quality.py"]
    )
    path = tmp_path / "rejected_candidate_quality.py"
    path.write_bytes(source)
    name = "biz02_rejected_quality"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    request.node.user_properties.extend(
        [
            ("implementation_subject", "REJECTED_CANDIDATE_NOT_CURRENT"),
            ("implementation_sha", REJECTED_SHA),
            ("quality_source_sha256", hashlib.sha256(source).hexdigest()),
        ]
    )
    return module


@pytest.fixture
def isolated(monkeypatch):
    with isolated_v14_database(monkeypatch) as database:
        yield database


def seed(factory):
    old = seed_published(factory)
    with factory() as db:
        db.add(m.StockBasic(ts_code="TEST.SZ", list_date=DAY))
        db.add(m.StockDaily(trade_date=DAY, ts_code="TEST.SZ", close=10))
        upsert_rows(
            db,
            m.DataQualityDaily,
            [
                dict(
                    trade_date=DAY,
                    dataset=name,
                    status="PASS",
                    job_id=old,
                    issue_codes={"original": name},
                )
                for name in DATASETS
            ],
            ["trade_date", "dataset"],
        )
        db.commit()
    return old


def patches(db, job):
    return list(
        db.scalars(
            select(DataPublicationRow)
            .where(
                DataPublicationRow.publication_id == job.id,
                DataPublicationRow.table_name == "data_quality_daily",
            )
            .order_by(DataPublicationRow.row_data["id"].as_integer())
        )
    )


def test_quality_uses_two_bounded_candidate_batches_per_day(isolated, monkeypatch, quality):
    factory, engine = isolated
    old = seed(factory)
    original, sizes = PublicationWorkspace.upsert, []

    def observe(ws, model, payload, *args, **kwargs):
        if model is m.DataQualityDaily:
            sizes.append(len(payload))
        return original(ws, model, payload, *args, **kwargs)

    monkeypatch.setattr(PublicationWorkspace, "upsert", observe)
    with candidate(factory, engine) as (db, job):
        result = quality.record_cross_table_quality(db, DAY, job_id=job.id)
        assert result.has_error  # B cannot borrow published A's factors.
        rows = patches(db, job)
        assert [row.row_data["dataset"] for row in rows] == list(DATASETS)
        assert [row.row_data["id"] for row in rows] == list(range(1, 7))
        assert all(row.row_data["job_id"] == str(job.id) for row in rows)
        assert all(row.base_row["job_id"] == str(old) for row in rows)
        assert sizes == [5, 1]


def test_repeat_keeps_ids_first_preimages_and_readers_only_see_a(isolated, quality):
    factory, engine = isolated
    old = seed(factory)
    with candidate(factory, engine) as (db, job):
        quality.record_cross_table_quality(db, DAY, job_id=job.id)
        before = [(row.row_key, row.row_data, row.base_row) for row in patches(db, job)]
        db.commit()
        quality.record_cross_table_quality(db, DAY, job_id=job.id)
        after = [(row.row_key, row.row_data, row.base_row) for row in patches(db, job)]

        # checked_at is transaction-time audit, not a financial value or identity.
        def stable(items):
            return [
                (key, {k: v for k, v in data.items() if k != "checked_at"}, base)
                for key, data, base in items
            ]

        assert stable(before) == stable(after)
        with factory() as reader:
            rows = list(reader.scalars(select(m.DataQualityDaily)))
            assert len(rows) == 6
            assert all(row.status == "PASS" and row.job_id == old for row in rows)


def test_sector_failure_still_observes_five_prior_quality_rows(isolated, monkeypatch, quality):
    factory, engine = isolated
    seed(factory)
    with candidate(factory, engine) as (db, job):

        def fail(*args, **kwargs):
            assert len(patches(db, job)) == 5
            raise ValueError("SYNTHETIC_SECTOR_FAILURE")

        monkeypatch.setattr(quality, "check_sector_factor_coverage", fail)
        with pytest.raises(ValueError, match="SYNTHETIC_SECTOR_FAILURE"):
            quality.record_cross_table_quality(db, DAY, job_id=job.id)


def test_malformed_later_threshold_preserves_valid_prefix(isolated, quality):
    factory, engine = isolated
    seed(factory)
    strategy = deepcopy(get_settings().strategy)
    strategy["data_quality"]["cross_table"]["factor_vs_daily"]["warning_coverage_rate"] = None
    with candidate(factory, engine) as (db, job):
        with pytest.raises(TypeError):
            quality.record_cross_table_quality(db, DAY, job_id=job.id, strategy=strategy)
        assert [row.row_data["dataset"] for row in patches(db, job)] == list(DATASETS[:3])


def test_mid_store_failure_rolls_back_b_without_touching_a(isolated, monkeypatch, quality):
    factory, engine = isolated
    old = seed(factory)
    original = PublicationWorkspace._store_batch
    calls = []

    def store(ws, rows):
        calls.append(len(rows))
        if len(calls) == 2:
            raise ValueError("SYNTHETIC_STORE_FAILURE")
        return original(ws, rows)

    monkeypatch.setattr(PublicationWorkspace, "_store_batch", store)
    with candidate(factory, engine) as (db, job):
        with pytest.raises(ValueError, match="SYNTHETIC_STORE_FAILURE"):
            quality.record_cross_table_quality(db, DAY, job_id=job.id)
        db.rollback()
        assert patches(db, job) == []
        with factory() as reader:
            assert all(
                row.job_id == old and row.status == "PASS"
                for row in reader.scalars(select(m.DataQualityDaily))
            )


def test_standalone_quality_keeps_original_six_write_order(isolated, monkeypatch, quality):
    factory, engine = isolated
    old = seed(factory)
    captured, original = [], quality.upsert_rows

    def observe(db, model, payload, *args, **kwargs):
        captured.append([row["dataset"] for row in payload])
        return original(db, model, payload, *args, **kwargs)

    monkeypatch.setattr(quality, "upsert_rows", observe)
    with factory() as db:
        quality.record_cross_table_quality(db, DAY, job_id=old)
        assert captured == [[name] for name in DATASETS]
        assert db.scalar(text("SELECT count(*) FROM data_quality_daily")) == 6


def test_live_quality_preserves_fields_ids_preimages_and_a_visibility(isolated):
    from app.services.quality.daily_quality import record_cross_table_quality

    factory, engine = isolated
    old = seed(factory)
    with candidate(factory, engine) as (db, job):
        result = record_cross_table_quality(db, DAY, job_id=job.id)
        assert result.has_error
        rows = patches(db, job)
        assert [row.row_data["dataset"] for row in rows] == list(DATASETS)
        assert [row.row_data["id"] for row in rows] == list(range(1, 7))
        assert all(row.row_data["job_id"] == str(job.id) for row in rows)
        assert all(row.base_row["job_id"] == str(old) for row in rows)
        with factory() as reader:
            assert all(
                row.status == "PASS" and row.job_id == old
                for row in reader.scalars(select(m.DataQualityDaily))
            )


def test_live_sector_failure_preserves_existing_prefix(isolated, monkeypatch):
    from app.services.quality import daily_quality as live

    factory, engine = isolated
    seed(factory)
    with candidate(factory, engine) as (db, job):

        def fail(*args, **kwargs):
            assert len(patches(db, job)) == 5
            raise ValueError("SYNTHETIC_LIVE_SECTOR_FAILURE")

        monkeypatch.setattr(live, "check_sector_factor_coverage", fail)
        with pytest.raises(ValueError, match="SYNTHETIC_LIVE_SECTOR_FAILURE"):
            live.record_cross_table_quality(db, DAY, job_id=job.id)
