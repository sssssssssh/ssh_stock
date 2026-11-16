"""Count actual candidate-path calls without executing SQL or opening a connection."""

import ast
import hashlib
import inspect as python_inspect
import json
import textwrap
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
            # Model the original ORM UPDATE's known-value session synchronization.
            for cached in self.identity_map.values():
                if isinstance(cached, DataPublicationSource):
                    cached.validated_at = None
                    cached.validation = None
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


def test_factor_scope_invalidates_source_with_original_statement_sequence():
    db, ws = candidate_session()
    cached = DataPublicationSource(publication_id=ROOT, source_job_id=ROOT,
                                   role="CANDIDATE", validated_at=NOW, validation={"ok": True})
    make_transient_to_detached(cached)
    db.identity_map.add(inspect(cached))
    ws.record_scope(StockFactorDaily, [StockFactorDaily.trade_date >= DAY,
                                     StockFactorDaily.trade_date <= DAY])
    assert [kind for kind, _, _ in db.calls] == ["source_insert", "source_update"]
    assert "DO NOTHING" in db.calls[0][1]
    assert "validated_at" in db.calls[1][1] and "validation" in db.calls[1][1]
    assert db.source == {"role": "CANDIDATE", "validated_at": None, "validation": None}
    assert cached.validated_at is None and cached.validation is None
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
            scope_filters=[
                StockFactorDaily.trade_date >= start,
                StockFactorDaily.trade_date <= end,
            ],
            key_columns=["trade_date", "ts_code"],
        ) == size
        kinds = [kind for kind, _, _ in db.calls]
        batches = (size + 499) // 500
        assert kinds.count("source_insert") == 2
        assert kinds.count("source_update") == 1
        assert kinds.count("reconcile") == 1
        assert kinds.count("lookup") == kinds.count("store") == batches
        assert len(kinds) == 4 + 2 * batches
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


@pytest.fixture
def previous_upsert():
    """Restore only the assignment placement; verify exact bf7b6a3 method AST.

    Current calls below use the real imported module method, never this reference.
    No subprocess, database, module stub or production source write is involved.
    """
    source = python_inspect.getsource(publication.PublicationWorkspace.upsert)
    tree = ast.parse(textwrap.dedent(source))
    method = tree.body[0]
    batch = next(n for n in method.body if isinstance(n, ast.For))
    rows = next(n for n in batch.body if isinstance(n, ast.For))
    assignment = next(n for n in batch.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "updates" for t in n.targets))
    batch.body.remove(assignment)
    previous = next(n for n in rows.body if isinstance(n, ast.If)
                    and isinstance(n.test, ast.Name) and n.test.id == "previous")
    rows.body.insert(rows.body.index(previous), assignment)
    assert hashlib.sha256(ast.dump(method).encode()).hexdigest() == (
        "083180e575856afe00b876f674e8b3cb352b1817dc5d37230eb21a8644e7e000")
    namespace = dict(vars(publication))
    exec(compile(ast.fix_missing_locations(tree), "<bf7b6a3-upsert-reference>", "exec"), namespace)
    return namespace["upsert"]


@pytest.mark.parametrize("size", [1, 500, 501, 1001, "S2"])
@pytest.mark.parametrize("update_mode", ["default", "empty", "explicit", "iterator"])
def test_native_candidate_preparation_matches_previous(previous_upsert, size, update_mode):
    snapshots = []
    for method in (previous_upsert, publication.PublicationWorkspace.upsert):
        db, ws = candidate_session()
        rows = factor_rows(size)
        # Seed the first candidate through the actual module path, then preserve
        # a fixed first-observation preimage through subsequent conflict updates.
        first = dict(rows[0])
        ws.upsert(StockFactorDaily, [dict(row) for row in rows[:2]], ["trade_date", "ts_code"])
        key = first["trade_date"].isoformat(), first["ts_code"]
        db.candidates[key]["base_row"] = {"adj_close": "first-public-observation"}
        rows[0] = {**rows[0], "adj_close": 99.25, "config_hash": None}
        if len(rows) > 1:
            rows[1] = {**rows[1], "adj_close": 77.5}
        columns = ["adj_close", "config_hash"]
        updates = {"default": None, "empty": [], "explicit": columns,
                   "iterator": iter(columns)}[update_mode]
        db.calls.clear()
        count = method(ws, StockFactorDaily, rows, ["trade_date", "ts_code"],
                       update_columns=updates, preserve_existing_on_null_columns=["config_hash"])
        assert count == len(rows)
        assert db.candidates[key]["base_row"] == {"adj_close": "first-public-observation"}
        assert db.candidates[key]["row_data"]["config_hash"] == "synthetic-fixed-hash"
        assert db.candidates[key]["row_data"]["adj_close"] == (
            first["adj_close"] if update_mode == "empty" else 99.25)
        if len(rows) > 1:
            second_key = rows[1]["trade_date"].isoformat(), rows[1]["ts_code"]
            assert db.candidates[second_key]["row_data"]["adj_close"] == (
                first["adj_close"] if update_mode in {"empty", "iterator"} else 77.5)
        batches = (len(rows) + 499) // 500
        assert [kind for kind, _, _ in db.calls].count("lookup") == batches
        assert [kind for kind, _, _ in db.calls].count("store") == batches
        snapshots.append((json.dumps(list(db.candidates.values()), sort_keys=True),
                          [(kind, sql, params) for kind, sql, params in db.calls]))
    assert snapshots[0] == snapshots[1]


