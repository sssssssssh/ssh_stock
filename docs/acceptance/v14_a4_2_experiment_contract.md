# A4-2 Experiment Contract

Baseline: `f8df915febe24bce3f3bcdb8a52ae2f3a5b78e62`, clean master fast-forwarded
from `c9f3b1a`. Scope: laboratory design, SQL and ADR only; no production rollout.

Preceding exact-baseline CI: A4-1 run 39478378917 SUCCESS, V1.3 run 39478378950
SUCCESS, main run 39478379063 CANCELLED (not accepted as a green full suite).

`source_contract()` verifies Git blob identities for all backend/migrations/config,
the frozen profiler/summary and original acceptance/evidence. It separately records
checkout SHA256; Windows checkout line-ending conversion is not a source edit.
The previous receipts and profiler will not be rewritten. Production flag stays false.

## Dedicated Instance

Before importing Settings or performing any DDL, `verified_environment()` invokes
the existing physical gate: explicit loopback `_test` URL, PostgreSQL 17,
random `v14.test_instance` UUID and independently recorded physical system ID.
Wrong identity must fail before CREATE and before cleanup DROP. Each experiment
uses the existing UUID child-database/migration/finally-cleanup fixture.
No connection to the cloud business database is authorized, including diagnostics.

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
