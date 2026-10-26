-- REVIEW ONLY: eighth initialization SQL. Does NOT inspect the probe's actual session GUC.
SELECT r.rolname,r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolinherit,r.rolbypassrls,r.rolreplication,
 EXISTS(SELECT 1 FROM pg_auth_members m WHERE m.member=r.oid) AS has_memberships,
 has_database_privilege(r.oid,current_database(),'CONNECT') AS can_connect,
 has_database_privilege(r.oid,current_database(),'CREATE') AS can_create,
 has_database_privilege(r.oid,current_database(),'TEMP') AS can_temp,
 EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname='public'
        AND has_schema_privilege(r.oid,n.oid,'CREATE')) AS public_create,
 EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')
        AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','f')) AS business_objects,
 EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND has_function_privilege(r.oid,p.oid,'EXECUTE')) AS public_execute
FROM pg_roles r WHERE r.rolname='g1_probe';
