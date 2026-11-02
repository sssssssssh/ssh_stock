# BIZ-PERF-02 Design And Registered Comparison

Baseline: merged master `3940d9b905e5234368f8a7474ae2ce6de73b0cb3`.
PR #1 merged at 2026-11-02T01:14:24Z and contains `8d6d3222`.
The taskbook's older Draft/Open observation is superseded by verified GitHub state.
Only master is used. Historical manifests/tests/receipts are not rewritten.

Measured outcome: RETENTION_FAILED / BUSINESS_CHANGE_WITHDRAWN. All nine pairs
matched, but the one-month whole-root median regressed 5.34%, exceeding the
registered 5% ceiling below. Current daily_quality.py is restored to baseline.
The description below applies only to preserved candidate 6c4096e5de77368c67ff1c2cff7ddd3285a8e56e.

## W00 And W01

The single baseline receipt is [baseline.json](biz_perf_02/baseline.json).
PG17.6 is a newly initialized loopback-only instance, marked with a new UUID;
its physical system identifier is independently read from its own control file.
The existing v14 verifier checks both identities before UUID test DB creation,
migration or deletion. No business dotenv, cloud, Provider, production service,
old test database or production DDL is accessed.

Original full-root 4-security, 12-month diagnostic: SUCCESS/PUBLISHED, 3,612 Raw
daily rows, 94.203 seconds overall. Cross-table quality took 16.281 seconds,
including 1,566 singleton candidate upserts taking 12.729 seconds. Each upsert
repeats candidate lookup, source registration, ID preparation and candidate store.
This is a reproducible small-workload round-trip bottleneck, not proof about WAN
or million-row capacity. Inclusive stages overlap and are never summed.

Actual first-lookup plans for seven tables were captured during that run via
auto_explain notices, with parameter logging disabled and condition/output text
removed from exported plans. Two earlier observer attempts failed closed on a
missing plan; FAILED/ABORTED receipts remain retained. The cause was delayed
extended-protocol notice delivery on the next Sync; the observer now keeps its
capture target until control SQL is drained. No failed attempt is replaced by
the successful observation or used as a timing denominator.

## W02 Rejected Minimal Candidate

Only `quality/daily_quality.py` changed business behavior in that candidate. The five basic quality
rows have the same date/job, static distinct natural keys and no intervening SQL.
A function-local list collects them in original order only inside an existing
PublicationWorkspace. Its finally flush occurs BEFORE the original sector query;
a later invalid threshold still flushes the earlier valid prefix before raising.
Sector checks and the sixth row stay in their original order. Standalone callers
keep six original writes. No persistent/global/Session buffer or reuse is added.

The original upsert/candidate machinery still resolves current typed B/A rows,
allocates serial IDs in order, preserves first base_row, performs conflict updates,
checks source/ownership and writes bounded batches. The unchanged global maximum
is 500; this local group is at most five. No lookup/store SQL, schema, index,
financial formula, NULL/dtype rule, 250-day warmup, 430-day window, timeout,
300-second publication budget, state machine or frozen source contract is changed.
All original optimization flags remain false.

## Registered Symmetric Small Comparison

Before measuring the candidate, fix: 4 securities; 1/3/12 requested months;
three pairs each; AB, BA, AB order per month; independent fresh process and UUID
database per sample; identical deterministic data, audit seed, PG instance,
configuration, instrumentation and resource settings. No discarded outliers,
retries, additional warmup or best-of selection. Keep every exit and failed receipt.
Preflight, compute, quality, source validation and atomic publication all run.

Each implementation's backend/config/migration canonical bytes must exactly match
its claimed full Git SHA. Driver checkout and actual implementation SHA are
separate facts. Both implementations run in fresh clean detached local shared
Git clones with autocrlf=false, so Git identity checks and LF bytes are symmetric.
The first archive-versus-live cohort was stopped for this identified protocol
asymmetry before judging its timings; its completed samples and unfinished
controller receipt remain retained, not filtered as performance outliers.
Dirty or docs-only identities must not
be relabeled as exact-SHA performance acceptance. Plans describe actual timed
lookup calls, not untimed replay. Observer control SQL/time is counted separately
and included in overall/lookup wall time on both versions; it is not free.

Retain only if all nine pairs have identical input snapshots, normalized complete
financial table digests (NULL/IDs/other sources retained), configuration/financial
identity and SUCCESS/PUBLISHED outcomes; the cross-table stage median improves
by at least 15% in each window and at least two of three pairs improve; no overall
window median regresses by more than 5%, and the 12-month overall median improves.
These are conservative small-diagnostic retention rules, not a new release gate
or a claim of statistical significance. Failure means withdraw the business change.

Formal acceptance remains >1,000,000 Raw daily rows, full universe/windows,
1/3/12 months, >=3 interleaved runs per implementation, unchanged correctness and
whole-root median improvement >=30%. The shared Windows host/legacy Linux VM
are not an allocated, capability-qualified independent capacity runner. No new
expensive Actions dispatch is authorized: RESOURCE_DEFERRED / PERFORMANCE_OPEN.

## Correctness And Safety

New PG17 tests first reproduce six singleton writes, then require `[5,1]`, ordered
IDs, root identity, first preimages across repeat calls, A-only readers, rollback,
valid-prefix evidence and unchanged sector order. Original financial, dtype,
source drift, tombstone, cancellation, transport, unknown-commit, publication and
Worker safety tests remain untouched and must run in full native CI. Ten different
real roots separately exercise FIFO, parameter deduplication and PUBLISHED results.
Synthetic test roots/faults do not authorize production execution or recovery.

After withdrawal, the six new candidate-specific cases explicitly load the pinned
rejected candidate and record that subject/SHA in JUnit. They do not route original
tests or claim current batching is enabled. Two additional live quality cases
cover the restored implementation. The registered retention rule is unchanged;
its refusal of the observed 5.34% regression has an explicit unit regression.

## R1 Evidence Review

Ordinary engineering CI on 8f4e6071b74ae90dd95eb56a71ade1ed3dcb1e6a has now
been verified from jobs/steps, logs and hashed artifacts, not inferred from a
workflow green light. See [R1 closeout](BIZ_PERF_02_closeout.md#r1-evidence-closure)
and [structured summary](biz_perf_02/ci_8f4e607_r1.json). This confirms engineering
checks only on that SHA; A05/A06 remain PARTIAL for the documented subject and
per-root provenance limits. Neither this documentation diff nor any future SHA
inherits that CI result. The registered rules, observations, withdrawal and
PERFORMANCE_OPEN / RESOURCE_DEFERRED disposition above are unchanged.
