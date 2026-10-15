from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api.v1 import jobs
from app.core.paper_config import PaperRiskConfig
from app.models.paper import PaperAccount
from app.repositories.paper import PaperRepository
from app.services.paper.job_application import safe_error_code
from app.services.paper.recovery import recover_stale_paper_jobs
from app.services.paper.scheduling import run_scheduled_paper
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql


def test_disabled_paper_automation_never_touches_tables():
    config = SimpleNamespace(paper_config=SimpleNamespace(enabled=False))

    class ForbiddenDb:
        def __getattr__(self, name):
            raise AssertionError("disabled automation accessed the database")

    assert run_scheduled_paper(ForbiddenDb(), None, settings=config) == {"queued": 0, "blocked": 0}
    assert recover_stale_paper_jobs(ForbiddenDb(), timeout_minutes=15, settings=config) == 0


def test_account_lock_serializes_state_and_allows_cancellation_fk_receipts():
    class Db:
        def scalar(self, statement):
            self.statement = statement
            return object()

    db = Db()
    PaperRepository(db).owned(PaperAccount, uuid4(), uuid4(), lock=True)
    assert "FOR NO KEY UPDATE" in str(db.statement.compile(dialect=postgresql.dialect()))


def test_paper_exception_does_not_export_sql_or_private_payload():
    assert (
        safe_error_code(RuntimeError("secret SQL parameters password=private"))
        == "PAPER_EXECUTION_FAILED"
    )


def test_legacy_cancel_endpoint_does_not_expose_paper_jobs():
    db = SimpleNamespace(get=lambda *_: SimpleNamespace(job_type="PAPER_DAILY"))
    with pytest.raises(HTTPException) as error:
        jobs.cancel_job(uuid4(), db)
    assert error.value.status_code == 404


@pytest.mark.parametrize("payload", [
    {"max_positions": True}, {"max_new_positions_per_day": 2.0},
    {"min_cash_ratio": "0e-500"}, {"max_single_position_weight": "1e-500"},
    {"max_theme_weight": "0.3333333333333333333333333333"},
])
def test_user_risk_limits_reject_boolean_counts_and_unbounded_decimal_scales(payload):
    with pytest.raises(ValidationError):
        PaperRiskConfig.model_validate(payload)
