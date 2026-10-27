# BIZ-PERF-01 Closeout

Status: **PERFORMANCE_OPEN**. Cloud: **REAL_CLOUD_RECALC_NOT_AUTHORIZED**.

Implemented actual business changes in recalculation, factor reads/calculation and
read-only completeness preflight. All switches default false. No schema, candidate
batch size, publication budget, formula/version or production data changes.

Old unprofiled 4-stock full business smoke: 18.078 s, 5684 SELECT, SUCCESS/PUBLISHED.
First opt-in smoke: 14.515 s, 1950 SELECT, SUCCESS/PUBLISHED. Ten normalized financial
table digests matched. These are SINGLE SMALL exploratory runs, not a controlled
median or the million-row acceptance; do not advertise their ratio as target closure.
The separately profiled baseline is diagnostic and not a fair timing denominator.

Final-source small matrix (8 securities, old/new each 3 runs for 1/3/12 months):
24.750 -> 16.625 s (32.8%), 33.032 -> 22.688 s (31.3%),
75.485 -> 59.063 s (21.8%). All 18 SUCCESS/PUBLISHED, all 9 complete financial
digest/snapshot/identity pairs equal, independent RR readers saw no B, source
mismatches and captured SQL errors both zero. Scale is only 5320..7224 Raw daily
rows; even this small 12-month case falls short of 30%, so acceptance remains OPEN.

Verified remaining 12-month costs (stage medians, inclusive/overlapping): candidate
lookup 12.065 s, candidate store 5.841 s, cross-table quality 14.812 s, opportunity
compute 7.469 s; input verification itself costs 4.811 s. Factor compute fell from
19.689 to 4.797 s, Raw preflight from 5.406 to 1.563 s. These are not exclusive
components that can be summed to overall time. The next bounded proposal is to
measure per-day derived-quality candidate write amplification, then validate batching
its equivalent rows without changing error evidence/first base_row/ID/validation
ordering. This proposal is NOT implemented or claimed to have proven a speedup.
The recorded candidate plan is an untimed post-publication replay, not a claim to
have captured the actual timed first-write plan. No index was added on that basis.

Preliminary regressions: 10 Raw cases compare all completeness fields and SQL counts;
input-window dtype/eviction/source-drift/memory/cursor tests; CPU golden covers nullable
status, date boundaries, exact RPS/fields/dtypes and pathological drawdown values.
The final backend regression selection passed 79 tests, including the original
RawCompleteness cases. Full default pytest on Windows stops at 10 Linux `resource`
module collection errors. An earlier continue-on-collection-errors diagnostic ran
to completion: 3712 passed, 317 failed, 300 errors; it exposed 7 genuine legacy
call-signature regressions, repaired without editing the old tests. Remaining
historical source-pin/platform failures are not waived or represented as passing.

## Checklist Disposition

- AT01-12: source baseline/window/read safeguards implemented; scale, real transport
  accounting and exhaustive B/root/cancellation matrix still require final evidence.
- AT13-23: batched preflight and CPU exact-value regressions implemented; multi-month
  whole-chain golden at required scale remains open.
- AT24-36: candidate/publication/queue protocol retained; no new index/DDL. Actual
  candidate plans and full-scale fault/ownership tests are not inferred from smoke.
- AT37-43: million-row 1/3/12-month >=3-per-version matrix and >=30% median target OPEN.
- AT44: topology/rollback plan only; no deployment.
- AT45-48: cleanup tests, full suite/CI and exact-source receipts must be reported
  separately. Windows Linux-only collection errors and deferred G1 guards are not waived.
- AT49: actual backend implementation present.
- AT50: cloud not authorized, no production-fix claim.

## Review Boundaries

User explicitly deferred G1 freeze-contract adaptation. No old guard, manifest,
negative test or financial/publication assertion was weakened to accept backend edits.
Cloud reads/jobs, DDL/index, deployment, Worker stop/retry and budget changes need
separate explicit authorization. Performance insufficiency is not an authorization
block: it stays PERFORMANCE_OPEN with switches off.

## Individual Acceptance

PASS below is scoped to the stated component/synthetic test, not a release waiver.
PARTIAL/OPEN entries remain required work; no automatic cloud/deployment approval.

