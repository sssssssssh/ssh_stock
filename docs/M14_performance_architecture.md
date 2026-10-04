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

## M14.2 benchmark and risk boundary

M14.2 adds an independent immutable `risk_v1` artifact. It does not change the M13 facts,
the M14.1 `performance_v1` schema, or any M14.1 return/drawdown calculation. The source is
exactly one successful M14.1 report and its complete daily rows, the owning run's frozen
`benchmark_code`, and `index_daily` rows for the exact same date set. Strategy returns come
only from `portfolio_performance_daily.daily_return`; callers cannot override the benchmark.

Benchmark Float values cross the source boundary as `Decimal(str(value))`, quantized to
`0.0001` with `ROUND_HALF_UP`. Day one uses `pre_close`; later days use the preceding
`close`, while every later `pre_close` must equal that close at the frozen precision. Missing,
non-finite, non-positive, extra/misaligned, or discontinuous benchmark facts fail closed.

The risk configuration is loaded independently from `config/performance_risk.yaml`; changing
it cannot alter `performance_config_hash` or create a new M14.1 artifact. Annualization days
are inherited from the base report's persisted `result_summary` rather than duplicated in the
risk configuration.

## Risk formulas and identity

`app.domain.performance.risk_engine` and `statistics` are ORM-free and Decimal-only. They
freeze the following formulas, with sample variance/covariance using `N - 1`:

- benchmark NAV compounds benchmark daily returns; relative NAV is strategy NAV divided by
  benchmark NAV; cumulative excess is relative NAV minus one;
- strategy/benchmark volatility and tracking error are sample standard deviations multiplied
  by `sqrt(A)`;
- the annual effective risk-free rate becomes a daily effective rate with Decimal `ln/exp`;
- Sharpe uses mean strategy excess over the daily risk-free rate divided by strategy sample
  standard deviation, then multiplied by `sqrt(A)`;
- downside deviation uses `sqrt(sum(min(strategy - rf_daily, 0)^2) / N)`, and Sortino uses
  the same excess-return mean divided by that daily deviation and multiplied by `sqrt(A)`;
- Calmar directly divides the M14.1 persisted annualized return by absolute persisted maximum
  drawdown;
- information ratio is mean active return divided by active sample standard deviation and
  multiplied by `sqrt(A)`;
- beta is sample covariance of strategy and benchmark divided by benchmark sample variance;
  daily alpha is `mean(strategy-rf) - beta * mean(benchmark-rf)`, and annual alpha is the
  arithmetic `alpha_daily * A`;
- correlation is sample covariance divided by the product of the two sample deviations.

With too few observations, daily benchmark/relative facts and Calmar remain available while
sample-statistical fields are null. Zero denominators also produce null ratios, not fabricated
values. Persisted warnings are deduplicated and sorted:
`INSUFFICIENT_RISK_OBSERVATIONS`, `RISK_SHORT_SAMPLE`, `ZERO_STRATEGY_VOLATILITY`,
`ZERO_BENCHMARK_VOLATILITY`, `ZERO_DOWNSIDE_DEVIATION`, `ZERO_MAX_DRAWDOWN`,
`ZERO_TRACKING_ERROR`, `ZERO_BENCHMARK_VARIANCE`, and `CORRELATION_UNDEFINED`.

`benchmark_source_hash` is SHA-256 over the benchmark code, frozen price precision identity,
and ascending `(trade_date, pre_close, close)` values. `risk_source_hash` adds the M14.1
artifact identity and source hash plus the risk version/config hash. The database identity is
`(performance_id, risk_version, risk_config_hash, benchmark_source_hash)`. A benchmark
revision therefore creates a new report and daily set without updating history.

Migration 0038 creates `portfolio_performance_risk_report` and
`portfolio_performance_risk_daily`. Composite foreign keys enforce same-run ownership,
same-performance ownership, and that every risk date exists in the selected M14.1 daily
artifact. Downgrade refuses to drop either table while risk data exists.

## Risk jobs, recovery, APIs, and errors

`portfolio_performance_risk` jobs serialize queueing and artifact calculation with a stable
per-performance advisory lock. The first report/daily write is flushed without commit, the
immutable `(job_id, worker_id, run_id, performance_id)` lease is rechecked under `FOR UPDATE`,
and artifact plus Job SUCCESS commit together. Recovery refreshes and locks each stale
candidate before marking it FAILED; a fresh heartbeat wins, a fenced old worker rolls back its
uncommitted artifact, and an explicit retry may reuse an already committed identity.

The application-service-only endpoints are:

