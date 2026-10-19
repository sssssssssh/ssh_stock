"""Compare candidate bytes with the immutable 9a377e4 implementation, not a mock."""

import json
from datetime import UTC, datetime

import pytest
from app.models import market_data as m
from app.models.data_publication import DataPublicationRow
from app.repositories.job_run import update_job
from app.services import data_publication as publication
from sqlalchemy import select

from scripts.publication_candidate_benchmark_v13 import baseline_class
from tests.integration import test_data_publication as support
from tests.integration.test_data_publication import (  # noqa: F401
    publication_db,
)


def snapshot(db, job):
    result = []
    for row in db.scalars(
        select(DataPublicationRow)
        .where(DataPublicationRow.publication_id == job.id)
        .order_by(DataPublicationRow.table_name, DataPublicationRow.row_key)
    ):
        value = dict(
            table_name=row.table_name,
            row_key=row.row_key,
            row_data=row.row_data,
            base_row=row.base_row,
            is_deleted=row.is_deleted,
            source_id=str(row.source_id),
        )
        result.append(json.loads(json.dumps(value, default=str).replace(str(job.id), "ROOT")))
    return result


def test_all_core_candidates_match_frozen_baseline(publication_db, monkeypatch):  # noqa: F811
    factory, engine = publication_db
    support.seed_published(factory)
    outputs = []
    for cls in (baseline_class(), publication.PublicationWorkspace):
        monkeypatch.setattr(support, "PublicationWorkspace", cls)
        with support.candidate(factory, engine) as (db, job):
            for model in support.MODELS[:8]:
                row = support.sample_row(model, job.id, 20)
                row["calculated_at"] = datetime(2026, 9, 1, tzinfo=UTC)
                if "created_at" in model.__table__.c:
                    row["created_at"] = datetime(2026, 9, 1, tzinfo=UTC)
                ws = db.info["publication_workspace"]
                ws.upsert(model, [row], support.KEYS[model.__tablename__])
                row.update(
                    {
                        k: 30
                        for k in ("adj_close", "market_score", "heat_score", "opportunity_score")
                        if k in row
                    }
                )
                ws.upsert(model, [row], support.KEYS[model.__tablename__])
            outputs.append(snapshot(db, job))
            update_job(db, job, status="FAILED", step="synthetic golden sample complete")
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("mode", ["empty", "delete", "delete_rebuild", "new_delete_rebuild"])
def test_tombstone_and_repeated_update_match_baseline(publication_db, monkeypatch, mode):  # noqa: F811
    factory, engine = publication_db
    if mode != "empty":
        support.seed_published(factory)
    outputs = []
    for cls in (baseline_class(), publication.PublicationWorkspace):
        monkeypatch.setattr(support, "PublicationWorkspace", cls)
        with support.candidate(factory, engine) as (db, job):
            model = m.StockTradeStatusDaily
            row = support.sample_row(model, job.id)
            row["calculated_at"] = datetime(2026, 9, 1, tzinfo=UTC)
            if mode == "new_delete_rebuild":
                row["ts_code"] = "NEW.SZ"
            ws = db.info["publication_workspace"]
            ws.upsert(model, [row], support.KEYS[model.__tablename__])
            if "delete" in mode:
                key = tuple(row[k] for k in support.KEYS[model.__tablename__])
                ws.delete_keys(model, [key])
                assert ws._lookup(model, [row]) == {}
                if "rebuild" in mode:
                    row["tradable"] = False
                    ws.upsert(model, [row], support.KEYS[model.__tablename__])
                    assert ws._lookup(model, [row])[key]["tradable"] is False
                    ws.delete_keys(model, [key])
            outputs.append(snapshot(db, job))
            update_job(db, job, status="FAILED")
    assert outputs[0] == outputs[1]


def test_update_allowlist_null_preserve_and_json_merge(publication_db):  # noqa: F811
    factory, engine = publication_db
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        model = m.StrategySignal
        ws = db.info["publication_workspace"]
        row = support.sample_row(model, job.id)
        row.update(score=12.5, payload={"old": 1}, reason_codes={"first": True})
        keys = support.KEYS[model.__tablename__]
        ws.upsert(model, [row], keys)
        before = ws._lookup(model, [row])[tuple(row[k] for k in keys)]
        ws.upsert(
            model,
            [{**row, "score": None, "payload": {"new": None}, "reason_codes": {"forbidden": True}}],
            keys,
            update_columns=["score", "payload"],
            preserve_existing_on_null_columns=["score"],
            merge_json_columns=["payload"],
        )
        actual = ws._lookup(model, [row])[tuple(row[k] for k in keys)]
        assert actual["score"] == 12.5
        assert actual["payload"] == {"old": 1, "new": None}
        assert actual["reason_codes"] == before["reason_codes"]
        assert actual["id"] == before["id"]


def test_lookup_uses_native_types_and_only_own_publication(publication_db):  # noqa: F811
    from decimal import Decimal
    from uuid import UUID

    factory, engine = publication_db
    support.seed_published(factory)
    with support.candidate(factory, engine) as (db, job):
        ws = db.info["publication_workspace"]
        row = support.sample_row(m.StockFactorDaily, job.id)
        row.update(adj_close=Decimal("12.125"), eligible=True)
        ws.upsert(m.StockFactorDaily, [row], support.KEYS["stock_factor_daily"])
        actual = ws._lookup(m.StockFactorDaily, [row])[(row["trade_date"], row["ts_code"])]
        assert type(actual["trade_date"]) is type(row["trade_date"])
        assert isinstance(actual["calc_run_id"], UUID)
        assert actual["adj_close"] == 12.125 and actual["eligible"] is True
        assert isinstance(actual["calculated_at"], datetime)
        with factory() as reader:
            assert reader.scalar(select(m.StockFactorDaily.adj_close)) == 10
