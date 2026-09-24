from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.api.v1.system import runtime
from app.services.retention import run_retention
from sqlalchemy.dialects import postgresql


class _Result:
    def __init__(self, *, rows=None, scalar=None, rowcount=0):
        self._rows = rows or []
        self._scalar = scalar
        self.rowcount = rowcount

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


def test_runtime_reports_queue_heartbeat_and_latest_dates() -> None:
    heartbeat = datetime(2026, 9, 24, 6, 30, tzinfo=UTC)
    active = SimpleNamespace(
        id="job-1",
        job_type="recalculate",
        step="90 factors",
        started_at=datetime(2026, 9, 24, 6, 0, tzinfo=UTC),
    )

    class Db:
        def __init__(self):
            self.scalar_values = [active, heartbeat]
            self.execute_values = [
                _Result(rows=[("QUEUED", 2), ("RUNNING", 1)]),
                _Result(scalar=date(2026, 9, 23)),
                _Result(scalar=date(2026, 9, 22)),
                _Result(scalar=date(2026, 9, 22)),
            ]

        def scalar(self, statement):
            return self.scalar_values.pop(0)

        def execute(self, statement):
            return self.execute_values.pop(0)

    payload = runtime(Db())["data"]

    assert payload["worker_heartbeat"] == heartbeat.isoformat()
    assert payload["latest_job_heartbeat"] == heartbeat.isoformat()
    assert payload["active_job"]["job_type"] == "recalculate"
    assert payload["queued_count"] == 2
    assert payload["running_count"] == 1
    assert payload["latest_raw_date"] == "2026-09-23"


def test_retention_only_targets_operational_tables() -> None:
    class Db:
        def __init__(self):
            self.statements = []
            self.commits = 0

        def execute(self, statement):
            self.statements.append(statement)
            return _Result(rowcount=len(self.statements))

        def commit(self):
            self.commits += 1

    db = Db()
    result = run_retention(db, now=datetime(2026, 9, 24, tzinfo=UTC))
    sql = "\n".join(
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in db.statements
    )

    assert result == {
        "provider_api_log": 1,
        "successful_jobs": 2,
        "failed_jobs": 3,
        "auth_sessions": 4,
    }
    assert db.commits == 1
    assert "provider_api_log" in sql
    assert "job_run" in sql
    assert "auth_session" in sql
    for protected_table in (
        "stock_daily",
        "stock_factor_daily",
        "data_quality_daily",
        "opportunity_forward_eval",
    ):
        assert protected_table not in sql
