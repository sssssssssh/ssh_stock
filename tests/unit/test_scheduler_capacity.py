from datetime import UTC, date, datetime, timedelta

from app.services import data_schedule
from sqlalchemy.exc import OperationalError


def test_unavailable_database_reports_unpersisted_without_sensitive_sql_or_log_storm(monkeypatch):
    class Offline:
        def get(self, *args):
            raise OperationalError("secret SQL", {"token": "secret"}, Exception("secret DSN"))

        def rollback(self):
            pass

    messages = []
    monkeypatch.setattr(data_schedule.logger, "error", lambda *parts: messages.append(parts))
    monkeypatch.setattr(data_schedule, "_unpersisted_log_at", {})
    now = datetime(2026, 10, 18, tzinfo=UTC)
    for offset in (0, 1, 299, 301):
        data_schedule.record_schedule_deferral(
            Offline(),
            "catchup",
            date(2026, 10, 17),
            "SCHEDULER_DATABASE_UNAVAILABLE",
            {},
            now=now + timedelta(seconds=offset),
        )
    assert len(messages) == 2
    assert "UNPERSISTED" in str(messages)
    assert "secret" not in str(messages)
