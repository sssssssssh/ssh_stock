# BIZ-POLICY-01 Delivery and Acceptance

baseline_sha: 2779a2a7a7120c86f67b4991bce196c652b5ebb0
field_cause: NOT_CONFIRMED_NO_BUSINESS_DB_ACCESS
status_at_registration: SOURCE_FIXED_PENDING_EXACT_SHA_PG17_CI
business_code_changed: YES, three policy/Worker/Job repository modules only
business_database_changes / DDL / TuShare_calls / service_restarts: 0 / 0 / 0 / 0
optimization_defaults: unchanged, all three false; AB_MERGE_READ_ENABLED unchanged
G1: SOURCE_PARTIAL_ENGINEERING_BLOCKED / PHYSICAL_NOT_RUN_NOT_AUTHORIZED
performance: PERFORMANCE_OPEN, no new capacity or G1/A4 measurement

## Frozen Contract Conflict Deferred by User

A42366 pins the previous backend and exact changed-file set. Its original
test_AT_W09_historical_manifests_and_all_original_tests_keep_their_blobs also
allows only tests/unit/test_a42366_* additions since its baseline. This task
requires three backend edits and new business-policy tests. Leaving those old
current-tree rules untouched necessarily rejects this new source; ordinary CI
cannot qualify it merely because helper tests pass.

The user explicitly chose to finish the business fix WITHOUT adapting frozen
contracts. No new whitelist, route or old assertion adaptation is applied. All
historical manifests and old tests remain byte-identical. Submission/push is
requested, but frozen-source CI failures must remain visible and separate from
business behavior tests. AT14 cannot be accepted under that conflict; do not
label the entire task or its same-SHA ordinary CI green.

## Implementation

calculation_policy.calculation_source_identity compares actual business content,
not Git provenance. Freeze/verify/resident Worker and legacy v1 validation use it;
schema, job/root/range and strict boolean flags remain mandatory. Old source and
commit_status are preserved; latest bounded diagnostics live in source_diagnostics.
Source/flag rejection is sticky and keeps the public error code. Missing or
unreadable source and malformed old identity still refuse, without echoing inputs.

job_worker preserves enum failure diagnostics before a Policy can be installed.
job_run adds those diagnostics and readable reason to terminal failures within
the original owner/token CAS, and JSONB-merges even the pre-freeze error path.
No financial formula/version, Raw chain, publication algorithm or G1 adapter changes.

## W00 RED and Local Records

Five original behavior failures were reproduced before production edits:
Git-only HEAD, worktree, resident freeze, persisted freeze and an actual temporary
Git repo containing unrelated docs/scripts/tests and an untracked progress file.
Raw JUnit .codex_tmp/biz-policy-red.xml SHA256
db2f18f66330d158d3f8441e6b80c80fce0f7c92c40e8243b15caf2689ce88ef.
The later source-only unit report has 20 passed; the broader business-unit run
has 62 passed (including input scalar/Decimal/null, CPU and memory regressions).
Both initial combined attempts
also retain a Windows WinError 1314 failure in the ORIGINAL symlink test; it is
not deleted or skipped. Linux exact-SHA CI must run that original node.
Full Windows pytest also retains ten original Linux-only collection errors
(fcntl/resource), report .codex_tmp/biz-policy-full-windows.xml. No test source
skip/xfail was added; these failures are not a passing full-suite claim.

## AT01 through AT17

| AT | Executable evidence / boundary |
|---|---|
| 01 | Baseline above; scan stays backend/**/*.py + config/**/*.yaml; old CI 40621359684 had 5088/0/0, 89.37%; not final evidence |
| 02 | test_business_policy_identity Git-only nodes; five baseline RED, then GREEN |
| 03 | test_business_policy_worker_pg17 resident Worker HEAD case; actual isolated PG17, pending final CI |
| 04 | Same Worker dirty case and actual Git temp-repo unit; pending PG17 final CI |
| 05 | Actual backend file change: FAILED/ABORTED/all published tables unchanged |
| 06 | Actual config file change: same negative assertions |
| 07 | Each of three flags: real Worker rejection plus original policy PG17 tests retained |
| 08 | Legacy hash/schema/range/null damage: no re-freeze, old evidence retained, no auto retry |
| 09 | Real run_worker entry/poll/claim/dispatch; daily/recalculate/catchup; real calculators and multiple children, root cumulative metrics |
| 10 | Original test_data_queue, test_data_queue_reliability, test_data_publication disconnect/cancel/owner-token nodes retained; final full CI required |
| 11 | New A snapshot negative tests plus original publication A/B, unknown-commit and rollback nodes retained |
| 12 | Enum reason/hash-only diagnostics; source sentinel unit; PG17 pre-freeze concurrent JSONB heartbeat merge |
| 13 | Original business input records, memory, financial Golden, cold-start and PG17 performance regressions unchanged |
| 14 | Final same-SHA main/A4-1/A4-2/Publication run URLs and raw JUnit digests must be verified after push; baseline is not a substitute |
| 15 | No environment/config/DDL/TuShare/cloud operations or default flag changes |
| 16 | BIZ_POLICY_01_runbook.md explicit operator gates; field rerun NOT_RUN, needs user confirmation |
| 17 | A42366 capability matrix and physical denials retained; no G1 qualification |

W00-W03 source/negative checks are implemented. W04 is not accepted until real
Linux/PG17 results are reviewed. W05 is an operator handoff, NOT a field retry.
W06 is evidence planning below, not a performance result. W07 remains separate.
Do not label BUSINESS_POLICY_CONFIRMED without the authorized new business Job.

## W06 Follow-up Performance Evidence

No field timing or new benchmark was collected. The 80-minute screenshot is an
end-to-end symptom, not a measured per-stage allocation. Collect existing bounded
calculation_execution.stages/reads/driver_reads/sql from an authorized NEW Job.

| Candidate hotspot | Existing metric / next diagnostic question |
|---|---|
| Raw preflight | recalculation.raw_prerequisites; how much original per-day versus opt-in range checking? |
| Warmup status | trade-status compute/read and candidate operation records; separate read/compute/lookup/store |
| Input verification | factors.input_verify; include repeated source scans and locking cost |
| Factor computation | factors.compute; distinguish complete monthly cross-section from transport batches |
| Candidate persistence | Existing candidate phase records and SQL aggregate; separate lookup, assembly and durable store |

Metrics nest; do not sum stage + contained SQL/FETCH durations. driver_reads
includes priming and EOF, reads describes delivered partitions. No 1,043,000-row
input SQL diagnostic is an 18-run full-chain capacity result. No claim of speedup.

## Final Evidence Convention

Final SHA, four ordinary run IDs, counts, coverage and artifact SHA256 are delivered
in the final response and immutable Actions artifacts. Do not rewrite this exact
commit merely to make its manifest self-reference its own final hash. All local
platform failures remain recorded alongside independent Linux results.
