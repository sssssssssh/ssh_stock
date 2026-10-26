-- Review ONLY for a NEW dedicated control plane, after 001. Never auto-migrate a live DB.
BEGIN;
CREATE TABLE g1_control.consumed_payloads (
 token_id uuid PRIMARY KEY REFERENCES g1_control.g1_consumptions(token_id),
 payload jsonb NOT NULL,
 payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE TABLE g1_control.external_imports (
 receipt_sha256 text PRIMARY KEY CHECK(receipt_sha256 ~ '^[0-9a-f]{64}$'),
 kind text NOT NULL CHECK(kind IN ('APPROVAL','KEY_STATUS','REVOCATION')),
 canonical_record jsonb NOT NULL,
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE g1_control.registry_events (
 issuer text NOT NULL, kid text NOT NULL, key_sha256 text NOT NULL,
 revision bigint PRIMARY KEY CHECK(revision>0),
 canonical_record jsonb NOT NULL,
 receipt_sha256 text NOT NULL UNIQUE REFERENCES g1_control.external_imports(receipt_sha256)
);
CREATE TABLE g1_control.approval_records (
 approval_id uuid PRIMARY KEY REFERENCES g1_control.g1_approvals(approval_id),
 canonical_record jsonb NOT NULL,
 registry_epoch bigint NOT NULL CHECK(registry_epoch>0),
 receipt_sha256 text NOT NULL UNIQUE REFERENCES g1_control.external_imports(receipt_sha256)
);
CREATE TABLE g1_control.approval_revocations (
 approval_id uuid PRIMARY KEY REFERENCES g1_control.g1_approvals(approval_id),
 canonical_record jsonb NOT NULL,
 receipt_sha256 text NOT NULL UNIQUE REFERENCES g1_control.external_imports(receipt_sha256)
);
CREATE TABLE g1_control.resource_events (
 sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 event_id uuid NOT NULL UNIQUE,
 token_id uuid NOT NULL REFERENCES g1_control.g1_consumptions(token_id),
 resource_kind text NOT NULL CHECK(resource_kind IN ('SOCKET_DIR','VOLUME','SECRET','CONTAINER')),
 resource_name text NOT NULL,
 event text NOT NULL CHECK(event IN ('RESERVED','CREATE_ATTEMPTED','OBSERVED_CREATED',
                                   'REMOVE_ATTEMPTED','OBSERVED_ABSENT','UNKNOWN')),
 request jsonb NOT NULL,
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(token_id,resource_kind,resource_name,event)
);
CREATE TABLE g1_control.absence_events (
 sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 token_id uuid NOT NULL UNIQUE REFERENCES g1_control.g1_consumptions(token_id),
 record jsonb NOT NULL,
 receipt_sha256 text NOT NULL UNIQUE CHECK(receipt_sha256 ~ '^[0-9a-f]{64}$'),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER external_imports_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.external_imports FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE TRIGGER consumed_payload_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.consumed_payloads FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE TRIGGER registry_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.registry_events FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE TRIGGER approval_record_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.approval_records FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE TRIGGER approval_revocation_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.approval_revocations FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE TRIGGER resource_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.resource_events FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE TRIGGER absence_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.absence_events FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();

-- Conservative epoch barrier: ANY registry revision invalidates all older unconsumed
-- approvals. No automatic reapproval, re-signing, refund or reset of consumed tokens.
CREATE OR REPLACE FUNCTION g1_control.lock_approval(p_id uuid) RETURNS void
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,g1_control AS $$
BEGIN
 PERFORM pg_advisory_xact_lock_shared(42362,1);
 PERFORM 1 FROM g1_control.g1_approvals WHERE approval_id=p_id FOR SHARE;
 IF NOT EXISTS (SELECT 1 FROM g1_control.approval_records a
  WHERE a.approval_id=p_id AND a.registry_epoch=(SELECT max(revision) FROM g1_control.registry_events)
  AND NOT EXISTS(SELECT 1 FROM g1_control.approval_revocations r WHERE r.approval_id=p_id))
 THEN RAISE EXCEPTION 'A42362_APPROVAL_REVOKED_OR_EPOCH_CHANGED'; END IF;
END $$;
CREATE FUNCTION g1_control.import_external_record(p_kind text,p_record jsonb,p_digest text)
 RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,g1_control AS $$
DECLARE epoch bigint; aid uuid;
BEGIN
 PERFORM pg_advisory_xact_lock(42362,1);
 IF p_digest !~ '^[0-9a-f]{64}$' OR p_kind NOT IN ('APPROVAL','KEY_STATUS','REVOCATION')
 THEN RAISE EXCEPTION 'A42362_IMPORT_REJECTED'; END IF;
 INSERT INTO g1_control.external_imports(receipt_sha256,kind,canonical_record)
 VALUES(p_digest,p_kind,p_record);
 IF p_kind='KEY_STATUS' THEN
  SELECT coalesce(max(revision),0) INTO epoch FROM g1_control.registry_events;
  IF (p_record->>'revision')::bigint<=epoch THEN RAISE EXCEPTION 'A42362_REVISION_REPLAY'; END IF;
  INSERT INTO g1_control.registry_events VALUES(p_record->>'issuer',p_record->>'kid',
   p_record->>'public_key_sha256',(p_record->>'revision')::bigint,p_record,p_digest);
 ELSE
  aid:=(p_record->>'approval_id')::uuid;
  IF p_kind='APPROVAL' THEN
   SELECT max(revision) INTO epoch FROM g1_control.registry_events;
   IF epoch IS NULL OR p_record->>'status'<>'APPROVED'
   THEN RAISE EXCEPTION 'A42362_APPROVAL_REJECTED'; END IF;
   INSERT INTO g1_control.g1_approvals(approval_id,payload_sha256,head_sha,run_id,attempt,
    status,expires_at,canonical_approval_sha256)
   VALUES(aid,p_record->>'payload_sha256',p_record#>>'{binding,identity,head_sha}',
    p_record#>>'{binding,identity,run_id}',(p_record#>>'{binding,identity,attempt}')::integer,
    'APPROVED',to_timestamp((p_record->>'expires_at')::bigint),p_digest);
   INSERT INTO g1_control.approval_records VALUES(aid,p_record,epoch,p_digest);
  ELSE
   PERFORM 1 FROM g1_control.g1_approvals WHERE approval_id=aid FOR UPDATE;
   INSERT INTO g1_control.approval_revocations VALUES(aid,p_record,p_digest);
  END IF;
 END IF;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA g1_control FROM PUBLIC;
REVOKE ALL ON FUNCTION g1_control.import_external_record(text,jsonb,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION g1_control.lock_approval(uuid) FROM PUBLIC;
GRANT USAGE ON SCHEMA g1_control TO g1_approval_writer,g1_receipt_reader,g1_auditor;
GRANT EXECUTE ON FUNCTION g1_control.import_external_record(text,jsonb,text) TO g1_approval_writer;
GRANT EXECUTE ON FUNCTION g1_control.lock_approval(uuid) TO g1_consumer;
GRANT SELECT ON g1_control.instance_identity,g1_control.external_imports,
 g1_control.registry_events,g1_control.approval_records,g1_control.approval_revocations,
 g1_control.g1_consumptions,g1_control.g1_audit_events,g1_control.resource_events,
 g1_control.absence_events,g1_control.consumed_payloads TO g1_receipt_reader;
GRANT INSERT ON g1_control.consumed_payloads TO g1_consumer;
GRANT INSERT,SELECT ON g1_control.resource_events TO g1_consumer;
GRANT USAGE ON SEQUENCE g1_control.resource_events_sequence_seq TO g1_consumer;
GRANT INSERT,SELECT ON g1_control.absence_events TO g1_auditor;
GRANT SELECT ON g1_control.instance_identity TO g1_auditor,g1_approval_writer;
GRANT USAGE ON SEQUENCE g1_control.absence_events_sequence_seq TO g1_auditor;
-- No controller/owner/worker DML grant. No UPDATE/DELETE/TRUNCATE grants to actors.
COMMIT;
