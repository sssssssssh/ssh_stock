# W02 / W03 Worker Regression Evidence

## Actual Defect

`abort_confirmed_writer()` previously accepted FAILED/ABORTED duplicates using
approval/operator/evidence only. It could report ALREADY_RECONCILED despite
another ledger token, active child or missing execution fingerprint. Its
fresh-session ACK reader rejected some of those cases, but still accepted
contradictory audit transitions and publication timestamps.

R4 shares one strict receipt predicate and active-child check between the two
paths. Matching owner/token, ABORTED ledger, absent publication timestamps,
execution fingerprint and RUNNING-to-FAILED audit transition are required.
Invalid duplicate recovery raises; invalid ACK evidence remains UNCONFIRMED.
Valid duplicates only roll back their read/lock transaction, do not consume
authority again, and do not append another audit. The ACK reader remains a
fresh REPEATABLE READ / READ ONLY transaction without writes or COMMIT.

## RED / GREEN Identity

RED uses production source from
`527f07593fc346f0448165e1f64dd6954eb798b4`, reconcile blob SHA-256
`a3684d7416888426156cc363fa0b5a2eb598232582688ff1750e3a193c239279`,
with the new regression module overlaid (not a claim that RED was in old Git).
GREEN is the patched source snapshot, then repeated by the final-SHA full
suite. See `evidence_index.json` and the PR closeout receipt for hashes.

| Execution | Result | Duration | Meaning |
| --- | --- | --- | --- |
| Pure unit RED, corrected fixture | 9 failed / 3 passed | 6.096 s | False success reproduced |
| Pure unit GREEN plus old contracts | 33 passed | 11.62 s | No DB/field proof |
| Real PG17 RED, corrected fixture | 5 failed / 1 passed | 16.73 s | Five false successes reproduced |
| Linux GREEN new unit/PG + unchanged Worker/parity | 66 passed | 487.28 s | Includes all three OFF/ON lifecycles |
| Clean historical Linux contract and native nodes | 14 passed | 11.046 s | Old positive/negative rules preserved |
| Clean input Linux native nodes | 3 failed | 2.85 s | All exact FROZEN_FILE_CHANGED |

The first unit fixture exposed fewer failures; its XML is retained. The first
PG fixture tried to mutate a terminal ledger and was correctly rejected by
PUBLICATION_IMMUTABLE. The corrected fixture inserts a separate inconsistent
imported snapshot for those two cases. No trigger, assertion or migration is
disabled. Likewise, an initial collection error from two new modules sharing
a basename is retained; the unit file was renamed, not skipped.

## Reproduction Commands

Only use explicitly provisioned marked PostgreSQL 17 with separately recorded
system identifier. The test helper verifies marker/identity before creating
and dropping its random test databases. Disable settings env-file discovery;
never copy production `.env` into the isolated checkout.

```bash
python -m pytest tests/unit/test_worker02_r4_receipt_contract.py
python -m pytest tests/integration/test_worker02_r4_recovery_receipt.py
python -m pytest tests/integration/test_business_worker_02_pg17.py tests/integration/test_business_worker_02_diagnostics.py tests/integration/test_worker02_revision.py tests/integration/test_worker02_r2.py tests/integration/test_worker02_r2_lifecycle.py
python scripts/ab_read_experiment_v14_a4_2.py --contract-only --output .codex_tmp/r4-contract/source.json
python -m ruff check backend tests migrations scripts
git diff --check
```

The existing PG17 modules run unchanged: real 57014/55P03/disconnect/JSONB
failure, lease/progress acknowledgement separation, monotonic observation,
owner/token/status CAS, cancellation and terminal dominance; authority
absence/revocation, child identity, Dirty/ABORTED/audit atomicity and unknown
ACK read-only reconciliation. Their XML nodes, failures and durations are
evidence, not a synthetic claim of a real production incident resolution.

## Native CI Failures

Archive/lookup/A4-1 each reproduce at the old exact-stage-path guard; A4-2
contract-only also records its own refusal artifact. The native Archive trace
is intentionally redacted; fresh Linux replay provides the actual stack.
Master already has the same named failures. No old test, historical manifest,
guard, workflow, release gate or coverage threshold is modified to turn red
green. Final exact-HEAD/PR-merge identities must be reported separately.

Full-suite platform failures are separate from SOURCE_CONTRACT. The VM uses
Linux 3.10; pidfd support cannot be inferred from Python 3.12. Missing compiler,
Node or shellcheck are not business fixes. Windows default-GBK and unsupported
dir-fd source checks are retained as platform observations, not Linux defects.
