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
Final HEAD CI: see the exact pushed SHA in Actions; no result is pre-certified here.
The checklist below records local executions separately from the independent
workflow's required matrix. A local OPEN is not proof that a remote run passed.

Local dedicated portable PG17.6 was freshly initialized with a random instance
marker and independently obtained physical ID. Every child uses the existing
verified UUID lifecycle and formal migrations, not `create_all`. DATABASE_URL is
overridden with synthetic credentials before Settings imports. No application
Worker, Scheduler, execution token, task state or historical candidate is operated.
Local CPU/RAM are not capped; network LOCAL_ONLY and cache_control UNCONTROLLED.
Cloud RTT, cold-cache behavior and production resource budgets remain UNPROVEN.

Taskbook output mapping:

| Requested artifact | Actual location |
| --- | --- |
| `v14_a4_2_baseline_receipt.json` | Per-size `a42-10k/100k/million.json` in CI; local final runs use `a42-final-*` |
| `v14_a4_2_window_matrix.json` | Same raw receipts, `runs` where `scope=window_matrix`; each keeps all cursors/metrics |
| Per-S SQL and plans | `sql()` in the laboratory script and raw `plans` grouped by SQL/fraction/scope/width |
| Unit file with duplicate basename | `tests/unit/test_ab_read_experiment_contract_v14_a4_2.py`, avoiding existing pytest import collision |

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
| Failure SQLSTATE/catalog snapshot regression | 2 passed, fault injection | `.codex_tmp/a42-failure-receipt.xml` |
| Final laboratory suite plus dotenv isolation | 117 passed, 100 warnings | `.codex_tmp/a42-final-targeted.xml` |
| Final census/root-tail protocol suite plus dotenv | 124 passed, 103 warnings, 1009.59 seconds | `.codex_tmp/a42-final-protocol-tests.xml` |
| First full pytest | 2353 passed, 2 environment failures | `.codex_tmp/a42-full.xml` / `a42-full.log` |
| LF checkout/environment recheck | 32 passed, including both failures | `.codex_tmp/a42-environment-recheck.xml` |
| Full pytest in clean LF checkout | 2361 passed, 591 warnings, 4034.00 seconds | `.codex_tmp/a42-full-clean.xml` / `a42-full-clean.log` |
| Ruff backend/tests/migrations/scripts | PASS | local command |
| Workflow YAML parse / frozen source diff / diff check | PASS | local commands |

The first full collection had 2355 items. Six supplemental cases were included
in the clean 2361-item rerun. Two later failure-receipt regressions ran separately
and are included in the 117-item laboratory/dotenv suite. Seven later protocol/
census cases are included in the 124-item final suite. Counts overlap;
do not add them as unique tests. Final CI collects the final tree afresh.
Alembic parent `current` and `heads` both confirmed `0058_data_publication`.
No migration was added and no user-data downgrade test was run.

First full-suite failures were the frozen A4-1 raw-byte guard (Windows CRLF vs
Git LF) and the EAS dotenv-priority test (laboratory OS `LLM_ENABLED=false`
overrode its explicit fixture dotenv). Both pass unchanged in an owned LF clone
without the business `.env` and without the LLM OS override. The first failure
XML/log remains intact. The clean full rerun completed independently; it is not
replaced by those 32 tests.

## Measurement Receipts

- `a42-w01-baseline.json`: 15 full-control trials, earlier script body, exploratory.
- `a42-10k.json` / log: interrupted v1, partial, retained. Its cumulative per-FETCH
  query text repeated excessively across trials; only its owned laboratory Python
  process was stopped. No business process was operated. It is not a performance
  acceptance receipt and was not overwritten by the replacement run.
- `a42-v2-10k.json`: completed 147 runs, 11 plan groups and 13 actual cursor plans;
  earlier script body before S3_KEYS/narrow S4/S5 and final measurement schema.
  It is exploratory, not exact-final-code performance evidence.
- Final-code `a42-final-10k.json` and `a42-final-100k.json`: COMPLETE, clean LF
  checkout `a6679c85fad4153725c7664bd1c81e64afaee4ec`, 177 full reads and 59 actual
  plan groups each, golden PASS. Output 9471 / 120592 rows respectively.
- `a42-final-million.json`: FAILED during actual-count verification at script
  a6679c8 line 402, OperationalError, zero timed trials. The old harness did not
  retain SQLSTATE or partially collected fixture metadata; exact database reason
  is UNKNOWN, not assumed to be 57014. Existing five-minute timeout was not raised.
  A concurrent owned-instance metadata probe observed approximately 5708 MiB
  candidate table + 1007 MiB indexes + 648 MiB public A; these are rounded manual
  observations, not a completed million capacity receipt or golden output.
