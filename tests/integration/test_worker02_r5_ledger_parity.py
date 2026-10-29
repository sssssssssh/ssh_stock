"""Keep the original lifecycle assertions and also compare complete ledger business fields."""

import hashlib
import json
from contextlib import contextmanager

import pytest
from app.models.data_publication import DataPublication
from app.models.job import JobRun
from sqlalchemy import select

from tests.integration import test_worker02_r2_lifecycle as original


@pytest.mark.parametrize("kind", ["recalculate", "daily", "catchup"])
def test_original_off_on_lifecycle_also_preserves_ledger_business_fields(
        monkeypatch, kind, record_property):
    isolate = original.isolated_v14_database
    snapshots = []

    @contextmanager
    def with_ledger_snapshot(patch):
        with isolate(patch) as (factory, engine):
            yield factory, engine
            # Observe after the original arm finishes, before its owned database is dropped.
            with factory() as db:
                ledgers = list(db.scalars(select(DataPublication)))
                assert ledgers
                assert set(DataPublication.__table__.columns.keys()) == {
                    "job_id", "execution_token", "state", "identity", "created_at",
                    "publish_started_at", "published_at", "row_counts"}
                rows = []
                for ledger in ledgers:
                    owner = db.get(JobRun, ledger.job_id)
                    assert owner is not None and owner.status == "SUCCESS"
                    assert ledger.execution_token == owner.execution_token
                    assert ledger.state == "PUBLISHED"
                    assert ledger.created_at <= ledger.publish_started_at <= ledger.published_at
                    rows.append({"state": ledger.state, "identity": ledger.identity,
                                 "row_counts": ledger.row_counts,
                                 "owner_type": owner.job_type,
                                 "root_owner": owner.parent_job_id is None})
                snapshots.append(sorted(rows, key=lambda row: json.dumps(row, sort_keys=True)))

    monkeypatch.setattr(original, "isolated_v14_database", with_ledger_snapshot)
    original.test_claimed_roots_off_on_complete_publication_and_record_cost(
        monkeypatch, kind, record_property)
    assert len(snapshots) == 2 and snapshots[0] == snapshots[1]
    hashes = [hashlib.sha256(json.dumps(rows, sort_keys=True, allow_nan=False).encode()).hexdigest()
              for rows in snapshots]
    assert hashes[0] == hashes[1]
    record_property("worker02_r5_ledger_parity", json.dumps({
        "root_kind": kind, "off_sha256": hashes[0], "on_sha256": hashes[1],
        "ledger_count": len(snapshots[0]), "business_fields_exact": True,
        "per_execution_identity_and_timestamp_invariants_checked": True,
        "capacity_qualified": False}))
