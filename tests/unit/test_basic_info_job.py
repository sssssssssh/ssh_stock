from types import SimpleNamespace
from uuid import uuid4

import app.jobs.basic_info_job as basic_info_job_module
from app.jobs.basic_info_job import BasicInfoJob


class _FakeDb:
    def add(self, row):
        return None

    def commit(self):
        return None

    def refresh(self, row):
        return None

    def rollback(self):
        return None


class _FakeIngestion:
    def __init__(self, db, provider):
        self.calls = provider.calls

    def sync_stock_basic(self):
        self.calls.append("stock_basic")
        return 10

    def sync_sector_metadata(self):
        self.calls.append("sector_metadata")
        return 2

    def sync_sector_members(self):
        self.calls.append("sector_members")
        return 30


def test_basic_info_job_syncs_metadata_only(monkeypatch) -> None:
    monkeypatch.setattr(basic_info_job_module, "IngestionService", _FakeIngestion)
    provider = SimpleNamespace(calls=[])
    job = SimpleNamespace(
        id=uuid4(),
        job_type="sync_basic",
        target_trade_date=None,
        started_at=None,
        finished_at=None,
        status="QUEUED",
        step=None,
        row_count=0,
        error_message=None,
        job_metadata={},
    )

    BasicInfoJob(_FakeDb(), provider).run(job=job)

    assert provider.calls == ["stock_basic", "sector_metadata", "sector_members"]
    assert job.status == "SUCCESS"
    assert job.step == "180 sync basic info complete"
    assert job.row_count == 42