- The failed raw receipt remains unchanged. Later instrumentation saves catalog
  metadata before counting, explicit phase and safe SQLSTATE; its real migrated
  fixture regression injects a 57014 count failure and verifies retained evidence.
  This synthetic regression does not establish the original failure's SQLSTATE.
- The primary shell stopped and its dependent local supplemental queue refused
  to run on an incomplete million receipt. No skipped matrix cell became PASS.
- `a42-retry-million.json` at 63f289e: FAILED again before timed reads, now with
  SQLSTATE **57014** and `phase=fixture_count_verification`. The full catalog was
  preserved: candidate table **5,984,976,896 bytes**, indexes **1,055,498,240**,
  total **7,040,475,136**; public A table **679,362,560**, indexes **159,416,320**.
  These are verified physical sizes, not completed cardinality or read metrics.
  SQLSTATE proves QueryCanceled at the census, not a business-path root cause.
- The final harness replaces only this setup aggregate with an exact full
  single-snapshot named-cursor census, retaining the same 300-second per-statement
  budget. Independent aggregate equality and interrupted-census regressions pass.
  Full-scale final-head execution remains a CI gate; setup time is not read gain.
- All 15 local distribution/deletion cells passed at 63f289e, **225 complete
  reads**: A-only/B-only/partial/high/mismatched times tombstone 0/1/10%.
  These use small fixtures and prove equality, not distribution-scale performance.
- E3 local 100k control passed 45 complete reads at 63f289e. It retains the old
  periodic-final monthly protocol, not the corrected one-tail root lifecycle.
  Full-read fraction .1 p50/p95: Q0 safety 7.1012/8.1214, Q1 7.0806/8.5532,
  E3 7.9148/10.7228 seconds. E3 is slower here and remains UNPROVEN regardless.
  Trigger installation was .1430 seconds; six zero-row statement probes used
  0 WAL bytes without events and 672 with events (whole-instance attribution,
  lower-bound probe, NOT writer-throughput evidence).

### Small-Scale Results At a6679c8

Complete read + commits + final verify, three alternating repeats. Each cell is
p50 / p95 in seconds. No scale extrapolation or cross-environment speed claim.

| Path | 10k fraction .1 | 10k fraction 1.0 | 100k fraction .1 | 100k fraction 1.0 |
| --- | --- | --- | --- | --- |
| Q0 raw, NOT_EQUIVALENT | .3017 / .3048 | .2643 / .3034 | 2.0885 / 2.1176 | 2.0063 / 2.2317 |
| Q0 service, NOT_EQUIVALENT | .3411 / .4754 | .3237 / .3692 | 2.1298 / 2.2304 | 2.1192 / 2.1797 |
| Q0 safety wrapper | .6424 / .7571 | .7738 / .9553 | 6.8510 / 7.6382 | 6.3723 / 7.3997 |
| Q1 current | .6771 / .6783 | .6385 / .7754 | 6.6329 / 9.0965 | 6.4471 / 6.7617 |
| Q2 current | 1.1299 / 1.1985 | 1.2204 / 1.2380 | 7.0900 / 7.6806 | 6.9574 / 7.0703 |
| S3 | .7814 / .7950 | .7221 / 1.2213 | 6.8415 / 7.4214 | 7.5890 / 7.6873 |
| S3 inline | .7641 / .8492 | .8524 / 1.0270 | 6.7367 / 9.0918 | 6.9235 / 6.9261 |
| S3 narrow keys | .7251 / .7545 | .8439 / 1.1250 | 6.5121 / 7.2627 | 6.5598 / 6.6445 |
| S4 | .6655 / .7138 | .7333 / .8209 | 6.4929 / 6.5246 | 6.2960 / 6.6905 |
| S5 | .7635 / .8272 | .7684 / .8085 | 6.6526 / 6.8408 | 6.5669 / 7.5145 |

At 100k, S4 vs Q1 p50 improves 2.11% (.1) / 2.34% (1.0), not 30%.
At 10k some alternatives regress; neither planner fraction is a universal winner.
These observed small-scale facts do not decide the unmeasured million case.

100k fraction .1 nested medians, seconds (overlap; **do not sum medians**):

| Path | T3 fingerprint | T4 B SQL | T8 final SHA | Read-stage + verify lock hold | Frame | Sort |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Q0 safety | 2.0724 | .2790 | 1.8557 | 6.6151 | .4795 | .0350 |
| Q1 | 1.8874 | .2717 | 2.1751 | 6.3755 | .4068 | .0287 |
| Q2 | 2.0684 | .2620 | 2.0878 | 6.9564 | .4260 | .0424 |
| S3 narrow | 1.9449 | .2685 | 2.0412 | 6.3917 | .4382 | .0307 |
| S4 | 2.0342 | .2728 | 1.9003 | 6.3452 | .4144 | .0318 |
| S5 | 2.3303 | .2675 | 1.9291 | 6.5262 | .4324 | .0380 |

