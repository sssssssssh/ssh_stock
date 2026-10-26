# A42362 Schema and Budgets

## Dedicated Control Schema, NOT RUN

001_control.sql remains byte-identical. 002_services.sql is review-only DDL for a NEW,
separately approved control plane, not an Alembic migration or live upgrade.

- external_imports: immutable external attestation digest and canonical record.
- registry_events: globally increasing key-status revision.
- approval_records/revocations: immutable approvals and revocations; no status-history rewrite.
- consumed_payloads: complete verified payload committed with the original one-shot consumption.
- resource_events: unique event ID and (token,kind,name,event), full ownership Scope,
  sequence/commit time; append-only trigger, no UPDATE/DELETE/TRUNCATE to actors.
- absence_events: separate E insert privilege; C/worker/owner cannot insert it.

A registry change takes the same exclusive advisory lock for which B takes a shared lock.
Any registry revision invalidates all older unconsumed approval epochs (conservative).
A new approval must be independently issued; existing records/tokens cannot be reset.
Approval revocation and B consumption share row locks. SQL functions are SECURITY DEFINER
with fixed search_path, PUBLIC execute revoked. Actual PostgreSQL concurrent crash/ACL
behavior is NOT_RUN_NOT_AUTHORIZED, not proved by a threading lock/transaction double.

Roles: g1_approval_writer imports via a fixed function; g1_consumer consumes/appends resources;
g1_receipt_reader reads committed facts; g1_auditor inserts only separate absence facts.
Roles/schema/functions must be independently provisioned/reviewed; no helper applies this DDL.

## Statement and Command Ledger

Fixed probe schedule/allowlist remains unchanged: 6 I4 + 6 I8 + 4 projections =16,
single100ms/window2000ms/at most8 rows. No identity/SHOW query has been added to this schedule.
B/A control-store transactions are not probe statements and cannot run without installed roots.

Owner review template lists seven initialization statements in owner_bootstrap.sql, with
owner_role_audit.sql as the eighth SELECT. It is NOT an executed or complete initialization
adapter. The audit template still does not independently prove the probe's session settings
or all raw physical metadata/ownership. INIT_STEPS is a planning ledger, not executable SQL.
Max12 commands/2000ms remain unchanged; no DO block hides extra SQL and no ninth statement
is silently added to cure missing evidence. An infeasible implementation must stop.

Termination/cleanup/artifact remain2000ms each. Runtime commands use fixed operation sets
and exact resources, never a prefix prune. Private rootless Podman runtime env and actual
distribution/namespace/GID/cgroup compatibility remain PLATFORM_NOT_VERIFIED.
