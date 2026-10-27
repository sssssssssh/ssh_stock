# BIZ-PERF-01 Design

Status: PERFORMANCE_OPEN. Cloud: REAL_CLOUD_RECALC_NOT_AUTHORIZED.
Baseline: `1e510532bd140110e29b10b6e4eed30fbd573159`.

## Execution And Commits

Calendar guard precedes the workspace in Worker, and precedes preflight in the service.
The original 250-open-day warmup determines analysis_start. TradeStatus stages B and commits.
Each calendar-month factor chunk still reads [chunk_start - 430 days, chunk_end],
computes the whole-market input, stages factor B and commits. Market, Sector, Theme,
Trend and Opportunity follow. Cross-table quality precedes root SUCCESS. Only the
existing root terminal transaction verifies preimages, applies patches and marks
PUBLISHED/SUCCESS. Candidate checkpoints are NOT publication.

## Rolling Inputs

Opt-in `FACTOR_INPUT_REUSE_ENABLED`, default false. Root-owned FactorInputWindow
uses the existing physical connection and temp views. Each FETCH is encoded into
compact float/category column blocks with an independent SQL-NULL mask; no full
list of Python row mappings is retained. It is NOT a concatenation of independently
inferred DataFrames. Each new month
evicts dates before that month's exact lookback and reads only the new date tail.
Whole-column inference from reconstructed raw scalars preserves all-NULL versus
all-NaN windows and nullable-bool inference, including after eviction.
StockBasic is reused only inside the same guarded root; no global/cross-job cache.

Transaction-scoped SHARE locks stabilize all five public input tables and B patches
while source evidence and new rows are assembled. Per-date canonical full-row SHA256
fingerprints cover public inputs, including absent dates; the full current-root
trade-status patch digest covers tombstones and malformed redundant dates. Every
reuse checks prior evidence; publication rechecks under locks before touching A.
Source drift aborts, not fallback/retry. These scans are real overhead and MUST be
included in the measurements. This is a checked read-set, not a claim that commits
preserve a single MVCC snapshot. Parent/child source changes may conservatively abort;
multi-child catchup acceptance remains open until exercised with this switch on.

Retention accounting stops before retaining a compact FETCH block beyond 1 GiB. Process memory is
checked at FETCH/frame/compute boundaries against 3 GiB (Windows/Linux current RSS;
other POSIX peak is conservative).
This is not a hard cap during individual NumPy allocations. Large-input RSS and safe
headroom remain acceptance requirements, not inferred from the small smoke.
Available Windows/Linux memory and standard v1/v2 container caps are checked too;
frame/compute entry reserves max(256 MiB, twice retained input bytes). This is a
conservative admission check, not a new cgroup controller or kernel-probe platform.
Failure/cancellation closes cursors; finally clears records and workspace ownership.

## Read-Only Preflight

Opt-in `RAW_PREFLIGHT_BATCH_ENABLED`, default false. RawRangeFacts performs 10 bounded
queries per calendar month instead of repeated per-day reads, plus the unchanged
IPO exemption queries only for invalid price limits. A transaction-scoped SHARE
lock stabilizes public preflight inputs through the caller's original commit;
there is no new per-month commit. Existing completeness evaluation
still produces all statuses/counts/codes; no ingestion or persistent-quality policy
is replaced. Calendar-month memory is released on each next group.

## Profiled CPU Hotspot

Opt-in `FACTOR_CPU_OPTIMIZATION_ENABLED`, default false. The old profiled 4-stock
run spent 10.333 s in 13,996 `_max_drawdown` calls, against 15.736 s total factor
compute. The alternative uses the identical accumulate/divide/subtract/min sequence
on NumPy arrays, avoiding a Series per rolling window. NaN is rejected as before;
0/0 is ignored by min exactly like Series.min. Listing checks use masked date
comparisons; explicit source is_active still overrides only present non-NULL facts.
No formula, version, rolling/RPS universe or exclusion-reason order changes.

Final source verification is charged to the existing 300-second publication budget;
each lock/fingerprint SQL first receives the remaining budget. There is no new
unbudgeted verification window or longer statement timeout.

## Deliberately Unchanged

AB_MERGE_READ_ENABLED remains false. No migrations/indexes, timeout increases,
candidate batch-size changes, new publication transactions, queue retries or ownership
changes. Candidate lookup/store and publication stay unchanged until actual plans
and full-scale evidence justify further work. No G1 contract adaptation, per user.
