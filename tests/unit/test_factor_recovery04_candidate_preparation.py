"""Source-isolated candidate diagnostic, NOT a native publication/PG acceptance test.

Compile the current method with real metadata and fake lookup/store/progress.
Reconstruct the verified bf7b6a3 placement for comparison; this is not a native
module import or database/performance acceptance result.
"""

import ast
import copy
import hashlib
import json
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic, perf_counter
from types import SimpleNamespace
from uuid import UUID

from app.models.market_data import StockFactorDaily
from sqlalchemy import Integer

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend/app/services/data_publication.py"
IDENTITY = UUID("00000000-0000-0000-0000-000000000004")
NOW = datetime(2026, 1, 1, tzinfo=UTC)
EVIDENCE = []


def candidate_method(trial):
    tree = ast.parse(SOURCE.read_bytes())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "PublicationWorkspace")
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                                and n.name == "upsert"))
    # Current source is the batch-hoisted implementation. Reconstruct only the
    # previous placement for the historical comparison, without changing disk.
    batch = next(n for n in method.body if isinstance(n, ast.For))
    rows = next(n for n in batch.body if isinstance(n, ast.For))
    updates = next(n for n in batch.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "updates" for t in n.targets))
    if not trial:
        batch.body.remove(updates)
        previous = next(n for n in rows.body if isinstance(n, ast.If)
                        and isinstance(n.test, ast.Name) and n.test.id == "previous")
        rows.body.insert(rows.body.index(previous), updates)
        assert hashlib.sha256(ast.dump(method).encode()).hexdigest() == (
            "083180e575856afe00b876f674e8b3cb352b1817dc5d37230eb21a8644e7e000")
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_json")

    class Progress:
        def __init__(self, *args, batch_count, **kwargs):
            self.batch_count = batch_count

        def report(self, *args, **kwargs):
            pass

    namespace = dict(json=json, date=date, datetime=datetime, UUID=UUID, Integer=Integer,
                     monotonic=monotonic, ProgressStep=Progress,
                     KEYS={"stock_factor_daily": ("trade_date", "ts_code")}, CORE=set())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[helper, method], type_ignores=[])),
                 str(SOURCE), "exec"), namespace)
    return namespace["upsert"]


def exercise(method, size, updates=None, *, wrong_source=False):
    checks = [0]

    class Column:
        def __init__(self, original):
            self.original = original

        def __getattr__(self, name):
            return getattr(self.original, name)

        @property
        def primary_key(self):
            checks[0] += 1
            return self.original.primary_key

    model = SimpleNamespace(__tablename__="stock_factor_daily", __table__=SimpleNamespace(
        c=StockFactorDaily.__table__.c,
        columns=[Column(c) for c in StockFactorDaily.__table__.columns]))
    rows = [{"trade_date": NOW.date(), "ts_code": f"{i:06d}.SZ", "adj_close": 12.125,
             "config_hash": None, "calc_run_id": IDENTITY} for i in range(size)]
    if wrong_source:
        rows[0]["calc_run_id"] = UUID(int=99)
    calls, staged = [], []

    def lookup(model, batch):
        calls.append(("lookup", len(batch)))
        existing, bases = {}, {}
        for row in batch:
            key = row["trade_date"], row["ts_code"]
            if int(row["ts_code"][:6]) % 2 == 0:
                existing[key] = {c.name: None for c in model.__table__.columns}
                existing[key].update(row, config_hash="previous", adj_close=1.5)
                bases[key] = {"_publication_base": {"fixture": "first-observation"}}
        return existing, bases, NOW

    def store(batch):
        calls.append(("store", len(batch)))
        staged.extend(batch)

    ws = SimpleNamespace(job_id=IDENTITY, db=SimpleNamespace(
        info={"calculation_job_id": IDENTITY}), _lookup_batch=lookup, _store=store,
        register_source=lambda *a, **k: calls.append(("source", 1)))
    started = perf_counter()
    count = method(ws, model, rows, ["trade_date", "ts_code"], update_columns=updates,
                   preserve_existing_on_null_columns=["config_hash"])
    seconds = perf_counter() - started
    wire = json.dumps(staged, sort_keys=True, default=str, allow_nan=False).encode()
    return dict(rows=count, primary_key_checks=checks[0], calls=calls,
                output_sha256=hashlib.sha256(wire).hexdigest(), seconds=seconds)


class CandidatePreparationDiagnostic(unittest.TestCase):
    def test_baseline_and_current_batch_column_work_match_outputs(self):
        baseline, trial = candidate_method(False), candidate_method(True)
        columns = len(StockFactorDaily.__table__.columns)
        for size in (1, 500, 501, 1001, 3450):
            before, after = exercise(baseline, size), exercise(trial, size)
            batches = (size + 499) // 500
            self.assertEqual(before["primary_key_checks"], size * columns)
            self.assertEqual(after["primary_key_checks"], batches * columns)
            self.assertEqual(before["output_sha256"], after["output_sha256"])
            self.assertEqual(before["calls"], after["calls"])
            self.assertEqual(before["rows"], after["rows"])
            self.assertEqual(sum(k == "lookup" for k, _ in before["calls"]), batches)
            self.assertEqual(sum(k == "store" for k, _ in before["calls"]), batches)
            EVIDENCE.append(dict(size=size, baseline=before, memory_only_trial=after))

    def test_explicit_and_empty_update_allowlists_keep_outputs(self):
        for updates in ([], ["adj_close", "config_hash"]):
            before = exercise(candidate_method(False), 501, updates)
            after = exercise(candidate_method(True), 501, updates)
            self.assertEqual(before["primary_key_checks"], 0)
            self.assertEqual(after["primary_key_checks"], 0)
            self.assertEqual(before["output_sha256"], after["output_sha256"])

    def test_source_mismatch_refuses_in_both_views(self):
        for trial in (False, True):
            with self.assertRaisesRegex(ValueError, "^PUBLICATION_SOURCE_MISMATCH$"):
                exercise(candidate_method(trial), 1, wrong_source=True)
