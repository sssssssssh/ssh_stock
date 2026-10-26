-- REVIEW TEMPLATE ONLY, NOT RUN. Eight statements total including separate role audit.
-- psql quoted identifiers/literals shown for review; no psql/live launcher is supplied.
-- Values must come from sealed owner FDs, never argv/env or user request JSON.
REVOKE ALL ON DATABASE :"database_name" FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE ROLE g1_probe NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS NOREPLICATION
 PASSWORD :'probe_password';
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO g1_probe;
ALTER ROLE g1_probe SET default_transaction_read_only=on;
ALTER ROLE g1_probe SET statement_timeout=100;
-- The eighth SELECT is owner_role_audit.sql. GUC evidence is still CONFIGURED, not target-session proof.
