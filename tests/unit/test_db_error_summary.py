from types import SimpleNamespace

import pytest
from app.core.db import database_error_summary
from sqlalchemy.exc import OperationalError, PendingRollbackError


def test_database_summary_keeps_root_driver_code_without_private_details():
    class ShutdownError(RuntimeError):
        sqlstate = "57P01"

    error = OperationalError("PRIVATE_SQL_SENTINEL", {"private": "PRIVATE_PARAMETER_SENTINEL"},
                             ShutdownError("PRIVATE_CONNECTION_SENTINEL"))
    summary = database_error_summary(error)
    assert summary == "database operation failed: OperationalError/ShutdownError (SQLSTATE 57P01)"
    assert "PRIVATE_" not in summary


@pytest.mark.parametrize("code", [None, "bad-code", "PRIVATE_STATE_SENTINEL"])
def test_database_summary_rejects_nonstandard_driver_state(code):
    class DriverError(RuntimeError):
        sqlstate = code

    summary = database_error_summary(OperationalError("private", {}, DriverError("private")))
    assert summary == "database operation failed: OperationalError/DriverError"


def test_pending_rollback_summary_does_not_include_exception_message():
    assert database_error_summary(PendingRollbackError("PRIVATE_CONNECTION_SENTINEL")) == (
        "database operation failed: PendingRollbackError"
    )


@pytest.mark.parametrize("primary,reason", [
    ("canceling statement due to statement timeout", "STATEMENT_TIMEOUT"),
    ("canceling statement due to user request", "QUERY_CANCELLED"),
    ("canceling statement due to lock timeout", "LOCK_TIMEOUT"),
])
def test_safe_cancel_reason_and_query_name_without_sql_or_parameters(primary, reason):
    class DriverError(RuntimeError):
        sqlstate = "57014"
        diag = SimpleNamespace(message_primary=primary)

    error = OperationalError("PRIVATE_SQL", {"token": "PRIVATE_PARAMETER"},
                             DriverError("PRIVATE_CONNECTION"))
    error.calculation_query_name = "trade_status.stock_daily"
    summary = database_error_summary(error)
    assert "query=trade_status.stock_daily" in summary
    assert "reason=" + reason in summary
    assert "SQLSTATE 57014" in summary
    assert "PRIVATE_" not in summary


def test_arbitrary_driver_diagnostics_and_query_labels_are_not_exposed():
    class DriverError(RuntimeError):
        diag = SimpleNamespace(message_primary="PRIVATE_DATABASE_DETAIL")

    error = OperationalError("PRIVATE_SQL", {}, DriverError("PRIVATE_CONNECTION"))
    error.calculation_query_name = "PRIVATE SQL WITH PARAMETERS"
    assert database_error_summary(error) == (
        "database operation failed: OperationalError/DriverError"
    )
