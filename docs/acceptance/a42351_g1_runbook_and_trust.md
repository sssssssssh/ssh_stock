# A42351 — G1 runbook and trust design (not authorization)

Status: G1_PREFLIGHT_READY_FOR_REVIEW; physical execution NOT_RUN_NOT_AUTHORIZED.
This document is a future checklist, not an executable runbook. This delivery creates
no database/container, performs zero real SQL, reads no business .env or /proc,
and does not issue a grant. Existing RealAdapter and all live CLIs still deny.

## Independent fixture evidence required before a later G1 decision

Use a newly created disposable synthetic PostgreSQL **17** instance, owned by an
independent trusted harness. Only exact 127.0.0.1 / ::1 or the dedicated local Unix
socket directory is proposed; no DNS alias, remote endpoint, shared existing database
or public port mapping. The offline Unix path is a design label, never opened here.
Future human review must bind all of:

- fresh fixture UUID, nonce, marker, database name/owner and creation receipt;
- observed server version and system_identifier, immutable image digest,
  container ID/namespace, loopback port/socket ownership and lifecycle;
- independent harness identity, requested exact full Git SHA and source fingerprint,
  CI run/attempt, and allowlisted synthetic template digest;
- destruction receipt for that owned fixture and independently observed absence.

Matching two self-reported JSON objects proves none of these physical facts.
An existing business database or unclear ownership is an immediate rejection.
No business tables, rows, provider tokens or user data are probe inputs.

## Least privilege and visibility, without escalation

Future role: separate read-only account, no SUPERUSER, CREATEDB, CREATEROLE,
BYPASSRLS, REPLICATION, MAINTAIN, writes, business read or default pg_read_all_stats.
The database owner is a separate harness identity; the probe must not inherit it.
Check memberships, role defaults, object grants and effective privileges independently.
For the current role, record exactly which fields of pg_prepared_statements and the
needed system views are visible for the **same session**. Invisible backend/statistics
fields mean NOT_PROVEN, not permission to add pg_read_all_stats or use an owner account.
No raw query text, parameter values, usernames, DSNs or backend secrets enter receipts.

## Proposed G1 budget, not approved

At most **16 tiny synthetic SQL statements**, total ≤2000ms, per SQL ≤100ms,
result ≤8 rows. Only pre-reviewed constant templates and the minimal read-only
pg_prepared_statements projection may be considered. Deadline accounting includes
all probe SQL; no hidden setup queries or retries. Signature and allowlist verification,
physical fixture attestation and cleanup must also have explicit bounds in a later plan.
These are **16 SQL statements, not 16 warmups**. Actual SQL in this delivery: **0**.
Effective warmups remain 8. G2 candidates 16 or 32 are separate unapproved alternatives.

## Future authorization trust (currently absent)

A future request needs an independent human-approved full 40-character SHA, source and
overlay fingerprint, run ID/attempt, trusted issuer, issued/expiry time, exact fixture
and nonce, scope SYNTHETIC_CAPABILITY_ONLY, immutable allowlist and resource budget.
It requires real signature verification and persistent, atomic once-only consumption
**before** any operation, plus bounded redacted refusal/audit receipts. Replay,
nonce reuse, expiry, mismatched attempt or scope must fail closed.

The current code has **no real signature verifier or persistent consumer**. Mock
FutureGrantDesign is only a negative-test schema. Environment variables, CLI flags,
tokens, a push, dispatch, clean Git, static overlay verification and matching mock
claims cannot authorize G1. No registered profile, Environment or policy is changed.
G1 approval would not approve G2 or G3, and old one-shot permissions are not reusable.

## Failure, cancellation and cleanup

Before connection: reject ambiguous identity, nonlocal/possibly business endpoint,
overprivilege, invalid grant/nonce or unavailable trusted evidence. During a future
probe: first error remains sticky; stop on timeout, cancellation, identity drift or
unknown state, retain bounded partial receipts and independent cleanup errors in order.
No retry, fallback role, alternate database, business read or automatic escalation.
Cleanup is limited to a proven-owned fixture; absence of independent destruction
evidence stays NOT_PROVEN. Never report CLEANUP_VERIFIED from a JSON claim, a failed
connection, an attempted cleanup or a timeout. Actual probe/cleanup here: NOT_RUN.

## UNVERIFIED matrix

| Capability | Execution | Proof | Blocking evidence |
|---|---|---|---|
| FIXTURE_IDENTITY | NOT_RUN | NOT_PROVEN | independent physical binding |
| ROLE_PRIVILEGE | NOT_RUN | NOT_PROVEN | effective role/grants/visibility |
| PREPARED_SAME_SESSION | NOT_RUN | NOT_PROVEN | exact driver/session identity |
| CACHED_PLAN_STRUCTURE | NOT_RUN | NOT_PROVEN | trustworthy non-disturbing method |
| BACKEND_CPU | NOT_RUN | NOT_PROVEN | bidirectional PID/namespace mapping |
| LONG_WINDOW | NOT_RUN | NOT_PROVEN | real full tick brackets/budgets |
| CLEANUP_AUDIT | NOT_RUN | NOT_PROVEN | independent owned-fixture destruction |

Offline design tests exercise rejection and modeled geometry only. Ordinary existing
CI PG17 micro/migration tests are legacy regressions, not new G1 execution or proof.

## Static overlay trust separation

Historical frozen tree 7681b57 remains immutable. The new manifest pins the exact
Reviewer/test/new-contract byte hashes; guard pins that manifest's SHA256 and exact
changed path set against 55bd6328. Every stage file is compared with its exact HEAD
blob; all protected working bytes are compared to HEAD objects even if Git index flags
hide a change. The fingerprint is derived from independently read HEAD + manifest +
patch hashes and included in A4235 source_sha256; frozen_sha256 keeps its historical
tree meaning. check_static additionally requires caller full target == HEAD ==
origin/master and a clean tree, rejecting ambient DB/proxy inputs.

The manifest cannot embed its own containing commit SHA without a hash cycle;
HEAD therefore comes from Git and the separately supplied exact target/remote, never
from a candidate bundle. Guard/manifest integrity is static source review, not a
human approval signature. A commit changing the verifier itself is outside that trust
assumption and must be independently reviewed. No claim of cryptographic authorization
or G1 readiness is inferred from this static binding.