@pytest.mark.parametrize("failure", ["source", "missing_key", "cancel_second_batch"])
def test_native_candidate_refusals_match_previous(previous_upsert, monkeypatch, failure):
    snapshots = []
    for method in (previous_upsert, publication.PublicationWorkspace.upsert):
        db, ws = candidate_session()
        rows = factor_rows(501)
        if failure == "source":
            rows[0]["calc_run_id"] = UUID(int=999)
        elif failure == "missing_key":
            del rows[0]["ts_code"]
        calls = []
        stopped = publication.JobCancelled("SYNTHETIC_SECOND_BATCH_CANCEL")

        def checkpoint(calls=calls, stopped=stopped):
            calls.append("checkpoint")
            if failure == "cancel_second_batch" and len(calls) == 2:
                raise stopped

        with monkeypatch.context() as patch:
            patch.setattr(publication, "checkpoint", checkpoint)
            expected = {"source": ValueError, "missing_key": KeyError,
                        "cancel_second_batch": publication.JobCancelled}[failure]
            with pytest.raises(expected) as caught:
                method(ws, StockFactorDaily, rows, ["trade_date", "ts_code"])
        if failure == "cancel_second_batch":
            assert caught.value is stopped and len(db.candidates) == 500
        else:
            assert db.candidates == {}
        if failure == "source":
            assert str(caught.value) == "PUBLICATION_SOURCE_MISMATCH"
        snapshots.append((json.dumps(list(db.candidates.values()), sort_keys=True),
                          [(kind, sql, params) for kind, sql, params in db.calls]))
    assert snapshots[0] == snapshots[1]


def test_native_candidate_json_merge_and_serial_identity(previous_upsert, monkeypatch):
    from app.models.market_data import DataQualityDaily

    snapshots = []
    for method in (previous_upsert, publication.PublicationWorkspace.upsert):
        db, ws = candidate_session()
        rows = [{"trade_date": DAY, "dataset": name, "job_id": ROOT,
                 "issue_codes": codes, "expected_rows": 2.0}
                for name, codes in (("offline-a", {"new": 2}), ("offline-b", None))]
        previous = {}
        for index, row in enumerate(rows, 1):
            key = row["trade_date"], row["dataset"]
            previous[key] = {col.name: None for col in DataQualityDaily.__table__.columns}
            previous[key].update(row, id=index, issue_codes={"keep": 1})
        bases = {key: {"_publication_base": {"first": True}} for key in previous}
        with monkeypatch.context() as patch:
            patch.setattr(ws, "_lookup_batch", lambda model, batch, previous=previous,
                          bases=bases: (previous, bases, NOW))
            patch.setattr(publication, "checkpoint", lambda: None)
            assert method(ws, DataQualityDaily, rows, ["trade_date", "dataset"],
                          merge_json_columns=["issue_codes"]) == 2
        values = list(db.candidates.values())
        assert values[0]["row_data"]["issue_codes"] == {"keep": 1, "new": 2}
        assert values[1]["row_data"]["issue_codes"] == {"keep": 1}
        assert [v["row_data"]["id"] for v in values] == [1, 2]
        assert all(v["row_data"]["expected_rows"] == 2 for v in values)
        assert all(v["base_row"] == {"first": True} for v in values)
        snapshots.append(json.dumps(values, sort_keys=True))
    assert snapshots[0] == snapshots[1]