100k S3 window matrix, fraction .1, total p50/p95 seconds:
None 6.7518/6.8240; 1 day 9.0441/10.9124; 3 days 7.1637/8.0999;
5 days 6.9004/6.9519; 10 days 7.0211/7.9603; 20 days 7.1463/7.8060.
All windows retain closed dates. Smaller FETCH tail alone is not lower total cost.
Q2 uses its intrinsic five-day policy even though the generic receipt's supplied
`window_days` argument is None for full Q2 controls; raw metrics retain each window.

Earlier 100k monthly input control at a6679c8, p50 seconds: evidence is carried
across commits, but a separate T8 follows EVERY read. This is NOT the cost of a
true root with only one final verification and must not be summed as that job.

| Path | Jan 2025 | Feb 2025 | Mar 2025 |
| --- | ---: | ---: | ---: |
| Q0 safety | 6.2152 | 6.3698 | 6.5754 |
| Q1 | 7.8170 | 6.8081 | 6.2484 |
| Q2 | 6.9396 | 7.0604 | 7.1431 |
| S3 narrow | 6.8472 | 6.8796 | 6.5855 |
| S4 | 6.5916 | 6.5100 | 7.1805 |
| S5 | 7.1209 | 6.5075 | 7.7676 |

The subsequent root-chain correction verifies only at the third month's tail,
without removing next-read E0 validation. New receipts explicitly declare
`ROOT_TAIL_ONLY` and record `final_verification_applied`; chain totals are summed
per actual repeat before median/p95. Old periodic-final receipts remain unchanged
and are not silently reinterpreted. Final CI must execute the corrected chain.

Host: Windows 10, Python 3.12.11, 8 logical CPUs, 34,271,772,672 bytes RAM,
uncapped. At 100k the candidate table is 232,980,480 bytes plus 40,026,112 index
bytes (273,006,592 total). Million complete storage/resources remain pending,
not inferred. Subsequent phase/SQLSTATE snapshot fixes do not change these read
SQL/control/timing paths; final-SHA CI must rerun and attest its own results.
Measured full receipts SHA256:

```text
a42-final-10k.json   a793b05922ecdc7300540b1f7e35556758da5c3efd6f15de84563ba96604c83c
a42-final-100k.json  54f756e8852ed3aef7bd741dffb9481fc2b0bcf6e5145fb8a24bb4ae7b148816
a42-final-million.json (failed setup) d68ca509a84197315db845ec0f2589844e36f49c4131f003cc96c77f61379921
a42-retry-million.json (failed setup) 587fd16d10a41fbae4cc587a40d71ac4d70f1518426cdb524b2b0afca063165a
```

LF laboratory source SHA256 (all raw receipts also store Git/checkout hashes):

```text
experiment  fd6cb4d4d296bb2ba8654d4b5436d537df6742b4295fa91a80c45b1f639aff2f
summary     5d85e44130528bc0b15f9598cf1ca4e1f5b77a625fff86f5744bf8b94586a668
evidence    ea786dfb13923e0638bcb9baf792220a7798407e8a20a40672ea28a99d020a6f
resources   38c628b3ada1235a8bd603957f990090b85de4d2fe50937961c10d6d122319da
```

### Earlier Exploratory Results

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
| T20 | PASS | Disconnect path and full-suite unknown-commit regressions passed |
| T21 | PASS | Wrong token; frozen takeover regressions retained |
| T22 | PASS | Warmup source mutation aborts original publication |
| T23 | OPEN | RR2 probe implemented; latest million reader run pending |
| T24 | PARTIAL | Real lock probe available; final matrix hold/reader comparison pending |
| T25 | PARTIAL | Small controls/shapes complete FETCH and EOF/close passed; million read gate pending |
| T26 | OPEN | 10k/100k passed; local million failed before timings; independent CI required |
| T27 | PARTIAL | Real caller/430-day bounds; corrected one-tail chain regressions pass, final scale pending |
| T28 | PARTIAL | Actual cursors in earlier receipt; latest-code scale plans pending |
| T29 | PASS | Frozen source/schema/config; default flag unchanged |
| T30 | PASS | Wrong marker/system ID refused before child CREATE |
| T31 | PASS | Real ten-table engine/quality/atomic-publication golden for S3_KEYS/S4/S5 |
| T32 | PASS | Production freeze and full frozen evidence regressions passed |
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
head full regression and measured tables. Local full baseline 2361 and final
related 124-item suite are separate executions, not a fake final-head full PASS.
UNPROVEN: strict all-writer event evidence,
production/cloud latency, controlled cold cache and cloud resource budgets.
Keep production off. Do not propose A4-3 on exploratory 10k results.
