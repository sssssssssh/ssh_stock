# WORKER-02 revision — SOURCE_PARTIAL_BUT_IMPROVED, not ready to merge

Review baseline: 4d183857cdf42e4f9e75bd2a78c792f0ef3847e3, master
75076eac443d935d622bf59e12aad20ce5aba85e. Branch remains codex/biz-worker-02,
draft PR https://github.com/sssssssssh/ssh_stock/pull/1. No merge/deployment.

## W00 / W01: evidence and independent contract decision

[Baseline](WORKER_02_revision_baseline.md) and [190-node inventory](WORKER_02_revision_failures.json)
retain original classifications, trace hashes and raw artifact hashes. Old failures
are not called business regressions or contract conflicts without their actual reason.
Independent 2779a2a clean checkout verify returned
8c296818dfd1522cea16c1b952696c49b61ce5992f27d3357c0d90f3e78b5770;
19 original business-source/guard cases including tamper negatives passed.
Current ordinary guard still rejects the unchanged historical contract.

Independent reviewer identity, signatures and approval ID remain absent. The
[revision source inventory](WORKER_02_revision_contract_PROPOSED.json) is inactive,
not a manifest migration or an approved dispatcher. Historical manifests, guards,
tests, workflows and real experiment entries are untouched. CONTRACT_MIGRATION_BLOCKED.

## W02: heartbeat communication and failed commits

job_run records the lease CAS affected-row count as well as the four original
UPDATE/COMMIT timings. A zero-row CAS or unknown lease COMMIT ACK cannot create a
confirmed communication timestamp. Progress failure after durable lease keeps that
lease; no global/SQL timeout change. Existing real 57014/55P03 regressions remain.

job_worker tracks HEARTBEAT_DEGRADED, last confirmed lease, consecutive failures,
safe phase/SQLSTATE and unconfirmed duration; optional metadata writes are bounded
independent CAS transactions. A failed telemetry write is explicitly unconfirmed,
not a reason to release/replay the computation. Job GET derives stale degradation
read-only and never turns it into a task terminal status or proves computation.
Two real committed transactions with injected lost client ACK test lease_commit
and progress_commit separately; rollback/session reuse and RUNNING preservation
are asserted. This is a controlled post-commit client fault, not a captured field ACK.

## W03 / W08: guarded recovery remains unavailable in production

[Authority proposal](WORKER_02_recovery_authority_proposal.md) requires complete
multi-host inventory, durable independent dual approval/revocation/consumption,
frozen claims and fresh process/transaction proof. No signer/service/credential/
control-plane trust is installed. RECOVERY_AUTHORITY_NOT_INSTALLED; dry-run only.

Internal RecoveryApproval optionally accepts complete timezone-aware validity bounds
(maximum 5 minutes), rejects expired/future/revoked evidence and rechecks before
commit. Original internal v1 interface is retained for old tests, not approved as
a production authorization format. A proposed installed service must reject v1.
Different/queued active children and mismatched approval replay remain refused;
normal ABORT/Dirty, first error, candidate ledger, owner/token CAS and unknown-ACK
no-retry are preserved. LocalTestAuthority is not promoted to a production method.
[Read-only runbook](../runbooks/WORKER_02_readonly_recovery.md) lists independent
Docker/PG facts and the sequence; none is run on business infrastructure here.

## W04: installed ordinary Worker diagnostic lifecycle

Settings.worker_diagnostics_enabled / WORKER_DIAGNOSTICS_ENABLED defaults false,
separate from calculation policy and all optimization flags. Ordinary claimed data
jobs install one root-scoped ExecutionDiagnostics before dispatch. Periodic heartbeat
snapshots and final success/failure/cancel/unconfirmed snapshots use independent
short-transaction owner/token CAS JSONB merge. They cannot commit/rollback a pinned
main Connection, change cancel/publication/progress keys or replay computation.
Context is reset even on workspace cleanup failure. Observer snapshot failure does
not kill the heartbeat. A final unconfirmed receipt cannot be overwritten by a live
heartbeat; terminal task CAS refuses a late live snapshot.

Registered labels and finite nonnegative numeric values only; 128 groups / 32 recent,
visible dropped_metrics on overflow. Missing phase is NOT_INSTRUMENTED. Raw preflight,
trade-status SQL/FETCH/frame/compute/materialize/replace, candidate lookup/store,
factor compute and publish intervals are recorded in actual Worker tests. Factor
input-window frame intervals are recorded only when that optional path actually runs;
the disabled path stays NOT_INSTRUMENTED, not 0. Nested intervals are not summed;
FETCH combines server cursor, transport and Python materialization.

