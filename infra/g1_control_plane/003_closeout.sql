-- REVIEW ONLY. Dedicated control database after 001/002; NOT executed by application/CI.
-- Administrator must provision all g1_*_writer roles and g1_control_owner NOLOGIN.
BEGIN;
CREATE TABLE g1_control.domain_events (
 sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 domain text NOT NULL CHECK(domain IN ('registry','approval','consumer','pg_owner',
   'controller','supervisor','absence_auditor')),
 scope_sha256 text NOT NULL CHECK(scope_sha256 ~ '^[0-9a-f]{64}$'),
 epoch uuid NOT NULL, event text NOT NULL CHECK(length(event) BETWEEN 1 AND 64),
 record jsonb NOT NULL, committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(domain,scope_sha256,epoch,event)
);
ALTER TABLE g1_control.domain_events OWNER TO g1_control_owner;
CREATE TRIGGER domain_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON g1_control.domain_events FOR EACH STATEMENT EXECUTE FUNCTION g1_control.reject_history_mutation();
CREATE FUNCTION g1_control.append_domain_event(p_scope text,p_epoch uuid,p_event text,p_record jsonb)
 RETURNS TABLE(sequence bigint) LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog,g1_control AS $$
DECLARE d text;
BEGIN
 d:=CASE session_user
 WHEN 'g1_registry_writer' THEN 'registry' WHEN 'g1_approval_writer' THEN 'approval'
 WHEN 'g1_consumer' THEN 'consumer' WHEN 'g1_pg_owner_writer' THEN 'pg_owner'
 WHEN 'g1_controller_writer' THEN 'controller' WHEN 'g1_supervisor_writer' THEN 'supervisor'
 WHEN 'g1_absence_auditor_writer' THEN 'absence_auditor' ELSE NULL END;
 IF d IS NULL THEN RAISE EXCEPTION 'A42363_DOMAIN_ACL'; END IF;
 RETURN QUERY INSERT INTO g1_control.domain_events(domain,scope_sha256,epoch,event,record)
 VALUES(d,p_scope,p_epoch,p_event,p_record) RETURNING domain_events.sequence;
END $$;
ALTER FUNCTION g1_control.append_domain_event(text,uuid,text,jsonb) OWNER TO g1_control_owner;
REVOKE ALL ON g1_control.domain_events FROM PUBLIC;
REVOKE ALL ON FUNCTION g1_control.append_domain_event(text,uuid,text,jsonb) FROM PUBLIC;
GRANT SELECT ON g1_control.domain_events TO g1_receipt_reader;
GRANT EXECUTE ON FUNCTION g1_control.append_domain_event(text,uuid,text,jsonb)
 TO g1_registry_writer,g1_approval_writer,g1_consumer,g1_pg_owner_writer,
 g1_controller_writer,g1_supervisor_writer,g1_absence_auditor_writer;
GRANT USAGE ON SCHEMA g1_control TO g1_registry_writer,g1_pg_owner_writer,
 g1_controller_writer,g1_supervisor_writer,g1_absence_auditor_writer;
GRANT SELECT ON g1_control.instance_identity TO g1_registry_writer,g1_pg_owner_writer,
 g1_controller_writer,g1_supervisor_writer,g1_absence_auditor_writer;
GRANT EXECUTE ON FUNCTION g1_control.import_external_record(text,jsonb,text) TO g1_registry_writer;
CREATE FUNCTION g1_control.external_domain_guard() RETURNS trigger LANGUAGE plpgsql
 SET search_path=pg_catalog,g1_control AS $$
BEGIN
 IF NOT ((session_user='g1_registry_writer' AND NEW.kind='KEY_STATUS') OR
         (session_user='g1_approval_writer' AND NEW.kind IN ('APPROVAL','REVOCATION')))
 THEN RAISE EXCEPTION 'A42363_IMPORT_ROLE_DOMAIN'; END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION g1_control.external_domain_guard() OWNER TO g1_control_owner;
