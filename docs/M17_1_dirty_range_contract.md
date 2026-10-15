# M17.1 Dirty Range Contract

Baseline: a3ee768, master. This document describes the existing writes before the
M17.1 read-side correction; it does not redefine a Raw row as a Derived artifact.

## Dates And States

`services/dirty.py::record_dirty_range` takes min/max of changed Raw dates. Both
ends are inclusive, with natural dates between them; only open SSE/SZSE calendar
dates require market calculation. An interval is a source-change envelope, not a
claim that rolling or stateful effects stop at its end. Stock daily, adjustment,
daily basic, index, ST, suspension, limit and theme feeds create these records in
the Raw write transaction. Overlapping records are retained; there is no merge or
split manager. No dataset is assumed irrelevant to PAPER without dependency proof.

The string states come from dirty.py, not a database enum:
OPEN -> PROCESSING -> RESOLVED; failures become FAILED and increment retry_count;
cancellation reopens OPEN; stale processing becomes FAILED. OPEN/PROCESSING/FAILED
block a target inside the closed interval. RESOLVED alone is not a dirty gate, but
is still change evidence for the separate dependency gate. Unknown states and
reversed/missing dates fail closed as SOURCE_DIRTY_RANGE_INVALID. Current NOT NULL
columns reject null writes; the schema has no date-order CHECK. Invalid future
records also fail closed: their true influence is unknown.

## Propagation Already Implemented

The dirty-repair API and CatchUpJob select the earliest changed start and
latest_raw_trade_date as the recalculation range. run_recalculation recomputes
trade status, factors, market, sectors and trend from its warmup start through the
end; themes/opportunities cover the requested slice. Only successful cross-table
quality and completion resolve the records. Cancellation/failure never certifies
repair. The original dirty_end_date is NOT enlarged. Manual range calculations can
repair a target while leaving the old record FAILED; the record must not be deleted
to permit a verified, unaffected target.

Factors read rolling history (430 natural days), trend reads factor/market/sector
history and previous states. Thus a recent timestamp on D alone cannot prove that
the earlier inputs consumed by that calculation were repaired. Resolved_at alone
is not provenance. Existing JobRun type/status/date coverage plus real calc_run_id,
current version/config and calculation timestamps are the available proof.

## M17.1 Read-Side Proof

All checks run inside capture's existing REPEATABLE READ, READ ONLY transaction.
The direct gate selects the first intersecting nonterminal interval ordered by
start/id with LIMIT 1 and explicit `is not None`. It never loads dirty JSON.

The dependency gate starts at the earliest recorded change <= D, including
RESOLVED. It validates actual upstream factor/state/trade-status rows for Raw
instruments and the historical market/sector rows, plus D opportunities. Missing
upstream rows, wrong identities, missing/failed jobs, invalid job date scopes or
jobs/rows predating a relevant change fail as SOURCE_DERIVED_STALE. A historical
change matters only to dates >= its own start; a later correction does not demand
recalculation of earlier unaffected dates. Known open dates without Raw are gaps.
Job scopes are grouped and bounded before metadata projection; no per-day/per-code
SQL loop and no historical record_json loading. Normal no-dirty operation takes a
constant fast path. Job start, calculation time, job finish, source-update time and
the capture cutoff are all checked; target date or validated ISO range must cover
the actual rows associated with a job. A newly calculated D cannot conceal an old
intermediate input. Existing `analysis_warmup_start` explicitly extends a range
job's foundation coverage before its requested start; it must be a valid ISO date
not later than that start. D opportunity still requires the existing requested
target/range validation. This preserves legitimate warmup work without inventing
coverage from timestamps. A newly calculated D cannot conceal an old
intermediate factor/state/market input. Calculations in the same job must follow
upstream/downstream timestamp order. Across jobs, the
upstream job must finish before its consumer starts. Later repair of a historical
factor therefore invalidates an earlier downstream result even if both postdate
the original dirty event. Missing calendar dates are unknown, not closed holidays.

This is a conservative verification interface, not another repair queue. Existing
Raw sync, repair scheduling and financial transactions are unchanged. It may ask
for a full repair when historical lineage cannot be proved. It never resolves a
record, recalculates data, changes a frozen hash or writes a financial artifact.

## Schema And Operations

No new migration. 0050-0053 remain untouched. No production anomaly count was
queried and no production migration was authorized. Therefore adding a date-order
CHECK without an approved historical-data remediation plan is deliberately deferred.
A future incremental migration must inventory invalid rows read-only, repair them
under explicit authorization, add/validate a new CHECK online, and test rollback
in a disposable PG17 database. Do not edit 0053 or delete invalid records silently.

On SOURCE_DIRTY_RANGE, repair the intersecting source interval. On
SOURCE_DERIVED_STALE, run the existing full-range repair from the earliest relevant
change through latest Raw, verify successful current-version jobs and retry.
SOURCE_DIRTY_RANGE_INVALID requires operator investigation; do not clear history.
JobRun.started_at is a conservative enqueue-time lower bound in the current model;
an old queued job cannot prove it started reading after a later input repair. Queue
a new repair after the upstream work finishes; never manually adjust timestamps.
Missing historical calculation Jobs, including evidence removed by generic
retention, cannot be silently treated as proof; preserve such provenance or arrange
an explicitly verified full repair. Long-term evidence retention is a P2 policy
concern, not permission to bypass the gate.
Already sealed PAPER finance remains immutable; source correction only requests
review. Rollback is a code/config rollback, never a ledger rewrite or hard downgrade.
