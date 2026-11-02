"""New diagnostics use separate read-only connections to marked test databases only."""

import json
from types import SimpleNamespace as NS

from sqlalchemy import text

from scripts.v14_test_database import isolated_v14_database
from scripts.worker02_r5_diagnostics import context, database_snapshot
from tests.integration.test_a4233_observer_pg17 import observer_pg17 as observer_pg17


def test_snapshot_does_not_change_pool_readonly_state_or_business_rows(monkeypatch):
    with isolated_v14_database(monkeypatch) as (factory, engine):
        item = NS(funcargs={"tiny_stability_database": (None, None, engine, None, None)})
        with factory() as db:
            before = db.scalar(text("SHOW default_transaction_read_only"))
            assert before == "off"
            assert db.scalar(text("SELECT count(*) FROM job_run")) == 0
        result = database_snapshot(item)
        assert result["status"] == "RECORDED_READ_ONLY"
        assert result["settings"]["transaction_read_only"] == "on"
        assert result["settings"]["statement_timeout"] == "500"
        with factory() as db:
            assert db.scalar(text("SHOW default_transaction_read_only")) == before
            assert db.scalar(text("SELECT count(*) FROM job_run")) == 0
        assert "postgresql" not in json.dumps(result)


def test_wrong_physical_identity_cannot_be_reported_as_collected(monkeypatch):
    with isolated_v14_database(monkeypatch) as (_, engine):
        with monkeypatch.context() as patch:
            patch.setenv("V14_TEST_SYSTEM_IDENTIFIER", "1")
            result = context(NS(fixturenames=[], funcargs={
                "tiny_stability_database": (None, None, engine, None, None)}))
            assert result["database"]["status"] == "UNCONFIRMED_SNAPSHOT_FAILURE"


def test_role_snapshot_reports_privileges_without_names_or_credentials(observer_pg17):
    engine, names = observer_pg17
    result = database_snapshot(NS(funcargs={"observer_pg17": (engine, names)}))
    assert result["status"] == "RECORDED_READ_ONLY"
    assert [r["read_all_stats"] for r in result["roles"]] == [True, False]
    assert all(not allowed for role in result["roles"]
               for allowed in role["business_privileges"].values())
    assert all(name not in json.dumps(result) for name in names)
