# BIZ-PERF-02 Closeout

Status: PARTIAL / BUSINESS_CHANGE_WITHDRAWN. Retention: FAILED.
Performance: PERFORMANCE_OPEN. Capacity: RESOURCE_DEFERRED.
Cloud: REAL_CLOUD_RECALC_NOT_AUTHORIZED.

This new record does not revise earlier BIZ-PERF-01/G1/Worker acceptance records.
Baseline and registered retention rules: [design](BIZ_PERF_02_design.md).
Operations and rollback: [runbook](BIZ_PERF_02_runbook.md).

W00 verified merged PR #1, synchronized clean master at 3940d9b, PG17.6 physical
marker/system ID, matching Alembic head and false flags. Initial provisioning
found an incomplete older binary directory; no server or database was created
there. A complete existing binary installation initialized a fresh owned cluster.
No installer, business environment, old database or cloud endpoint was used.

W01 captured real SUCCESS/PUBLISHED 1/12-month roots and actual seven-table timed
plans. Twelve-month cross-table quality staged 1,566 singleton rows in 1,566 calls;
its 16.281 seconds includes 12.729 seconds of candidate upserts. The same run
retained two SQLSTATE 55P03 observations; overall success does not erase those
bounded observation failures. The two failed plan-capture attempts remain RED.

W02 implemented one candidate: same-transaction five-row quality batching before
the unchanged sector check. It is preserved in commits c0f0fca43f2fe4f66fa36c9e63dc465f36424b8b
and 6c4096e5de77368c67ff1c2cff7ddd3285a8e56e, without rewriting either commit.
The new batching test failed at `[1,1,1,1,1,1] != [5,1]` before the change;
afterward 10 focused new/original tests passed. This functional RED-to-GREEN proof
did not predict overall benefit. The retention failure below required withdrawal.
Current daily_quality.py is byte-equivalent in Git to baseline 3940d9b; there is
no retained business optimization and no financial/Raw/publishing/schema change.

Ten different real roots completed FIFO/dedup validation with all ten
SUCCESS/PUBLISHED in 398.76 seconds; original fault-matrix CI remains separate.
That local continuity receipt was produced before the candidate commit, carries
DIRTY source provenance, and is not exact-final-SHA performance acceptance.
The local resource preflight observed a memory/disk lower floor, not a refusal
or an exclusive/capability-qualified capacity reservation. Do not claim RAM was
exhausted: formal capacity remains deferred for lack of an allocated qualified
runner and representative million-row fixture, not because a small test passed.
The first comparison cohort was stopped because the old archive lacked Git while
the new runtime had Git. Only its verified controller was stopped; its active
root child finished naturally. The incomplete controller and all child receipts
remain separate. The corrected protocol uses two clean detached local Git clones
with LF line endings; no timing conclusion is drawn from the asymmetric cohort.

## Controlled Comparison And Withdrawal

The corrected cohort ran baseline 3940d9b905e5234368f8a7474ae2ce6de73b0cb3
against candidate 6c4096e5de77368c67ff1c2cff7ddd3285a8e56e. Both clean detached
Git clones had LF bytes and independently verified implementation identity.
All four optimization flags were false. Three AB/BA/AB pairs per window produced
18 zero-exit SUCCESS/PUBLISHED children and nine matching input snapshots,
complete financial table digests, identities, windows and publication counts.
Only root UUID/audit timestamps are normalized; NULL, serial IDs and other source
identity remain in the comparison. This is a four-security synthetic diagnostic,
not a representative universe or million-row test.

Times below are whole-root seconds; P95 is linear inclusive, with only three
samples per implementation/window. No statistical significance is claimed.

| Months | Old samples | New samples | Old/new median | Old/new P95 | Median improvement |
| --- | --- | --- | --- | --- | --- |
| 1 | 53.547, 63.094, 57.343 | 60.422, 59.750, 60.406 | 57.343 / 60.406 | 62.5189 / 60.4204 | -5.34% |
| 3 | 65.031, 66.906, 66.969 | 64.250, 59.437, 60.812 | 66.906 / 60.812 | 66.9627 / 63.9062 | +9.11% |
| 12 | 141.204, 128.640, 136.265 | 117.406, 126.421, 122.282 | 136.265 / 122.282 | 140.7101 / 126.0071 | +10.26% |

Quality-stage medians improved 42.34%, 45.92% and 42.17%; respectively two, three
and three pairs improved. Nevertheless the one-month whole-root median regression
of 5.34% exceeds the registered 5% ceiling. Overall retain_candidate=false.
The candidate was withdrawn, not retried with more rounds, filtered or admitted
by raising the ceiling. The controller was observed as nonzero by the PowerShell
wrapper (exit 1); this does not replace any of its 18 recorded child exit codes.

Evidence: [matrix](biz_perf_02/matrix.json), [raw index](biz_perf_02/raw_index.json),
[local test receipts](biz_perf_02/local_tests.json),
[original local log hashes](biz_perf_02/local_log_index.json). Lossless gzip observations
include all corrected samples, original failed diagnostics and asymmetric samples;
compressed/uncompressed hashes and original local log/XML hashes are recorded.
The original XML/logs remain in the ignored owned lab, without publishing paths,
SQL parameters or credentials. Timed plans are actual first lookup plans, not
publication replay. Successful driver SQL time and inclusive stage wall time are
reported separately; failed statement exclusive/server CPU time is unavailable,
not filled with zero. Inclusive overlapping stages must not be summed.

## Regression And Final CI

After withdrawal, 20 focused tests passed: six new explicitly pinned rejected-
candidate cases, two live restored-quality cases, nine observer/retention cases
and three original quality cases. The six cases record their rejected subject,
full candidate SHA and source hash; they do not re-route original tests or prove
current batching is active. Original safety assertions remain unchanged.
Earlier focused receipts include 10 and 17 passing cases. Ten real root receipts
remain separate from the current implementation's full fault matrix.

Unfiltered local Windows pytest failed collection with 10 errors because native
fcntl is unavailable. It is not a passing or skipped full suite. Ruff passed;
the final exact-SHA ordinary Linux CI must supply unfiltered pytest/coverage,
fault matrix, PG17 migration, frontend and Compose checks. Its outcome and links
will be attached to the final commit, rather than relabeling earlier CI results.
No high-cost workflow dispatch, business cloud access, deployment, Worker or
Scheduler restart was performed.

| Item | Current disposition |
| --- | --- |
| A01 | PASS: merged master; no new branch |
| A02 | WITHDRAWN: real candidate/RED-GREEN preserved; no optimization retained |
| A03 | DATA_COMPLETE / RETENTION_FAILED: all 18 samples kept |
| A04 | PASS_SMALL_SCOPE: nine whole-root golden pairs equal |
| A05 | PARTIAL: focused A-only visibility/rollback/prefix; full safety CI pending |
| A06 | PARTIAL: ten real roots passed; full fault-matrix CI pending |
| A07 | PENDING: final-source native engineering CI; Windows collection failed |
| A08 | PASS: explicit PERFORMANCE_OPEN; no million-row claim |

Formal W04 capacity remains NOT_RUN / RESOURCE_DEFERRED. There is no allocated
independent qualified runner and representative >1,000,000-row fixture. The
resource-floor observation is not capacity qualification. The >=30% formal
whole-root acceptance is not met. Ordinary engineering CI cannot close that gap.
Business withdrawal is complete; combined tooling rollback is documented in the
runbook. Stop here for review, without automatically trying another hotspot or
starting the next phase.
