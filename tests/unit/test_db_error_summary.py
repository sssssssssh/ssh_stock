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
