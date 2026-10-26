# ADR: target session projection and fresh-fixture initialization

Decision is **NOT APPROVED**. session_method() remains unconditional
METHOD_BLOCKED_NEEDS_PROTOCOL_DECISION. No flags, CLI, environment, token or green CI
can approve it. The following bytes are a proposal only; no probe SQL was executed.

## A: one replacement projection within the existing four projection slots

Complete driver AND wire SQL, ASCII406bytes, no trailing LF:

```sql
SELECT current_setting('statement_timeout') AS statement_timeout, current_setting('transaction_read_only')::boolean AS read_only, p.name,p.parameter_types::oid[],p.from_sql,p.generic_plans,p.custom_plans FROM (SELECT 1) AS singleton LEFT JOIN LATERAL (SELECT name,parameter_types,from_sql,generic_plans,custom_plans FROM pg_catalog.pg_prepared_statements ORDER BY name LIMIT 8) AS p ON true ORDER BY p.name
```

SQL SHA256: `2f2f912b70ec0fe9c81c17c9098d8c2208a54e78ba69277bfe49c1bcf5986b56`.
Input parameters/OIDs: none / `()`. Output columns/OIDs:
statement_timeout:text25, read_only:bool16, name:text25,
parameter_types:oid[]1028, from_sql:bool16, generic_plans:int8/20, custom_plans:int8/20.
The LEFT JOIN gives one metadata row even with no prepared statements; nullable plan
columns must be treated as absence, never a fabricated cached plan or zero metric.
The two GUCs must be present and equal100ms/true on every returned row. Any null,
inconsistent value, server error or unexpected OID fails closed before probe progress.

Old allowlist: `d0aa6b635b0eb35eb373e0b1fa003593535eac68dd07bc3445b6c80d9ef752f8`.
Candidate allowlist using the unchanged digest algorithm and only this PROJECTION
replacement: `9b4a128a2cfb0c2c44d7eb70ab0e6d311162c902a53a3e96fb34eb0ca130d571`.
This hash is not installed. I4/I8 bytes and their parameter OIDs23/20 are unchanged.
Execution count remains6I4+6I8+4projection=16, additional executions0, max8rows,
100ms each/2s window, natural GC unchanged. G2 remains a different pending total8.
Changing projection shape also requires a new parser, session-v2 provenance, new
protocol/version-bound grant and independent approval. No consumed old grant is reused.
Keep old code/protocol/allowlist immutable and disabled; no silent parser fallback.
Rollback keeps the gate and all consumption/UNKNOWN history, never refunds tokens.

## B: unchanged SQL and independently sufficient server/OS proof

No sufficient chain is available. Another backend's SHOW/pg_settings, role defaults,
PQoptions or a self-hashed Owner response is not target-session truth. A bounded
same-backend monitor extension would itself need new reviewed source/platform/permissions.
It is not implemented, installed or assumed. Status INSUFFICIENT_EVIDENCE.

## C: retain block

Selected current path. Worker cannot obtain executable credentials or first SQL.
No seventeenth query, GUC query disguised as initialization or extra warmup is allowed.

## Fresh fixture initialization: separate decision, not free hidden SQL

InitializationPlan explicitly exposes CREATE DATABASE + the existing8 statements,
a **minimum9** counted owner SQL. Runtime command lower bound also needs review:
four-resource creation uses6Podman calls; prepared inspect1; start pre-inspect/start/
post-inspect3; readiness inspect1; independent Owner before/after inspection adds at
least6, already17>12 before image bootstrap commands. E's independent readonly calls
and cleanup have separate budgets, never reset or refund initialization counters.
The initializer refuses9>8 before any resource/credential/connection operation.

The9-statement list is a lower bound, not a complete approved authentication plan:
the inherited CREATE ROLE has no SCRAM password. A pinned image's initdb, mount UID/GID,
pg_hba/peer mapping or sealed password initialization must be specified and counted;
POSTGRES_DB/entrypoint-created database is not an exemption. The candidate image
entrypoint referenced by the container command is not supplied/installed/proven here.
Do not treat health/socket existence as restricted-role authentication or PG_READY.

Protocol owner must choose: a newly reviewed bounded bootstrap contract with explicit
init/auth budgets, or a separately audited prebuilt empty isolated fixture contract.
Both require new protocol/version identity and safety tests; neither is authorized
by this source-only task. Current code therefore cannot claim source/physical readiness.
