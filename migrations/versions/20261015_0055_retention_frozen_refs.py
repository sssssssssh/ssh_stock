"""Protect canonical frozen candidate Job references without rewriting snapshots.

Revision ID: 0055_retention_frozen_refs
Revises: 0054_retention_lineage
"""

import sqlalchemy as sa
from alembic import op

revision = "0055_retention_frozen_refs"
down_revision = "0054_retention_lineage"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
    bind.execute(sa.text("SET LOCAL statement_timeout = '30s'"))
    existing = bind.execute(sa.text("""
        SELECT i.indisvalid AND i.indisready AND NOT i.indisunique
          AND i.indrelid = 'decision_observation'::regclass
          AND i.indpred IS NULL AND i.indexprs IS NULL
          AND i.indnkeyatts = 1 AND i.indnatts = 1
          AND am.amname = 'gin' AND o.opcname = 'jsonb_path_ops'
          AND i.indkey[0] = (SELECT attnum FROM pg_attribute
              WHERE attrelid = i.indrelid AND attname = 'record_json') AS ready
        FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_am am ON am.oid = c.relam JOIN pg_opclass o ON o.oid = i.indclass[0]
        WHERE c.oid = to_regclass('ix_decision_observation_source_jobs')
    """)).first()
    if existing is None:
        op.create_index("ix_decision_observation_source_jobs", "decision_observation",
                        ["record_json"], postgresql_using="gin",
                        postgresql_ops={"record_json": "jsonb_path_ops"})
    elif not existing.ready:
        raise RuntimeError("RETENTION_INDEX_REQUIRES_OPERATOR_REPAIR")
    op.execute("""
        CREATE FUNCTION retain_observation_source_jobs() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE candidates jsonb; item jsonb; identity_text text; identity_uuid uuid;
        BEGIN
          candidates := NEW.record_json #> '{data,candidates}';
          IF candidates IS NULL OR candidates = 'null'::jsonb THEN RETURN NEW; END IF;
          IF jsonb_typeof(candidates) <> 'array' THEN
            RAISE EXCEPTION 'INVALID_FROZEN_PROVENANCE' USING ERRCODE = '23514';
          END IF;
          FOR item IN SELECT value FROM jsonb_array_elements(candidates) LOOP
            IF item->'calc_run_id' IS NULL OR item->'calc_run_id' = 'null'::jsonb THEN
              CONTINUE;
            END IF;
            identity_text := item->>'calc_run_id';
            IF jsonb_typeof(item->'calc_run_id') <> 'string' OR identity_text !~
              '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
              RAISE EXCEPTION 'INVALID_FROZEN_PROVENANCE' USING ERRCODE = '23514';
            END IF;
          END LOOP;
          FOR identity_uuid IN SELECT DISTINCT (value->>'calc_run_id')::uuid
              FROM jsonb_array_elements(candidates)
              WHERE value->'calc_run_id' IS NOT NULL AND value->'calc_run_id' <> 'null'::jsonb
              ORDER BY 1 LOOP
            PERFORM id FROM job_run WHERE id = identity_uuid FOR KEY SHARE;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'SOURCE_CALC_LINEAGE_UNAVAILABLE' USING ERRCODE = '23503',
                CONSTRAINT = 'observation_source_job_reference';
            END IF;
          END LOOP;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_observation_source_jobs AFTER INSERT ON decision_observation
          FOR EACH ROW EXECUTE FUNCTION retain_observation_source_jobs();
    """)


def downgrade():
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("DROP TRIGGER trg_observation_source_jobs ON decision_observation")
    op.execute("DROP FUNCTION retain_observation_source_jobs()")
    op.drop_index("ix_decision_observation_source_jobs", table_name="decision_observation")
