"""Count actual candidate-path calls without executing SQL or opening a connection."""

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from app.models.data_publication import DataPublicationSource
from app.models.market_data import StockFactorDaily
from app.repositories.replace_slice import replace_slice_rows
from app.services import data_publication as publication
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, make_transient_to_detached

ROOT = UUID("00000000-0000-0000-0000-000000000002")
DAY = date(2026, 9, 15)
NOW = datetime(2026, 9, 16, tzinfo=UTC)


class RecordingSession(Session):
    """In-memory boundary; SQL is compiled/recorded, never evaluated by a database."""

    def __init__(self, *, fail_source=False):
        super().__init__()
        self.info["calculation_job_id"] = ROOT
        self.calls = []
        self.scopes = []
        self.candidates = {}
        self.source = {"role": "CANDIDATE", "validated_at": NOW, "validation": {"ok": True}}
        self.fail_source = fail_source
        self.owner = SimpleNamespace(id=ROOT, parent_job_id=None)

    def get(self, model, identity, **kwargs):
        assert identity == ROOT
        return self.owner

    def add(self, instance, **kwargs):
        self.scopes.append(instance)

    def execute(self, statement, params=None, **kwargs):
        sql = str(statement.compile(dialect=postgresql.dialect()))
        if "INSERT INTO data_publication_source" in sql:
            self.calls.append(("source_insert", sql, None))
            if self.fail_source:
                raise RuntimeError("SYNTHETIC_SOURCE_FAILURE")
            if "DO UPDATE" in sql:
                self.source.update(validated_at=None, validation=None)
        elif "UPDATE data_publication_source" in sql:
            self.calls.append(("source_update", sql, None))
            self.source.update(validated_at=None, validation=None)
        elif "WITH input_keys" in sql:
            requested = json.loads(params["keys"])
            self.calls.append(("lookup", sql, dict(params)))
            mapped = []
            for key in requested:
                identity = (key["trade_date"], key["ts_code"])
                previous = self.candidates.get(identity)
                mapped.append({
                    **{col.name: None for col in StockFactorDaily.__table__.columns},
                    **(previous["row_data"] if previous else {}),
                    "_key_0": date.fromisoformat(key["trade_date"]),
                    "_key_1": key["ts_code"], "_has_current": previous is not None,
                    "_publication_base": None, "_transaction_now": NOW,
                })
            return SimpleNamespace(mappings=lambda: mapped)
        elif "INSERT INTO public.data_publication_row" in sql:
            staged = json.loads(params["rows"])
            self.calls.append(("store", sql, dict(params)))
            for row in staged:
                key = tuple(row["row_key"])
                if key in self.candidates:
                    row["base_row"] = self.candidates[key]["base_row"]
                self.candidates[key] = row
        elif getattr(statement, "is_select", False):
            self.calls.append(("reconcile", sql, None))
            return SimpleNamespace(all=lambda: [
                (date.fromisoformat(key[0]), key[1]) for key in self.candidates
            ])
        else:
            raise AssertionError("UNEXPECTED_OFFLINE_STATEMENT")
        return SimpleNamespace()


def candidate_session(**options):
    db = RecordingSession(**options)
    ws = publication.PublicationWorkspace.__new__(publication.PublicationWorkspace)
    ws.db, ws.job_id, ws.token = db, ROOT, ROOT
    db.info["publication_workspace"] = ws
    return db, ws


def test_factor_scope_invalidates_source_in_one_statement():
    db, ws = candidate_session()
    cached = DataPublicationSource(publication_id=ROOT, source_job_id=ROOT,
                                   role="CANDIDATE", validated_at=NOW, validation={"ok": True})
    make_transient_to_detached(cached)
    db.identity_map.add(inspect(cached))
    ws.record_scope(StockFactorDaily, [StockFactorDaily.trade_date >= DAY,
                                     StockFactorDaily.trade_date <= DAY])
    assert [kind for kind, _, _ in db.calls] == ["source_insert"]
    assert "DO UPDATE SET validated_at" in db.calls[0][1]
    assert db.source == {"role": "CANDIDATE", "validated_at": None, "validation": None}
    assert {"validated_at", "validation"} <= inspect(cached).expired_attributes
    assert len(db.scopes) == 1
    scope = db.scopes[0]
    assert (scope.publication_id, scope.source_id, scope.table_name) == (
        ROOT, ROOT, "stock_factor_daily",
    )
    assert scope.start_date == scope.end_date == DAY


