"""Compare candidate bytes with the immutable 9a377e4 implementation, not a mock."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from app.models import market_data as m
from app.models.data_publication import DataPublicationRow, DataPublicationSource
from app.repositories.job_run import update_job
from app.repositories.replace_slice import replace_slice_rows
from app.services import data_publication as publication
from sqlalchemy import event, select, text

from scripts.publication_candidate_benchmark_v13 import baseline_class
from tests.integration import test_data_publication as support
from tests.integration.m16_6_support import isolated_contract_database
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


def test_uncommitted_growth_with_empty_statistics_uses_candidate_primary_key(publication_db):  # noqa: F811
    factory, engine = publication_db
    with support.candidate(factory, engine) as (db, job):
        db.execute(text("ANALYZE public.data_publication_row"))
        ws = db.info["publication_workspace"]
        rows = [
            {**support.sample_row(m.StockTradeStatusDaily, job.id), "ts_code": f"V{n:06d}.SZ"}
            for n in range(1000)
        ]
        ws.upsert(m.StockTradeStatusDaily, rows, ["trade_date", "ts_code"])
        captured = []

        def capture(conn, cursor, statement, parameters, context, many):
            captured.append((statement, parameters))

        event.listen(engine, "before_cursor_execute", capture)
        try:
            found, _, _ = ws._lookup_batch(m.StockTradeStatusDaily, rows[:500])
            assert len(found) == 500
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        statement, parameters = captured[0]
        with db.connection().connection.cursor() as cursor:
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters)
            root = cursor.fetchone()[0][0]["Plan"]
        nodes = []

        def visit(node):
            nodes.append(node)
            for child in node.get("Plans", []):
                visit(child)

        visit(root)
        probes = [n for n in nodes if n.get("Relation Name") == "data_publication_row"]
        assert len(probes) == 1
        assert probes[0]["Index Name"] == "pk_data_publication_row"
        assert probes[0]["Actual Loops"] == 500
        assert probes[0]["Actual Rows"] <= 1
        assert probes[0].get("Rows Removed by Filter", 0) == 0


def test_core_rewrite_invalidates_already_cached_quality_certificate(publication_db):  # noqa: F811
    from types import SimpleNamespace

    factory, engine = publication_db
    with support.candidate(factory, engine) as (db, job):
        support.record_validation(db, job.id, support.DAY, SimpleNamespace(has_error=False))
        db.commit()
        certificate = db.get(DataPublicationSource, (job.id, job.id))
        assert certificate.validated_at is not None
        ws = db.info["publication_workspace"]
        ws.upsert(
            m.StockTradeStatusDaily,
            [support.sample_row(m.StockTradeStatusDaily, job.id)],
            ["trade_date", "ts_code"],
        )
        assert certificate.validation is None
        assert certificate.validated_at is None


@pytest.mark.parametrize("start", [date(2025, 12, 31), date(2026, 1, 31)])
def test_scope_closed_boundaries_match_baseline_without_deleting_neighbors(
    publication_db, monkeypatch, start,  # noqa: F811
):
    factory, engine = publication_db
    end = start + timedelta(days=1)
    model = m.StockTradeStatusDaily
    support.seed_published(factory)
    with factory() as db:
        old = db.scalar(select(model.calc_run_id))
        for day in (start - timedelta(days=1), start, end, end + timedelta(days=1)):
            db.add(model(**support.sample_row(model, old, day=day)))
        db.commit()
    outputs = []
    for cls in (baseline_class(), publication.PublicationWorkspace):
        monkeypatch.setattr(support, "PublicationWorkspace", cls)
        with support.candidate(factory, engine, start=start, end=end) as (db, job):
            replace_slice_rows(
                db, model, [], scope_filters=[model.trade_date >= start, model.trade_date <= end],
                key_columns=support.KEYS[model.__tablename__],
            )
            days = set(db.scalars(select(model.trade_date)))
            assert start not in days and end not in days
            assert {start - timedelta(days=1), end + timedelta(days=1)} <= days
            outputs.append(snapshot(db, job))
            with factory() as reader:
                assert {start, end} <= set(reader.scalars(select(model.trade_date)))
            update_job(db, job, status="FAILED")
    assert outputs[0] == outputs[1]


def test_real_worker_chain_published_business_output_matches_frozen_baseline(monkeypatch):
    from app.models.data_publication import DataPublication

    outputs = []
    current = publication.PublicationWorkspace
    for cls in (baseline_class(), current):
        with monkeypatch.context() as patch:
            patch.setattr(publication, "PublicationWorkspace", cls)
            with isolated_contract_database(patch) as (factory, engine):
                # Same real input fixture, real Worker, calculators, quality and
                # root publication; no synthetic quality certificate or engines.
                support.test_real_recalculation_and_quality_publish_without_synthetic_certificate(
                    (factory, engine), patch, "absent", None,
                )
                with factory() as reader:
                    roots = set(reader.scalars(select(DataPublication.job_id)))
                    result = {}
                    for model in support.MODELS:
                        rows = []
                        for row in reader.execute(select(model.__table__)).mappings():
                            value = dict(row)
                            # Independent executions have different audit clocks
                            # and UUIDs; compare all business fields exactly and
                            # retain the source role instead of discarding lineage.
                            for field in ("calculated_at", "created_at", "checked_at"):
                                value.pop(field, None)
                            for field in ("calc_run_id", "job_id"):
                                if value.get(field) is not None:
                                    value[field] = "ROOT" if value[field] in roots else "SEED"
                            rows.append(json.dumps(value, default=str, sort_keys=True))
                        result[model.__tablename__] = sorted(rows)
                    outputs.append(result)
    assert outputs[0] == outputs[1]
