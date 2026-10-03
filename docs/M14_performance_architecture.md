# M14 Performance & Backtest Analytics

## M14.1 boundary

M14.1 derives performance facts from a completed M13 backtest. It reads
`portfolio_backtest_run`, `portfolio_nav_daily`, and the exact open-date set in
`trade_calendar`; it never updates an M13 table. Its only durable business outputs are
`portfolio_performance_report` and `portfolio_performance_daily`.

Later M14 phases own benchmark-relative metrics, risk-adjusted ratios, trade episodes,
period aggregation, comparison APIs, UI, and agent integration. They are intentionally
absent from M14.1.

## Identity and source integrity

The artifact identity is:

`(run_id, performance_version, performance_config_hash, source_hash)`

`source_hash` is SHA-256 over a canonical JSON payload containing the frozen M13 engine
versions, run bounds and capital, the performance identity, and every persisted NAV fact
used by the calculation. Timestamps, random identifiers other than the business `run_id`,
and physical row order are excluded. Decimal values are normalized before hashing.

The source provider fails closed unless the run is a successful `BACKTEST`, the calendar
has open dates, the ordered NAV date set exactly equals the open-date set, NAV values are
positive, total assets are positive, dates are unique and increasing, and the final NAV
matches `result_summary.final_nav` at NAV persistence precision. Cash and market value must
be nonnegative and add to total assets at money persistence precision; NAV must equal total
assets divided by initial cash; exposures, position count, and trading cost must be
nonnegative. It does not forward-fill or use a latest-before fallback.

## Calculation and persistence

`app.domain.performance` is a pure-Python, `Decimal`-only layer. Day one return is
calculated against NAV 1.0. The engine produces daily/cumulative returns, running peaks,
drawdowns, maximum-drawdown dates and recovery, underwater duration, annualized return,
and positive/negative/flat day counts. A short sample still produces annualization and
adds `SHORT_SAMPLE_ANNUALIZATION`. `max_drawdown_duration_days` belongs to the same episode
as the stored maximum-drawdown peak/trough/recovery; a longer but shallower underwater
episode cannot replace it.

The application service freezes configuration, loads and validates a source snapshot,
checks the identity, invokes the domain engine, and writes the report and all daily rows in
one transaction. Repeating an identical request reuses the existing artifact. A changed
M13 fact produces a new source hash and a new artifact while preserving history.

Migration 0037 binds each Daily row to `(performance_id, run_id)` through a composite
foreign key, backed by `UNIQUE(report.id, report.run_id)`. It also expands annualized return
to `NUMERIC(60,18)` so legitimate short-sample annualization can be persisted. Upgrade
fails closed on historical cross-run rows; downgrade fails closed when narrowing would
lose range or scale.

## Job and API flow

`POST /api/v1/portfolio/backtests/{run_id}/performance/calculate` queues a
`portfolio_performance` JobRun. The worker claims it, validates and calculates the source,
persists both tables atomically, and marks the job successful. A failure rolls the artifact
transaction back before the generic worker failure path marks the job failed.

Queue creation and artifact calculation share one stable per-run PostgreSQL advisory lock.
Concurrent queue requests therefore linearize to one active job. A worker records an
immutable `(job_id, worker_id, run_id)` execution lease and rechecks the Job row under
`FOR UPDATE` immediately before SUCCESS. A stale-worker recovery independently discovers
expired candidates, locks and refreshes each Job, then marks only still-stale ownership as
FAILED with `PERFORMANCE_WORKER_HEARTBEAT_TIMEOUT`; it neither deletes artifacts nor
automatically retries. A refreshed heartbeat wins the race, and a fenced old worker cannot
revive a failed Job. Explicit recalculation creates a new Job and reuses an already committed
artifact when its identity is unchanged.

Read APIs are:

- `GET /api/v1/portfolio/backtests/{run_id}/performance`
- `GET /api/v1/portfolio/backtests/{run_id}/performance/daily?limit=&offset=`

All three endpoints call only the performance application service.
