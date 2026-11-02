# BIZ-PERF-02 Closeout

Status: PARTIAL, candidate under controlled validation.
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

W02 has one real business change: same-transaction five-row quality batching before
the unchanged sector check. The new batching test failed at `[1,1,1,1,1,1] != [5,1]`
before the change. Afterward 10 focused new/original tests passed. This is a
functional RED-to-GREEN proof, not a wall-time or capacity claim.

W03-W06 remain in progress until the measured candidate, fault/continuity tests
and final native CI have actual receipts. The three-round matrix and its complete
raw/golden results must determine whether to keep or withdraw the optimization.
Do not infer final PASS from this pre-measurement design/implementation commit.
Ten different real roots completed FIFO/dedup validation with all ten
SUCCESS/PUBLISHED in 398.76 seconds; original fault-matrix CI remains separate.
The local resource preflight observed a memory/disk lower floor, not a refusal
or an exclusive/capability-qualified capacity reservation. Do not claim RAM was
exhausted: formal capacity remains deferred for lack of an allocated qualified
runner and representative million-row fixture, not because a small test passed.
The first comparison cohort was stopped because the old archive lacked Git while
the new runtime had Git. Only its verified controller was stopped; its active
root child finished naturally. The incomplete controller and all child receipts
remain separate. The corrected protocol uses two clean detached local Git clones
with LF line endings; no timing conclusion is drawn from the asymmetric cohort.

| Item | Current disposition |
| --- | --- |
| A01 | PASS: merged master; no new branch |
| A02 | PARTIAL: measured hotspot and actual code/functional RED-GREEN; retention pending |
| A03 | NOT_RUN: registered three-round interleaved matrix pending |
| A04 | PARTIAL: focused IDs/preimage/quality goldens; whole-root pairs pending |
| A05 | PARTIAL: focused A-only visibility/rollback/prefix; full safety CI pending |
| A06 | PARTIAL: ten real roots passed; full fault-matrix CI pending |
| A07 | NOT_RUN: final-source engineering CI pending |
| A08 | PASS: explicit PERFORMANCE_OPEN; no million-row claim |
