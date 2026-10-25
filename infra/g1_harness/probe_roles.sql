-- SOURCE ONLY / NOT RUN. Two candidate infrastructure statements, counted separately.
-- A complete owner initialization/credential service is still BLOCKED; this is NOT
-- an executable bootstrap migration or permission to run SQL in any existing DB.
CREATE ROLE g1_probe LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
 NOBYPASSRLS NOREPLICATION CONNECTION LIMIT 1;
ALTER ROLE g1_probe SET default_transaction_read_only = on;
-- Future reviewed owner adapter must: revoke PUBLIC database/schema/function rights,
-- set 100ms statement_timeout, assert zero role memberships/MAINTAIN/DDL/DML and grant
-- only CONNECT on the one new database. No credential is shipped here.
-- Missing owner adapter and full <=8 initialization statement contract are blockers.