REVOKE ALL ON FUNCTION g1_control.external_domain_guard() FROM PUBLIC;
CREATE TRIGGER external_domain BEFORE INSERT ON g1_control.external_imports
 FOR EACH ROW EXECUTE FUNCTION g1_control.external_domain_guard();
ALTER FUNCTION g1_control.import_external_record(text,jsonb,text) OWNER TO g1_control_owner;
ALTER FUNCTION g1_control.lock_approval(uuid) OWNER TO g1_control_owner;
GRANT SELECT,INSERT ON g1_control.external_imports,g1_control.registry_events,
 g1_control.approval_records,g1_control.approval_revocations,g1_control.g1_approvals
 TO g1_control_owner;
GRANT UPDATE(approval_id) ON g1_control.g1_approvals TO g1_control_owner;

-- Enforce lifecycle inside the database, even if an application caller bypasses Python.
CREATE FUNCTION g1_control.resource_transition_guard() RETURNS trigger LANGUAGE plpgsql
 SECURITY DEFINER SET search_path=pg_catalog,g1_control AS $$
DECLARE prior text; previous_request jsonb;
BEGIN
 PERFORM 1 FROM g1_control.g1_consumptions WHERE token_id=NEW.token_id FOR UPDATE;
 SELECT event,request INTO prior,previous_request FROM g1_control.resource_events
 WHERE token_id=NEW.token_id AND resource_kind=NEW.resource_kind AND resource_name=NEW.resource_name
 ORDER BY sequence DESC LIMIT 1;
 IF (prior IS NULL AND NEW.event<>'RESERVED') OR
 (prior='RESERVED' AND NEW.event NOT IN ('CREATE_ATTEMPTED','UNKNOWN','REMOVE_ATTEMPTED')) OR
 (prior='CREATE_ATTEMPTED' AND NEW.event NOT IN ('OBSERVED_CREATED','UNKNOWN','REMOVE_ATTEMPTED')) OR
 (prior='OBSERVED_CREATED' AND NEW.event NOT IN ('REMOVE_ATTEMPTED','UNKNOWN')) OR
 (prior='UNKNOWN' AND NEW.event<>'REMOVE_ATTEMPTED') OR
 (prior='REMOVE_ATTEMPTED' AND NEW.event NOT IN ('OBSERVED_ABSENT','UNKNOWN')) OR prior='OBSERVED_ABSENT'
 THEN RAISE EXCEPTION 'A42363_LEDGER_TRANSITION'; END IF;
 IF previous_request IS NOT NULL AND previous_request->'resource' IS DISTINCT FROM NEW.request->'resource'
 THEN RAISE EXCEPTION 'A42363_OWNERSHIP_CHANGED'; END IF;
 IF (NEW.request->>'event') IS DISTINCT FROM NEW.event OR
 (NEW.request#>>'{resource,kind}') IS DISTINCT FROM NEW.resource_kind OR
 (NEW.request#>>'{resource,name}') IS DISTINCT FROM NEW.resource_name OR
 (NEW.request#>>'{resource,scope,token_id}') IS DISTINCT FROM NEW.token_id::text
 THEN RAISE EXCEPTION 'A42363_LEDGER_BINDING'; END IF;
 RETURN NEW;
END $$;
ALTER FUNCTION g1_control.resource_transition_guard() OWNER TO g1_control_owner;
REVOKE ALL ON FUNCTION g1_control.resource_transition_guard() FROM PUBLIC;
CREATE TRIGGER resource_transition BEFORE INSERT ON g1_control.resource_events
 FOR EACH ROW EXECUTE FUNCTION g1_control.resource_transition_guard();
-- Trigger owner must be granted only these exact reads; no membership in writer roles.
GRANT SELECT ON g1_control.g1_consumptions,g1_control.resource_events TO g1_control_owner;
GRANT UPDATE(token_id) ON g1_control.g1_consumptions TO g1_control_owner;
COMMIT;
