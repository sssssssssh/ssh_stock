# M17.1 Closeout

Status: IN PROGRESS. Baseline a3ee768, master. Batch 1 T01/T02 implemented; isolated
PG17 acceptance pending. Batch 2 T03/T07 continuity exercise and P2 documents/audit
remain pending. No business database write, migration or cleanup was performed.

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

Local unit/Ruff results and CI evidence will be recorded before acceptance.
All PostgreSQL writes must be on CI disposable PG17, never the user's stock_db.

## Remaining Gates

- T01/T02: isolated PG17 regressions and full CI.
- T03/T07: observation/proposal/approval/EOD/worker/scheduler/review continuity,
  holiday/pause/gap/retry/cancellation/owner and immutable financial evidence.
- Recheck real 1/30/250-day SQL/time and complete backend/frontend/migrations/
  containers/browser pipeline against final HEAD.
- T04 version policy, T05 capacity design and T06 reproducible dependency audit.
  Monitoring API/UI and major dependency upgrades may be explicitly DEFERRED;
  they must not be reported as implemented.