Real opt-in ON/OFF Worker runs compare factor/trade-status fields, pandas dtype and
hash exactly; only existing per-run provenance UUID/time is excluded from that
financial comparison. This is correctness evidence on a small seeded input, not
capacity, network-only timing, performance acceptance or a full finance Golden replacement.

## W05: observed DB backend identity, not process exit proof

core.db's transaction event registers server-returned application_name, actual PID,
backend_start, database OID, postmaster_start and observation timestamp. Names use
fixed ASCII role/root UUID/token fingerprint, under 64 bytes; no raw token, DSN,
host/address, query text, parameters or Raw. Main, heartbeat and diagnostic roles
are separate. First/latest per role is bounded; SET LOCAL clears pool reuse.
The main connection includes candidate writes on the existing pinned workspace;
no new candidate SQL, formula, transaction boundary or database schema is introduced.

Read-only data_job_diagnostics/reconcile matches the full observed backend tuple,
not just a forged name. Real PG17 tests hold an original transaction and a second
connection with the same label: REGISTERED_BACKEND_FACT_MATCH versus NAME_ONLY_UNVERIFIED.
No match remains EXECUTION_UNCONFIRMED. Legacy unlabelled sessions/all-host exit
cannot be established by these facts; no new recovery permission follows.

## W06 / W07: explicit resource and acceptance gaps

Resource precheck measured 2,090,057,728 available bytes versus a 4GiB planning
reserve. The target remains 1,443,097 rows × 3 rounds; 0 measured. This is an estimate,
not measured OOM or proven minimum memory. Full 1/3/12-month performance/G1/million-row
work is not run, SQL/DDL optimization not selected: RESOURCE_DEFERRED / PERFORMANCE_OPEN.

Relevant regression before final full run: 146 passed, 0 failed/errors/skips,
111.78s, followed by 6/0 approval/queued-child checks after the last narrow guard
change. These are not full-suite or final-SHA CI claims. Original RED truly failed
with KeyError execution_diagnostics after actual Worker success. One intermediate
new test basename collision and one FakeDb compatibility regression were fixed;
their original failed outputs remain in evidence. No original assertion was changed.
[Pre-full audit](WORKER_02_revision_validation.json) pins the actual XML hashes.

Full pytest and four ordinary workflows must be reported with their actual source
and checkout SHA in final delivery; PR merge checkout cannot be substituted for HEAD.
Linux local Docker daemon is unavailable; unsupported /proc/peer/kernel/tool cases
are not skipped or rewritten. If native CI stops before full Linux pytest at the
unsigned contract, AT20 remains BLOCKED/NOT_VERIFIED regardless of local pass count.
No source is declared SOURCE_FIXED_PENDING_FIELD_VALIDATION or READY_TO_MERGE.

## AT01–AT22 disposition and rollback

| AT | Evidence / remaining boundary |
|---|---|
| 01–02 | exact review/master/PR identities; 190 original nodes, raw hashes retained |
| 03 | historical clean checkout + 19 original tests including negative cases |
| 04 | unsigned proposal only; BLOCKED |
| 05–06 | latest SHA native workflow receipts delivered after push; no costly dispatch |
| 07–11 | unchanged PG17 timeout/lock/owner/unknown-ACK tests + health/rowcount evidence |
| 12 | readonly real PG17 reconcile always denies release |
| 13 | no independent installed all-host proof; production BLOCKED |
| 14–15 | expiry/revoke/child/unknown ACK/CAS/ABORT internal tests; no field authority |
| 16–17 | actual Worker lifecycle, periodic snapshots, bounded safe labels, cleanup isolation |
| 18 | real registered vs forged backend; pool cleanup, no absence-as-exit inference |
| 19 | real ON/OFF financial fields/dtypes/hash; original finance tests unchanged |
| 20 | full results delivered separately; supported Linux full remains blocked if gate stops |
| 21 | RESOURCE_DEFERRED, actual 0 rounds, no substituted smaller capacity |
| 22 | PR stays draft; NOT_READY_TO_MERGE / FIELD_NOT_RETESTED |

Code-only rollback to the reviewed prior branch commit; no schema downgrade,
clear/reset/delete/retry or audit erasure. Before any separately approved deployment,
prove old executors safely stopped; never hot-edit their content identity. Owned
synthetic test PG17 is stopped after validation. No business .env/cloud DB/TuShare,
G1 physical resources or production running tasks were accessed or changed.
