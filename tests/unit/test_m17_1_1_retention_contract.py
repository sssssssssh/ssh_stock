from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from app.core.retention_config import RetentionPolicy
from app.services.calc_metadata import calculation_metadata
from app.services.retention import eligible_jobs
from app.services.retention_lineage import (
    JOB_REFERENCES,
    RetentionBlocked,
    assert_reference_schema,
    discovered_orm_references,
    referenced_job,
)
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql


def test_manifest_discovers_every_persistent_reference_and_job_fk():
    assert discovered_orm_references() == set(JOB_REFERENCES)
    assert len(JOB_REFERENCES) == 17
    assert {("data_publication", "job_id"),
            ("data_publication_source", "source_job_id"),
            ("data_schedule_intent", "job_id")} <= set(JOB_REFERENCES)
    assert {("job_run", "parent_job_id"), ("job_run", "depends_on_job_id")} <= set(JOB_REFERENCES)


def test_new_orm_reference_without_manifest_change_blocks_before_sql(monkeypatch):
    metadata = sa.MetaData()
    sa.Table("future_derived", metadata, sa.Column("calc_run_id", sa.Uuid))
    unknown = discovered_orm_references(metadata)
    assert unknown == {("future_derived", "calc_run_id")}
    monkeypatch.setattr("app.services.retention_lineage.discovered_orm_references",
                        lambda: set(JOB_REFERENCES) | unknown)
    with pytest.raises(RetentionBlocked, match="RETENTION_REFERENCE_MANIFEST_MISMATCH"):
        assert_reference_schema(None)


def test_protection_sql_uses_indexable_exists_without_record_json_or_uuid_materialization():
    query = sa.select(sa.literal(1)).where(referenced_job())
    sql = str(query.compile(dialect=postgresql.dialect()))
    assert sql.count("EXISTS") == len(JOB_REFERENCES) + 1
    assert "SELECT decision_observation.record_json" not in sql and "job_metadata" not in sql
    assert "decision_observation.record_json @>" in sql
    for table, column in JOB_REFERENCES:
        source = f"referencing_{column}" if table == "job_run" else table
        assert f"{source}.{column} = job_run.id" in sql


def test_age_predicate_keeps_original_statuses_and_strict_cutoffs():
    filters = eligible_jobs(datetime(2026, 10, 15, tzinfo=UTC))
    sql = str(sa.select(sa.literal(1)).where(*filters).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    for status in ("SUCCESS", "PARTIAL", "CANCELLED", "FAILED"):
        assert status in sql
    assert "finished_at <" in sql and "finished_at <=" not in sql
    for kind in ("PAPER_DAILY", "PAPER_REVIEW", "PAPER_OBSERVATION"):
        assert kind in sql


@pytest.mark.parametrize("update", [
    {"max_candidate_rows": 0}, {"max_candidate_rows": 100001},
    {"statement_timeout_ms": 0}, {"max_duration_ms": 0}, {"lock_timeout_ms": 0},
    {"diagnostic_limit": 101}, {"job_deletion_enabled": "true"}, {"unknown": 1},
    {"candidate_warning_percent": 0}, {"candidate_warning_percent": 101},
])
def test_policy_is_bounded_strict_and_job_deletion_defaults_off(update):
    assert not RetentionPolicy().job_deletion_enabled
    with pytest.raises(ValidationError):
        RetentionPolicy.model_validate(update)


def test_untracked_direct_calculation_does_not_fabricate_a_job_uuid():
    result = calculation_metadata(config={}, calc_version="synthetic")
    assert result["calc_run_id"] is None
