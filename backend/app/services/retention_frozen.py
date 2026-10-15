"""Canonical source Job references retained by immutable decision observations.

Proposal/order/position candidate copies originate in this immutable observation
and its RESTRICT-linked graph. Agent report calc_run_id identifies BACKTEST runs,
not JobRun, and must not be interpreted as a Job reference.
"""

from sqlalchemy import String, cast, func, select, text

from app.models.job import JobRun
from app.models.paper import DecisionObservation

FROZEN_JOB_INDEX = "ix_decision_observation_source_jobs"
FROZEN_SCHEMA = text("""
SELECT EXISTS (
    SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_am a ON a.oid = c.relam JOIN pg_opclass o ON o.oid = i.indclass[0]
    WHERE c.oid = to_regclass('ix_decision_observation_source_jobs')
      AND i.indrelid = 'decision_observation'::regclass AND i.indisvalid AND i.indisready
      AND NOT i.indisunique AND i.indpred IS NULL AND i.indexprs IS NULL
      AND i.indnkeyatts = 1 AND i.indnatts = 1 AND a.amname = 'gin'
      AND o.opcname = 'jsonb_path_ops'
      AND i.indkey[0] = (SELECT attnum FROM pg_attribute
          WHERE attrelid = i.indrelid AND attname = 'record_json')
) AND EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgrelid = 'decision_observation'::regclass
      AND tgname = 'trg_observation_source_jobs' AND tgenabled IN ('O', 'A') AND tgtype = 5
      AND tgfoid = to_regprocedure('retain_observation_source_jobs()')
)
""")

# Invalid values are never projected to Python (they could contain private text).
FROZEN_ISSUES = text("""
WITH snapshots AS (
    SELECT signal_date, record_json #> '{data,candidates}' AS candidates
    FROM decision_observation
), refs AS (
    SELECT signal_date, item->>'calc_run_id' AS job_text,
           jsonb_typeof(item->'calc_run_id') = 'string'
           AND item->>'calc_run_id' ~
               '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' AS valid
    FROM snapshots CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(candidates) = 'array' THEN candidates ELSE '[]'::jsonb END
    ) AS item
    WHERE item->'calc_run_id' IS NOT NULL AND item->'calc_run_id' <> 'null'::jsonb
), issues AS (
    SELECT signal_date, NULL::text AS job_text, 'INVALID' AS issue FROM snapshots
    WHERE candidates IS NOT NULL AND jsonb_typeof(candidates) NOT IN ('array', 'null')
    UNION ALL
    SELECT signal_date, CASE WHEN valid THEN job_text END,
           CASE WHEN valid THEN 'MISSING' ELSE 'INVALID' END FROM refs
    WHERE CASE WHEN valid THEN NOT EXISTS (
        SELECT 1 FROM job_run WHERE id = refs.job_text::uuid
    ) ELSE true END
)
SELECT * FROM (SELECT * FROM issues LIMIT :limit) bounded
ORDER BY signal_date, job_text NULLS FIRST
""")


def frozen_job_reference():
    snapshot = func.jsonb_build_object("data", func.jsonb_build_object(
        "candidates", func.jsonb_build_array(func.jsonb_build_object(
            "calc_run_id", cast(JobRun.id, String),
        )),
    ))
    return select(DecisionObservation.id).where(
        DecisionObservation.record_json.contains(snapshot),
    ).exists()