- `POST /api/v1/portfolio/backtests/{run_id}/performance/risk/calculate`
- `GET /api/v1/portfolio/backtests/{run_id}/performance/risk?performance_id=`
- `GET /api/v1/portfolio/backtests/{run_id}/performance/risk/daily?performance_id=&limit=&offset=`

Stable source/job error codes are `PERFORMANCE_BASE_NOT_FOUND`,
`PERFORMANCE_ARTIFACT_RUN_MISMATCH`, `PERFORMANCE_BASE_IDENTITY_INVALID`,
`PERFORMANCE_BASE_DAILY_INCOMPLETE`, `BENCHMARK_CODE_MISSING`,
`BENCHMARK_SOURCE_INCOMPLETE`, `BENCHMARK_SOURCE_INVALID`,
`BENCHMARK_PRE_CLOSE_MISMATCH`, `PERFORMANCE_RISK_CALCULATION_CONFLICT`,
`PERFORMANCE_RISK_OWNERSHIP_LOST`, and `PERFORMANCE_RISK_WORKER_HEARTBEAT_TIMEOUT`.

## M14.3 trade and cost analytics boundary

M14.3 adds an independent immutable `trade_v1` artifact over one successful M14.1
performance artifact and the owning M13 Order, Attempt, Fill, NAV, and Position ledgers.
It does not update M13, M14.1, or M14.2 rows. The strict configuration lives in
`config/performance_trade.yaml`; annualization days are inherited from the selected M14.1
report. All source queries are fresh reads and fail closed on cross-owner identities,
Attempt/Fill cardinality or ledger differences, non-finite values, an incomplete performance
date set, a daily Fill-cost/NAV-cost difference, or a Position replay difference.

The immutable database identity is
`(performance_id, trade_version, trade_config_hash, trade_source_hash)`. The source hash
covers the selected performance identity and versions, frozen M13 engine versions and
initial capital, and every participating Order, Attempt, Fill, NAV, and Position fact in
canonical order. An identical calculation reuses its artifact; a valid source revision
creates a new report/daily/episode set and preserves history.

### Episode, PnL, cost, and turnover semantics

Fills replay by date, with SELL before BUY, then `scheduled_trade_date`, `order_id`, and
`fill_id`, exactly matching M13 accounting. An episode is one continuous positive-quantity
holding interval. Adds and partial sells stay in the same episode; quantity reaching zero
closes it; a later buy (including one later in that same date's replay) increments
`episode_no`.

BUY average cost is `(old_avg_cost * old_quantity + gross_amount + cash_fee_total) /
new_quantity`. SELL realized PnL is `gross_amount - cash_fee_total - avg_cost * quantity`.
Slippage remains a separately reported execution cost and is not deducted a second time
from the fill-price PnL. Only closed episodes participate in win rate, profit factor, payoff,
best/worst, and holding-period statistics. An open episode reports final persisted realized
and unrealized PnL but no episode return.

Daily turnover is double-sided `buy_gross + sell_gross` without division by two. Day one
uses initial cash as denominator and later dates use previous-day total assets. Zero-fill
dates still persist a zero daily row. Total turnover is the daily sum and annualized turnover
is average daily turnover multiplied by the inherited M14.1 annualization days. Report,
daily, and episode fill/cost totals reconcile before persistence.

Migration 0039 creates `portfolio_performance_trade_report`,
`portfolio_performance_trade_daily`, and `portfolio_performance_trade_episode`. Composite
foreign keys bind children to the same trade/performance/run owner and bind every daily row
to both the selected performance date and run NAV date. Downgrade refuses to drop these
tables while any trade artifact exists.

### Trade jobs and APIs

`portfolio_performance_trade` uses a distinct stable per-performance advisory lock, so it
can run independently of `portfolio_performance_risk`. Artifact writes remain uncommitted
until the worker's `(job_id, worker_id, run_id, performance_id)` lease is rechecked under
`FOR UPDATE`; artifact rows and Job SUCCESS then commit atomically. Stale recovery refreshes
under lock, marks only still-stale jobs failed with
`PERFORMANCE_TRADE_WORKER_HEARTBEAT_TIMEOUT`, and never silently retries.

The application-service-only endpoints are:

- `POST /api/v1/portfolio/backtests/{run_id}/performance/trade/calculate`
- `GET /api/v1/portfolio/backtests/{run_id}/performance/trade?performance_id=`
- `GET /api/v1/portfolio/backtests/{run_id}/performance/trade/daily?performance_id=&limit=&offset=`
- `GET /api/v1/portfolio/backtests/{run_id}/performance/trade/episodes?performance_id=&status=&ts_code=&limit=&offset=`

Callers may select a base performance artifact and filter reads, but cannot override replay,
cost, PnL, episode, epsilon, or turnover definitions.