| ID | Disposition | Evidence Or Remaining Work |
| --- | --- | --- |
| AT01 | PARTIAL | Frozen archive and per-file/runtime source hashes; final CI still required. |
| AT02 | PASS | Actual 1/3/12-month warmup/monthly 430-day windows in each receipt. |
| AT03 | PARTIAL | SQL/FETCH/rows/estimated bytes/stages/RSS; pure WAN/server CPU unobservable here. |
| AT04 | PARTIAL | Actual PG17 old reader, but current completed matrix is small scale. |
| AT05 | PARTIAL | Actual tail-only reads and repeated-row reduction; capacity-scale replay open. |
| AT06 | PASS | Root/config/version/physical connection/read-transaction checks; no global cache. |
| AT07 | PASS | Unchanged 430/250 boundaries; exact engine golden and monthly service tests. |
| AT08 | PARTIAL | Closed dates, empty/invalid inputs and listing boundaries tested; scale matrix open. |
| AT09 | PARTIAL | FETCH cleanup, compact-block bounds and memory failure tested; large RSS open. |
| AT10 | PASS | Existing FETCH checkpoints/budgets and observable wall time retained. |
| AT11 | PARTIAL | B overwrite/tombstone/root drift tests; multi-child catchup remains unaccepted. |
| AT12 | PASS | AB read remains false; combined experimental flags reject unsupported mixing. |
| AT13 | PASS | Read-only monthly facts; actual preflight and total SQL counts recorded. |
| AT14 | PASS | Ten actual PG17 completeness variants match every result field. |
| AT15 | PASS | Existing Worker/service calendar guards retained before candidate/preflight. |
| AT16 | PASS | Existing output/warmup/month chunk logic unchanged. |
| AT17 | PASS | Exact numeric/eligibility/RPS/NULL/dtype engine golden and table digests. |
| AT18 | PASS | SQL NULL masks preserve all-NULL versus NaN and nullable bool after eviction. |
| AT19 | PASS | Inclusive listing/delisting and explicit nullable source active override tests. |
| AT20 | OPEN | Small exact frames pass; million-row whole-window dtype/size proof pending. |
| AT21 | PASS | Actual old cProfile identifies Series drawdown/row-apply; exact alternatives tested. |
| AT22 | PASS | Whole-market calculation remains one whole-window frame, never FETCH sub-engines. |
| AT23 | OPEN | Required-scale multi-month and dirty_repair published golden pending. |
| AT24 | PARTIAL | Real lookup/store wall time and counts, small synthetic data only. |
| AT25 | PARTIAL | Scrubbed untimed post-publication lookup plan; not the timed first-write plan. |
| AT26 | PARTIAL | Original write/preimage/ID code retained; large mixed-A/B fault matrix open. |
| AT27 | PASS | Independent RR reader sees no committed B; real Worker failed/cancelled roots abort. |
| AT28 | PASS | Real cross-table quality remains mandatory; no synthetic derived certificate. |
| AT29 | PASS | No batch or budget increase; final input verification charged to original 300s. |
| AT30 | PARTIAL | Existing unknown-commit path untouched; no new capacity-scale fault injection. |
| AT31 | PARTIAL | FETCH/CPU cancellation, memory and source-error cleanup; full owner-loss matrix open. |
| AT32 | PARTIAL | No FIFO/claim changes; old source guards deferred, final Linux suite required. |
| AT33 | PASS | No retry/replay of old FAILED tasks or reuse across runs/restarts. |
| AT34 | PARTIAL | Published-reader protocol unchanged; all Research/PAPER CI not green. |
| AT35 | PASS | No schema/index/migration change or cloud DDL. |
| AT36 | PARTIAL | Actual ledger row counts/root source checks; required large provenance matrix open. |
| AT37 | PARTIAL | Interleaved >=3 old/new small runs per case; required scale not met. |
| AT38 | PARTIAL | Actual small 1/3/12-month stages; not capacity acceptance. |
| AT39 | OPEN | Completed full-chain matrix is not >1M Raw rows. |
| AT40 | OPEN | No qualifying million-row >=30% complete-job median proof. |
| AT41 | PARTIAL | Small real SUCCESS/PUBLISHED; no claim for required capacity/cloud workload. |
| AT42 | PARTIAL | All services/real quality run; richer nonempty theme/signal capacity cases pending. |
| AT43 | PARTIAL | Delivered rows/payload estimates/SQL/FETCH/RSS recorded; actual WAN bytes not measured. |
| AT44 | PASS | Topology/access/rollback plan only; no Worker migration/deployment. |
| AT45 | PARTIAL | Source/memory/cancel faults clean up in real Worker; full large-fault matrix open. |
| AT46 | PASS | Windows/loopback/fixture limitations and failed runs disclosed separately. |
| AT47 | OPEN | Final full Linux regression/CI and deferred freeze-contract reconciliation required. |
| AT48 | PARTIAL | Source/harness/data/raw-receipt digests; exact-SHA accepted CI not obtained. |
| AT49 | PASS | Actual recalculation/reader/factor/preflight business backend optimizations. |
| AT50 | PASS | PERFORMANCE_OPEN; REAL_CLOUD_RECALC_NOT_AUTHORIZED; switches remain false. |

Raw/source-sync facts are synthetic fixture inputs. Derived calculators, cross-table
quality and publication are real; this does not claim Provider/Tushare ingestion or
cloud execution. Original exploratory/interrupted measurements are retained, not
mixed into the final-source matrix. Compressed JSON observations are formal task
evidence, not DB dumps, application data, installers or temporary build archives.
