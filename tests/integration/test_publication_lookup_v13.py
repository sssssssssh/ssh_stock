"""Compare candidate bytes with the immutable 9a377e4 implementation, not a mock."""

import json
from datetime import UTC, datetime

from app.models.data_publication import DataPublicationRow
from app.repositories.job_run import update_job
from app.services import data_publication as publication
from sqlalchemy import select

from scripts.publication_candidate_benchmark_v13 import baseline_class
from tests.integration import test_data_publication as support
from tests.integration.test_data_publication import (  # noqa: F401
    publication_db,
)


def snapshot(db, job):
    result = []
    for row in db.scalars(
        select(DataPublicationRow)
        .where(DataPublicationRow.publication_id == job.id)
        .order_by(DataPublicationRow.table_name, DataPublicationRow.row_key)
    ):
        value = dict(
            table_name=row.table_name,
            row_key=row.row_key,
            row_data=row.row_data,
            base_row=row.base_row,
            is_deleted=row.is_deleted,
            source_id=str(row.source_id),
        )
        result.append(json.loads(json.dumps(value, default=str).replace(str(job.id), "ROOT")))
    return result


def test_all_core_candidates_match_frozen_baseline(publication_db, monkeypatch):  # noqa: F811
    factory, engine = publication_db
    support.seed_published(factory)
    outputs = []
    for cls in (baseline_class(), publication.PublicationWorkspace):
        monkeypatch.setattr(support, "PublicationWorkspace", cls)
        with support.candidate(factory, engine) as (db, job):
            for model in support.MODELS[:8]:
                row = support.sample_row(model, job.id, 20)
                row["calculated_at"] = datetime(2026, 9, 1, tzinfo=UTC)
                if "created_at" in model.__table__.c:
                    row["created_at"] = datetime(2026, 9, 1, tzinfo=UTC)
                ws = db.info["publication_workspace"]
                ws.upsert(model, [row], support.KEYS[model.__tablename__])
                row.update(
                    {
                        k: 30
                        for k in ("adj_close", "market_score", "heat_score", "opportunity_score")
                        if k in row
                    }
                )
                ws.upsert(model, [row], support.KEYS[model.__tablename__])
            outputs.append(snapshot(db, job))
            update_job(db, job, status="FAILED", step="synthetic golden sample complete")
    assert outputs[0] == outputs[1]
