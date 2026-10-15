# M17.1 Closeout

Status: IN PROGRESS. Baseline a3ee768, master. Batch 1 T01/T02 accepted at 30ed272 /
[CI 38669794915](https://github.com/sssssssssh/ssh_stock/actions/runs/38669794915),
including targeted PG17 and the complete backend/migration/Ruff/container/frontend/
browser pipeline. Batch 2 T03/T07 implemented, awaiting isolated PG acceptance.
P2 documents/audit remain pending. No business database write, migration or cleanup
was performed.

## Batch 1

The direct dirty gate now uses inclusive start/end intersection, deterministic
ordering, LIMIT 1 and explicit None checks. Reversed/missing dates and unknown
states fail closed. No schema change and no new migration; 0053 is unchanged.
The existing repair manager still propagates earliest source changes through
latest Raw. PAPER additionally verifies actual historical dependency lineage in
the same repeatable read-only snapshot, including calculation job bounds,
current identities, missing inputs, calendar completeness and dependency order.
No Raw sync, strategy algorithm, immutable payload/hash or financial formula changes.

Contract and operational remediation: [M17_1_dirty_range_contract.md](M17_1_dirty_range_contract.md).
Core tests: tests/integration/test_m17_1_dirty_dependencies.py and
tests/unit/test_m17_1_dirty_contract.py. Tests cover closed boundaries, historical
and future nonintersection, overlapping records/datasets, malformed dates/states,
new D with stale intermediate inputs, repairs, old hash preservation and a later
upstream repair that invalidates an earlier downstream calculation.

Local focused unit tests: 19 passed; full Ruff passed. The full CI passed after
the warmup scope supplement; the superseded unwrapped fixture candidate was
cancelled rather than accepted. Full CI evidence is linked above.
All PostgreSQL writes must be on CI disposable PG17, never the user's stock_db.

## Batch 2 Candidate

tests/integration/test_m17_1_paper_continuity.py adds 21 real PG transaction cases:
observation/proposal/approval errors, same-request replay, historical FAILED interval
with successful settlement, dirty rejection with unchanged financial counts and
all original record_json/hash pairs, prior-day drift review, pause/gap/recovery
through weekend plus holiday, concurrent workers, cancellation, lost response,
explicit retry, scheduler and append-only review, owner isolation and frozen
version rejection. Financial invariants are asserted against committed rows.

The existing capacity test now independently executes 1/30/250 days both without
dirty records and with a retained RESOLVED change whose actual dependencies were
rebuilt. It still uses <=400 SQL/day and <15 seconds/day, one manual buy, actual
source sessions and atomic Worker settlement. No budget/assertion was relaxed.
Synthetic calendar/source facts are fixtures, not market throughput claims or
proof of the numerical factor algorithm being rerun.

## Remaining Gates

- T01/T02: ACCEPTED, CI 38669794915.
- T03/T07: final PG gate for observation/proposal/approval/EOD/worker/scheduler/review continuity,
  holiday/pause/gap/retry/cancellation/owner and immutable financial evidence.
- Recheck real 1/30/250-day SQL/time and complete backend/frontend/migrations/
  containers/browser pipeline against final HEAD.
- T04 version policy, T05 capacity design and T06 reproducible dependency audit.
  Monitoring API/UI and major dependency upgrades may be explicitly DEFERRED;
  they must not be reported as implemented.
