# A4-2 Experiment Contract

Baseline: `f8df915febe24bce3f3bcdb8a52ae2f3a5b78e62`, clean master fast-forwarded
from `c9f3b1a`. Scope: laboratory design, SQL and ADR only; no production rollout.

Preceding exact-baseline CI: A4-1 run 39478378917 SUCCESS, V1.3 run 39478378950
SUCCESS, main run 39478379063 CANCELLED (not accepted as a green full suite).

`source_contract()` verifies Git blob identities for all backend/migrations/config,
the frozen profiler/summary and original acceptance/evidence. It separately records
checkout SHA256; Windows checkout line-ending conversion is not a source edit.
The previous receipts and profiler will not be rewritten. Production flag stays false.

The old A4-1 unit guard additionally compares raw checkout bytes with `git show`.
On a Windows CRLF checkout it can fail even when Git blobs are identical. Run
the frozen suite in a new disposable LF checkout (`git -c core.autocrlf=false
clone --shared . <new-owned-lab-directory>`, then set that clone's local
`core.autocrlf=false`); do not rewrite production files or weaken its assertion.
Do not copy the business `.env` there. Use explicit synthetic DB/token settings.
For full pytest, leave `LLM_ENABLED` unset: the default remains disabled while
dotenv-priority tests may enable their mocked endpoint without an OS override.

## Dedicated Instance

Before importing Settings or performing any DDL, `verified_environment()` invokes
the existing physical gate: explicit loopback `_test` URL, PostgreSQL 17,
random `v14.test_instance` UUID and independently recorded physical system ID.
Wrong identity must fail before CREATE and before cleanup DROP. Each experiment
uses the existing UUID child-database/migration/finally-cleanup fixture.
No connection to the cloud business database is authorized, including diagnostics.

Fixture cardinality uses a single-snapshot named cursor over ALL published A and
ALL B rows, not LIMIT/first-batch sampling. The client counts A/current-root B/
other-root B through EOF with 5000-row bounded transport, then requires exact
agreement with requested cardinalities. Receipt proof includes cursor name,
closure, rows, batches, completion and total census time. A failure never returns
partial counters as actual counts. The original aggregate census failed locally
at the unchanged 300-second budget; its failed receipts are retained. This
setup-only transport change neither changes benchmark SQL/T3/T4/T8 nor raises
timeouts or reduces data. Census time is NOT credited as a read-performance gain.
It also warms caches; every control follows the same census with cache resets
UNCONTROLLED. Source hashes additionally freeze the reused seed/gate/golden helpers.

Taskbook path mapping: the unit file is named
`tests/unit/test_ab_read_experiment_contract_v14_a4_2.py`; integration retains
`tests/integration/test_ab_read_experiment_v14_a4_2.py`. Identical basenames collide
under this repository's existing pytest prepend mode. No global test/import
configuration or package layout was changed to hide that collection failure.

Local provisioning uses a newly initialized portable PG17 data directory and a free
loopback port, NOT the prior test cluster or the running application database.
Read the expected system ID from `pg_controldata` for that directory, and set the
random marker at server launch. Explicitly set synthetic DATABASE_URL and
TEST_DATABASE_URL before any pytest import. LLM/Provider calls are disabled.
Stop only the owned laboratory cluster after all tests have exited.

CI provisions a separate disposable PG17 container with label, UUID marker,
independently recorded system ID, CPU/memory limits and always-upload receipts.
Local Windows is LOCAL_ONLY/cache UNCONTROLLED; it is not a 2-CPU/3-GB cloud result.

## Fair Comparators

Q0_LEGACY_RAW and Q0_SERVICE_CONTROL retain their lack of T3/T4/T8 and are explicitly
NOT_EQUIVALENT. Q0_SAFETY_EQUIVALENT wraps the unchanged Q0 SELECT with the exact
E0 prepare/final verify and the same complete-frame sort as Q1/Q2. This is
equivalence to the existing E0 observation contract, NOT proof of detecting an
unobserved A-to-A'-to-A between checks. Such a stronger claim requires events.

Every protected comparison includes complete named-cursor FETCH, whole-frame
construction/sort, commits and final source verification. SQL/driver nested timers
are attribution only, never added to wall-clock totals. Alternate trial order;
retain every slow run and negative experiment. No increased timeout or reduced
fixture can produce a performance PASS. Monthly reads preserve overlapping input
and root evidence across commits, without invoking or changing financial engines.

Single-read and window controls always include their final verification. A true
Jan/Feb/Mar root chain commits each read but verifies the whole read set only at
the March tail, matching the unchanged publication lifecycle. Each next read
still runs the original E0 A/B guards. Sum the three actual sample spans first,
then compute chain medians; never add three independent monthly medians. Earlier
a6679c8/63f289e periodic-final controls remain labelled legacy receipts, not a
measurement of this one-tail root lifecycle. Final CI rejects missing T8 in a
protected full/window read and extra/missing T8 in a new monthly chain.
