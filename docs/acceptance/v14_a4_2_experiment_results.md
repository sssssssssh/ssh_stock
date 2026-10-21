# A4-2 Isolated Experiment Results

Baseline: `f8df915febe24bce3f3bcdb8a52ae2f3a5b78e62`.
Core laboratory implementation: `e073b46`, followed by scoped-plan/final ADR work.
Status: **A4_2_NO_SAFE_WINNER**, acceptance in progress.
READ_PERFORMANCE_PASS: **NOT_CLAIMED**. A4-3/B/C authorization: **NO**.
Production path changes: **NONE**. Cloud business database touched: **NO**.

## Scope and Evidence

Production `backend`, `migrations`, `config`, A4-1 profiler/summary, original report
and original evidence remain unchanged. `source_contract()` verifies Git blobs
and separately records checkout SHA256. Only laboratory process-local patches,
UUID synthetic databases, scripts/tests/docs and an independent workflow are added.

Baseline CI: [A4-1 SUCCESS](https://github.com/sssssssssh/ssh_stock/actions/runs/39478378917),
[V1.3 SUCCESS](https://github.com/sssssssssh/ssh_stock/actions/runs/39478378950),
[main CANCELLED](https://github.com/sssssssssh/ssh_stock/actions/runs/39478379063).
These are baseline results, not evidence for the new HEAD.
Final HEAD CI: OPEN, not yet pushed at this report revision.

Local dedicated portable PG17.6 was freshly initialized with a random instance
marker and independently obtained physical ID. Every child uses the existing
verified UUID lifecycle and formal migrations, not `create_all`. DATABASE_URL is
overridden with synthetic credentials before Settings imports. No application
Worker, Scheduler, execution token, task state or historical candidate is operated.
Local CPU/RAM are not capped; network LOCAL_ONLY and cache_control UNCONTROLLED.
Cloud RTT, cold-cache behavior and production resource budgets remain UNPROVEN.

## Work Packages

| Package | State | Evidence |
| --- | --- | --- |
| W00 | PASS | Contract, frozen diff zero, physical mismatch before child DDL |
| W01 | PARTIAL | Five separate controls; full-read/commit/final verification schema; new full-scale receipts pending |
| W02 | PASS, negative decision | E1/E2 REJECTED; E3 UNPROVEN; real DML/ABA/savepoint counterexamples |
| W03 | PARTIAL | Five alternate SQL forms, golden tests; latest-code actual-plan scale matrix pending |
| W04 | PARTIAL | Six window sizes and real three-month service input caller; full matrix pending |
| W05 | OPEN | Fault/resource/reader probes and dedicated CI implemented; final scale runs pending |
| W06 | PASS, no authorization | ADR answers all eight questions without selecting an unproved winner |
| W07 | OPEN | Delivery paths present; final full regression/CI/results still required |

## Local Regression Receipts

All XML/log files below are ignored local artifacts, not source-controlled data.
Counts from separate invocations overlap and must not be added as unique tests.

| Command/scope | Actual result | Receipt |
| --- | --- | --- |
| Initial E0-E3 real PG proofs | 9 passed | `.codex_tmp/a42-evidence-mechanisms.xml` |
| Initial expanded SQL golden | 59 passed | `.codex_tmp/a42-sql-golden.xml` |
| Fault, source and physical gate probes | 31 passed, 69 deselected | `.codex_tmp/a42-final-probes.xml` |
| Latest native/closure/event/engine proofs | 10 passed, 86 deselected | `.codex_tmp/a42-latest-proofs.xml` |
| Latest summary/contract/resource units | 15 passed | `.codex_tmp/a42-latest-summary.xml` |
| Full pytest | RUNNING, 2355 collected | `.codex_tmp/a42-full.xml` / `a42-full.log` |
| Ruff backend/tests/migrations/scripts | PASS | local command |
| Workflow YAML parse / frozen source diff / diff check | PASS | local commands |

Two final summary tests and supplemental closure/event probes were added after
the full-suite collection; their separate receipts above do not imply inclusion
in that already-running collection. Final CI collects the final tree afresh.
Alembic parent `current` and `heads` both confirmed `0058_data_publication`.
No migration was added and no user-data downgrade test was run.

## Measurement Receipts

- `a42-w01-baseline.json`: 15 full-control trials, earlier script body, exploratory.
- `a42-10k.json` / log: interrupted v1, partial, retained. Its cumulative per-FETCH
  query text repeated excessively across trials; only its owned laboratory Python
  process was stopped. No business process was operated. It is not a performance
  acceptance receipt and was not overwritten by the replacement run.
- `a42-v2-10k.json`: completed 147 runs, 11 plan groups and 13 actual cursor plans;
  earlier script body before S3_KEYS/narrow S4/S5 and final measurement schema.
  It is exploratory, not exact-final-code performance evidence.
- Final-code 10k/100k/million serial runs: queued after full pytest; pending.

Exploratory v2 10k, fraction 0.1, complete read + commits + final verify, seconds:

| Path | p50 | p95 | Protection |
| --- | ---: | ---: | --- |
| Q0 raw | 0.279 | 0.284 | NOT_EQUIVALENT |
| Q0 service | 0.370 | 0.481 | NOT_EQUIVALENT |
| Q0 safety wrapper | 0.817 | 0.906 | Existing E0 |
| Q1 current | 0.742 | 0.742 | Existing E0 |
| Q2 current | 1.184 | 1.301 | Existing E0 |
| S3 | 0.885 | 0.986 | Existing E0 |
| S3 inline | 0.696 | 0.696 | Existing E0 |
| Earlier wide S4 | 0.730 | 0.863 | Existing E0 |
| Earlier wide S5 | 0.809 | 0.867 | Existing E0 |
| E3 prototype | 0.705 | 0.798 | UNPROVEN; retained E0 final SHA |

Three alternating repeats only; p95 is interpolated and not a robust tail SLA.
Nested phase medians cannot be added. This table does not establish the >=30%
million-scale goal or claim the latest SQL is fast. Latest script hashes, exact
head/dirty, counts/sizes, raw FETCH, SQL/auto_explain, resources, maintenance and
all slow samples are stored in each new receipt.

## Checklist

PASS below means the named regression assertion passed, not production approval.
OPEN/UNPROVEN are not silently converted into completed matrix coverage.

| ID | State | Evidence / limit |
| --- | --- | --- |
| T01 | PASS | Frozen all-field golden A-only |
| T02 | PASS | B-only golden; A unchanged |
| T03 | PASS | B overwrite golden |
| T04 | PASS | Tombstone golden |
| T05 | PASS | Wrong version/hash still masks A |
| T06 | PASS | Other-root golden |
| T07 | PASS | Corrupt redundant date/entity/payload/identity rejected before bounded SQL |
| T08 | PASS | Native full-field NULL/bool/timestamp/UUID/numeric and dtype golden |
| T09 | PASS | Month/year, explicit spring closure, 1/3/5/10/20 boundaries |
| T10 | PASS | Empty and partial windows, no synthetic fill |
| T11 | PASS | First preimage through update/delete/rebuild/savepoint |
| T12 | PASS | Same-tx reuse; explicit savepoint-reuse counterexample |
| T13 | PASS | Committed A update detected at next E0 check; E1 rejected |
| T14 | PASS | E3 committed A insert/delete probes and retained original E0 regressions |
| T15 | UNPROVEN (negative test PASS) | E1 ABA accepted; E3 bypass/rollback gaps; no strict all-events guarantee |
| T16 | PASS (unsafe E2 rejected) | Direct B corruption not trusted by E0 |
| T17 | PASS | Delete/version/hash masks and rebuild golden |
| T18 | PASS | Real Worker cancel, no partial frame or public mutation |
| T19 | PASS | Real Worker 57014, original publication isolation |
| T20 | PARTIAL | Disconnect path passed; final full-suite unknown-commit regression pending |
| T21 | PASS | Wrong token; frozen takeover regressions retained |
| T22 | PASS | Warmup source mutation aborts original publication |
| T23 | OPEN | RR2 probe implemented; latest million reader run pending |
| T24 | PARTIAL | Real lock probe available; final matrix hold/reader comparison pending |
| T25 | PARTIAL | Exploratory complete FETCH and EOF/close checks passed; final scale pending |
| T26 | OPEN | Exact million fixture helper reused; actual new matrix pending |
| T27 | PARTIAL | Actual service caller with 430-day bounds, carried root evidence; scale pending |
| T28 | PARTIAL | Actual cursors in earlier receipt; latest-code scale plans pending |
| T29 | PASS | Frozen source/schema/config; default flag unchanged |
| T30 | PASS | Wrong marker/system ID refused before child CREATE |
| T31 | PASS | Real ten-table engine/quality/atomic-publication golden for S3_KEYS/S4/S5 |
| T32 | PARTIAL | Production freeze verified; full frozen evidence regressions pending |
| T33 | PASS | Raw slow samples retained; outlier/incomplete/cross-scope receipt rejection units |
| T34 | PASS | NO_SAFE_WINNER, NOT_CLAIMED, no automatic next phase |

## Artifacts and Remaining Gates

The independent [A4-2 workflow](../../.github/workflows/ab-read-a4-2.yml) provisions
its own labelled PG17, 2 CPU/3 GB, marker and physical ID. It serializes three full
scales, actual plans, six windows, monthly reads, distribution/tombstone cells,
event-cost probes and million-scale RR2. It uploads only `a42-*.json/xml` through
the explicit hidden-file allowlist with `if-no-files-found: error`; large receipts
and private logs are not committed. Partial artifacts never constitute PASS.
Primary and supplemental jobs run serially (`max-parallel: 1`), each with its own
fresh instance. This separates GitHub job-duration budgets without increasing SQL
timeouts or reducing datasets. Primary validation requires every three-repeat
variant/fraction/window/month cell and its actual cursor plans, not just one plan.

OPEN: final exact-SHA main/A4-2 CI, complete scale/resource/reader matrix, final
regression and measured tables. UNPROVEN: strict all-writer event evidence,
production/cloud latency, controlled cold cache and cloud resource budgets.
Keep production off. Do not propose A4-3 on exploratory 10k results.