def factor_rows(size):
    if size == "S2":
        # Existing business_synthetic_dataset S2: 150 stocks, 23 synthetic January weekdays.
        days = [date(2025, 1, 1) + timedelta(days=i) for i in range(31)]
        keys = [(day, i) for day in days if day.weekday() < 5 for i in range(1, 151)]
        assert len(keys) == 3450
    else:
        keys = [(DAY, i) for i in range(size)]
    return [{"trade_date": day, "ts_code": f"{i:06d}.SZ", "adj_close": 12.125,
             "eligible": True, "calc_run_id": ROOT, "calc_version": "factor_v2",
             "config_hash": "synthetic-fixed-hash", "calculated_at": NOW} for day, i in keys]


@pytest.mark.parametrize("size", [1, 500, 501, 1001, "S2"])
def test_factor_candidate_path_bounds_queries_and_preserves_rows(size):
    db, _ = candidate_session()
    rows = factor_rows(size)
    size = len(rows)
    start, end = min(row["trade_date"] for row in rows), max(row["trade_date"] for row in rows)
    first = None
    for attempt in range(2):
        db.calls.clear()
        assert replace_slice_rows(
            db, StockFactorDaily, rows,
            scope_filters=[StockFactorDaily.trade_date >= start, StockFactorDaily.trade_date <= end],
            key_columns=["trade_date", "ts_code"],
        ) == size
        kinds = [kind for kind, _, _ in db.calls]
        batches = (size + 499) // 500
        assert kinds.count("source_insert") == 2
        assert kinds.count("source_update") == 0
        assert kinds.count("reconcile") == 1
        assert kinds.count("lookup") == kinds.count("store") == batches
        assert len(kinds) == 3 + 2 * batches
        lookups = [params for kind, _, params in db.calls if kind == "lookup"]
        assert [len(json.loads(p["keys"])) for p in lookups] == [
            min(500, size - start) for start in range(0, size, 500)
        ]
        assert all(set(p) == {"keys", "publication", "table_name"} for p in lookups)
        assert all(p["publication"] == ROOT and p["table_name"] == "stock_factor_daily"
                   for p in lookups)
        assert len(db.candidates) == size
        snapshot = json.dumps(list(db.candidates.values()), sort_keys=True)
        if attempt == 0:
            first = snapshot
        else:
            assert snapshot == first
        for row in rows:
            staged = db.candidates[(row["trade_date"].isoformat(), row["ts_code"])]
            assert staged["source_id"] == staged["publication_id"] == str(ROOT)
            assert staged["base_row"] is None and staged["is_deleted"] is False
            expected = json.loads(json.dumps(row, default=lambda v: v.isoformat()
                                            if isinstance(v, (date, datetime)) else str(v)))
            assert all(staged["row_data"][key] == value for key, value in expected.items())


def test_scope_source_failure_does_not_record_scope():
    db, ws = candidate_session(fail_source=True)
    with pytest.raises(RuntimeError, match="SYNTHETIC_SOURCE_FAILURE"):
        ws.record_scope(StockFactorDaily, [StockFactorDaily.trade_date == DAY])
    assert db.scopes == [] and db.candidates == {}


def test_scope_rejects_unowned_source_before_sql():
    db, ws = candidate_session()
    db.owner = None
    with pytest.raises(publication.JobOwnershipLost, match="PUBLICATION_SOURCE_NOT_OWNED"):
        ws.record_scope(StockFactorDaily, [StockFactorDaily.trade_date == DAY])
    assert db.calls == [] and db.scopes == [] and db.candidates == {}


def test_candidate_stop_before_store_is_not_swallowed(monkeypatch):
    db, ws = candidate_session()
    stopped = publication.JobCancelled("SYNTHETIC_CANCEL")

    def checkpoint():
        raise stopped

    monkeypatch.setattr(publication, "checkpoint", checkpoint)
    row = {"trade_date": DAY, "ts_code": "000001.SZ", "calc_run_id": ROOT}
    with pytest.raises(publication.JobCancelled) as error:
        ws.upsert(StockFactorDaily, [row], ["trade_date", "ts_code"])
    assert error.value is stopped
    assert [kind for kind, _, _ in db.calls] == ["source_insert", "lookup"]
    assert db.candidates == {}
