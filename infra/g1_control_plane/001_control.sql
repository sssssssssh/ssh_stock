-- Dedicated CONTROL PLANE ONLY; not an application Alembic migration. NOT RUN.
-- Independently provision owner/approval-writer/consumer/receipt-reader roles first.
BEGIN;
CREATE SCHEMA g1_control;
REVOKE ALL ON SCHEMA g1_control FROM PUBLIC;
CREATE TABLE g1_control.instance_identity (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 instance_sha256 text NOT NULL CHECK(instance_sha256 ~ '^[0-9a-f]{64}$'),
 purpose text NOT NULL CHECK(purpose='G1_CONTROL_PLANE_ONLY')
);
CREATE TABLE g1_control.g1_approvals (
 approval_id uuid PRIMARY KEY,
 payload_sha256 text NOT NULL UNIQUE CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
 head_sha text NOT NULL CHECK(head_sha ~ '^[0-9a-f]{40}$'),
 run_id text NOT NULL, attempt integer NOT NULL CHECK(attempt>0),
 status text NOT NULL CHECK(status IN ('APPROVED','PENDING','REVOKED','DENIED')),
 expires_at timestamptz NOT NULL,
 -- The independent approval writer validates two reviewers, canonical signed payload
 -- and budget before inserting. Probe/controller cannot write this table.
 canonical_approval_sha256 text NOT NULL CHECK(canonical_approval_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE TABLE g1_control.g1_consumptions (
 token_id uuid PRIMARY KEY, nonce uuid NOT NULL UNIQUE,
 fixture_uuid uuid NOT NULL UNIQUE,
 approval_id uuid NOT NULL UNIQUE REFERENCES g1_control.g1_approvals(approval_id),
 payload_sha256 text NOT NULL, head_sha text NOT NULL, run_id text NOT NULL,
 attempt integer NOT NULL CHECK(attempt>0), committed_at timestamptz NOT NULL
);
CREATE TABLE g1_control.g1_audit_events (
 event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 token_id uuid NOT NULL REFERENCES g1_control.g1_consumptions(token_id),
 event text NOT NULL CHECK(event IN ('CONSUMED','CREATE_REQUESTED','SECRET_CREATED','DESTROY_REQUESTED',
   'DESTROYED','ABSENT','INCOMPLETE')),
 payload_sha256 text NOT NULL,
 details jsonb NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE(token_id,event),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE FUNCTION g1_control.reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'A42361_APPEND_ONLY'; END $$;
CREATE TRIGGER consumption_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.g1_consumptions FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.g1_audit_events FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
REVOKE ALL ON ALL TABLES IN SCHEMA g1_control FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA g1_control FROM PUBLIC;
CREATE FUNCTION g1_control.lock_approval(p_id uuid) RETURNS void
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,g1_control AS $$
BEGIN PERFORM 1 FROM g1_control.g1_approvals WHERE approval_id=p_id FOR SHARE; END $$;
REVOKE ALL ON FUNCTION g1_control.lock_approval(uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA g1_control TO g1_consumer;
GRANT SELECT ON g1_control.g1_approvals, g1_control.instance_identity TO g1_consumer;
GRANT EXECUTE ON FUNCTION g1_control.lock_approval(uuid) TO g1_consumer;
GRANT INSERT, SELECT ON g1_control.g1_consumptions TO g1_consumer;
GRANT INSERT, SELECT ON g1_control.g1_audit_events TO g1_consumer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA g1_control TO g1_consumer;
COMMIT;
