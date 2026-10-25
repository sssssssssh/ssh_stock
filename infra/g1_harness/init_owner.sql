-- SOURCE ONLY / NOT RUN. Independently budgeted infrastructure session, NEVER probe SQL.
-- Fixed owner metadata query for a fresh synthetic PG17; no business relations.
-- Bootstrap owner may read pg_control_system only inside the isolated disposable cluster.
SELECT current_setting('server_version_num')::integer,
       system_identifier::text FROM pg_catalog.pg_control_system();
-- Controller must bind this result to actual fresh volume/image/namespace identity.
-- It cannot be accepted merely because caller JSON says pg_major=17.
