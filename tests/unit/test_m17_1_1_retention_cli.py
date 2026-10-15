from types import SimpleNamespace

import pytest
from app.cli import cli
from app.services.retention_indexes import index_ready
from typer.testing import CliRunner

runner = CliRunner()


def test_unconfirmed_retention_and_index_apply_fail_before_database_connection(monkeypatch):
    def unsafe_connection(*args, **kwargs):
        raise AssertionError("unconfirmed command connected to a database")

    monkeypatch.setattr("app.cli.SessionLocal", unsafe_connection)
    monkeypatch.setattr("sqlalchemy.create_engine", unsafe_connection)
    for args in (["retention-run"], ["retention-run", "--confirm"],
                 ["retention-indexes", "--apply"]):
        result = runner.invoke(cli, args)
        assert result.exit_code == 2


def test_check_cli_is_read_only_and_diagnostics_are_explicit(monkeypatch):
    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = []
    monkeypatch.setattr("app.cli.SessionLocal", Db)

    def check(db, **kwargs):
        seen.append(kwargs)
        return {"blocked": False, "dry_run": True}

    monkeypatch.setattr("app.services.retention.run_retention", check)
    assert runner.invoke(cli, ["retention-check"]).exit_code == 0
    assert runner.invoke(cli, ["retention-check", "--details"]).exit_code == 0
    assert seen == [{"dry_run": True, "include_diagnostics": False},
                    {"dry_run": True, "include_diagnostics": True}]


def test_retention_run_needs_enabled_policy_and_reports_blocked_exit_status(monkeypatch):
    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.cli.SessionLocal", Db)
    monkeypatch.setattr("app.cli.get_settings", lambda: SimpleNamespace(
        app_config={"retention": {"job_deletion_enabled": True}},
    ))
    calls = []

    def blocked(db, *, policy):
        calls.append(policy)
        return {"blocked": True, "error_code": "RETENTION_CANDIDATE_BUDGET_EXCEEDED"}

    monkeypatch.setattr("app.services.retention.run_retention", blocked)
    assert runner.invoke(cli, ["retention-run", "--confirm"]).exit_code == 1
    assert calls[0].job_deletion_enabled


def test_online_index_helper_rejects_transactional_connection_before_ddl():
    from app.services.retention_indexes import prepare_retention_indexes
    from app.services.retention_lineage import RetentionBlocked

    connection = SimpleNamespace(get_isolation_level=lambda: "READ COMMITTED",
                                 get_execution_options=lambda: {})
    with pytest.raises(RetentionBlocked, match="RETENTION_INDEX_REQUIRES_AUTOCOMMIT"):
        prepare_retention_indexes(connection, apply=True)


@pytest.mark.parametrize("change", [
    {}, {"indisvalid": False}, {"indisunique": True}, {"right_table": False},
    {"plain": False}, {"indnatts": 2}, {"amname": "hash"},
    {"column_names": ["wrong_column"]},
])
def test_prebuilt_index_verification_uses_physical_metadata_not_name_only(change):
    values = dict(indisvalid=True, indisready=True, indisunique=False, right_table=True,
                  plain=True, amname="btree", indnkeyatts=1, indnatts=1,
                  column_names=["calc_run_id"])
    values.update(change)
    assert bool(index_ready(SimpleNamespace(**values), ("calc_run_id",))) == (not change)
