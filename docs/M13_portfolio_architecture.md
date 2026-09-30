# M13 Portfolio / Backtest Architecture

Current production identity is `portfolio_v3 / execution_v3 / accounting_v3 / backtest_v7`.
Sections describing M13.1 are retained as historical design context; they are not the current
runtime contract.

## Scope

Historical M13.1 established the portfolio backtest foundation without claiming a production-grade
execution engine. The dependency direction is fixed:

`Data / Analysis -> Strategy / Opportunity -> Portfolio -> Execution -> Accounting -> Backtest -> Agent`

An Agent may call an application service, but it must not import ORM models, construct SQL,
or bypass the identity and authorization boundaries.

## Configuration and identity

- `config/portfolio.yaml` is validated by `PortfolioConfig`.
- `config/execution.yaml` is validated by `ExecutionConfig`.
- Money, price, cost and weight values use `Decimal` in configuration and domain code and
  `Numeric` in PostgreSQL.
- A backtest definition freezes the complete Strategy, Opportunity, Portfolio and Execution
  configuration snapshots and their hashes.
- The historical M13.1 identity tuple used `portfolio_v1` and `backtest_v3`. The current
  executable contract is `portfolio_v3`, `execution_v3`, `accounting_v3`, and `backtest_v7`;
  older identities remain immutable history and are not silently upgraded.
- Existing `execution_v1/v2` definitions remain immutable history and are rejected by the
  execution application service. Newly created definitions freeze `execution_v3`, ruleset
  `cn_a_share_2026_v2` and synthetic order style `LIMIT_AT_OPEN`.
- Existing `backtest_v1` and `backtest_v2` definitions remain immutable history. A future run command must reject
  any definition whose stored Backtest Engine version differs from the current engine version.
- M13.1 application APIs accept only `BACKTEST`. `PAPER` and `LIVE` are reserved schema values,
  not enabled operating modes.

## Candidate boundary

`OpportunityCandidateProvider` is the only M13.1 candidate adapter. It reads
`stock_opportunity_daily` for the exact requested trade date and applies the shared current
Opportunity identity filters. It never falls back to an earlier date and never recalculates
Factor, State, Sector or Theme data. Ranking fields are whitelisted and ordering is stable:
score descending, then code ascending.

An empty filtered result and an unready source are distinct. M13.1.2 uses an independent
Portfolio source-integrity gate. For the requested date it compares exact code sets across:

1. the Point-in-Time expected universe from `expected_stock_daily_codes()`;
2. `StockDaily` Raw rows;
3. current Strategy identity `StockFactorDaily` rows;
4. current algorithm and Strategy identity `StockStateDaily` rows;
5. current Opportunity identity `StockOpportunityDaily` rows.

`READY` requires all five non-empty sets to be identical and the existing Core context gate to
pass for Market and Sector context. All five sets empty is `UNAVAILABLE`; an unavailable
expected universe, any missing or extra code, an old identity row, or incomplete Core context is
`INCOMPLETE`. Diagnostics expose stable layer names, all five counts, and at most 20 sorted
missing/extra code samples per layer. Portfolio construction fails closed unless the source is
`READY`. A `READY` source with zero candidates after portfolio filters remains a valid no-signal
day and produces an all-cash target.

## Portfolio policy

`TopNEqualWeightPolicy` is a pure service. It has no database dependency. It performs stable
candidate ordering, caps the selection by `top_n` and `max_positions`, applies equal weights,
respects the single-position cap, and keeps total allocation within `1 - min_cash_ratio`.
The output is a `PortfolioTarget`; it does not create orders or fills.

## Execution and backtest boundaries

M13.2 supplies an auditable simulated A-share `AshareExecutionResolver` for orders that already
have an explicit `target_quantity`. It executes against raw `StockDaily.open`, current identity
Trade Status, persisted Stock Limit rows and Stock Basic instrument metadata. Those four sources
are loaded in fixed batch queries; any missing row or invalid raw open makes the entire execution
batch `INCOMPLETE` with zero order, attempt or fill writes.

The resolver applies deterministic precedence, A-share board lot and maximum order quantity
rules, T+1 available quantity,
open limit blocking, adverse tick-rounded slippage, date-effective commission/stamp/transfer
fees, and SELL-before-BUY working cash. Temporary blockers remain pending and expire on the fifth
real open attempt. Oversize orders are terminally rejected as `MAX_QUANTITY_EXCEEDED`; it never
splits orders, performs partial fills or automatically reduces quantity. A NULL quantity is an
auditable single-order `INVALID_QUANTITY` reject and does not roll back valid orders in the same
batch. Resolver logic is pure and contains no ORM or Session dependency.

The `BacktestEngine` remains dependency-injected and only orchestrates
`TradingCalendarGateway`, `CandidateProvider`, `PortfolioPolicy`, `ExecutionResolver` and
`AccountingLedger`. Its loop imports neither SQLAlchemy nor ORM models.

The loop has three ordered phases for every real open date `D`:

1. `OPEN`: execute only previously created pending orders scheduled for `D`.
2. `CLOSE`: mark the post-execution account to market.
3. `AFTER_CLOSE`: consume `Candidate(D)`, build `Target(D)`, and create an intent scheduled for
   `next_trade_date(D)` from the trading calendar.

Therefore a close signal from `D` can never execute at the open of `D`. The first date may have
an empty execution phase. An intent created after the final in-range close may remain pending
for the next real open outside the backtest range, but it is never executed early.

## Persistence

Migration `0029_m13_1_portfolio_foundation` introduces:

- `portfolio_backtest_run`: immutable configuration identity and run lifecycle;
- `portfolio_order`: order intent and lifecycle;
- `portfolio_fill`: executed quantity, price and separate costs;
- `portfolio_position_daily`: daily position/accounting snapshot;
- `portfolio_nav_daily`: cash, NAV, exposure, turnover and trading cost.

All child tables carry an explicit `run_id` and cascade when a backtest definition is removed.
The repository performs persistence only; it contains no selection, allocation, or execution
rules.

Migration `0030_m13_1_1_portfolio_integrity` makes Fill ownership ledger-safe with a composite
foreign key from `(order_id, run_id)` to the matching Order, and rejects historical cross-run
rows instead of deleting them. It also enforces `available_quantity <= quantity` and the
current long-only `0..1` bounds for position and target weights.

Migration `0031_m13_2_execution_audit` adds immutable per-open `portfolio_order_attempt` rows.
Each attempt belongs to the same Run as its Order; new execution Fills reference the matching
Attempt with another same-Run composite foreign key. Fill audit now stores raw reference price,
transfer fee and cash fee total separately. Historical Fills keep a nullable Attempt reference,
backfill reference price from their price, and retain canonical cost totals.

Migration `0032_m13_2_1_execution_integrity` requires positive non-NULL Order quantities and
allows zero requested quantity only for a `REJECTED/INVALID_QUANTITY` Attempt. Database checks
also enforce outcome/reason, full-fill price and quantity, non-executed zero values, and canonical
cost components. Upgrade rejects dirty history rather than rewriting it; downgrade refuses to
discard zero-quantity audit evidence that 0031 cannot represent.

`ExecutionApplicationService.execute_open_batch()` is an internal transaction boundary. It
rejects non-BACKTEST and old execution identities, obtains account state through an injected
gateway, fails closed before writes on source gaps, and atomically inserts attempts, updates
orders and inserts executed fills. Position and NAV accounting remain reserved for M13.3.

## M13.1 API

All endpoints are authenticated and live under `/api/v1/portfolio`:

- `GET /config`
- `GET /candidates?trade_date=YYYY-MM-DD`
- `POST /targets/preview`
- `POST /backtests`
- `GET /backtests`
- `GET /backtests/{run_id}`

Creating a backtest stores a `CREATED` definition only. There is no run, broker or live-trading
endpoint in this milestone. Candidate and preview requests are read-only.

## M13.3.2 ledger and frozen run consistency closeout

M13.3.2 keeps `portfolio_v3` and `execution_v3`, and advances the immutable identities to
`accounting_v3` and `backtest_v6`. Historical accounting v2/backtest v5 definitions are
read-only. All four write paths use the same current-contract guard, which validates typed
frozen snapshots, hashes, effective cash/benchmark values, and runtime source compatibility.

The daily protocol is START_OF_DAY, OPEN, CLOSE, AFTER_CLOSE. AccountGateway resolves the first
real open date from the run interval. Later dates must use the current calendar row's exact
`pretrade_date` NAV and Position snapshot; latest-before fallback is forbidden. The prior shares
become available under T+1, then current Trade Status and D-1/D adjustment factors are checked
only for those prior holdings. A gate failure occurs before any execution Attempt or Fill.
Before rollover, NAV and PositionDaily rows reconcile by count, quantities, prices, market value,
total assets, and NAV ratio. Missing position rows cannot silently turn a portfolio into cash.

At CLOSE, `AccountingEngine` replays persisted fills in SELL-before-BUY order, then the provider
loads current status, Raw close, and current factor only for post-fill holdings. BUY cash fees are
capitalized into moving-average cost; SELL cash fees reduce realized PnL; slippage is already in
the fill price and is not deducted from cash again. Active holdings require positive Raw close.
A suspended holding without a Raw close may carry only its prior persisted close. Position and
NAV rows are rebuilt for the same run/date, making accounting retries idempotent.

At AFTER_CLOSE, `RebalancePlanner` converts target weights using close total assets and Raw
close. New holdings are floored to legal buy quantities; existing holdings retain raw economic
target quantities and validate only the resulting delta. Small illegal deltas are skipped and
`projected_quantity` records only executable children and kept pending orders. Source gaps
produce no plan, order, or cancellation writes.

Every portfolio_v3 plan stores a canonical `rebalance_input_v1` hash over signal/scheduled dates,
the frozen portfolio config hash, target snapshot, and close account snapshot. Live pending
orders are audit evidence in `plan_snapshot`, not hash input. Same-hash retries return the plan;
different-hash retries fail before loading pending state or mutating orders.

NavDaily and RebalancePlan also form the minimal phase seal. Either row closes same-day OPEN.
Once a Plan exists, Accounting can only return an identical rebuilt Close. Rebalance reloads the
authoritative NavDaily and PositionDaily snapshot, validates the caller DTO against it, and uses
the persisted snapshot for planning and hashing. This is a ledger seal, not the M13.4 runner or
checkpoint state machine.

All Execution, Accounting, and Rebalance write services require a `BACKTEST/RUNNING` run and
acquire the same run row with `SELECT FOR UPDATE`. Migration
`0034_m13_3_1_closeout` adds plan input identity and its portfolio_v3 constraint. Public run
lifecycle orchestration, performance/benchmark calculations, corporate-action settlement,
PAPER/LIVE, and Broker integration remain deferred.

## M13.3.3 persistence precision and quantity closeout

Accounting retains full Decimal precision while replaying fills and valuing holdings. The final
snapshot crosses one explicit persistence boundary before it is returned or written: cash,
market value, total assets, PnL, trading cost, and close price use scale 4; moving-average cost,
NAV, weight, and exposure use scale 8; adjustment factor uses scale 10. `ROUND_HALF_UP` matches
PostgreSQL Numeric behavior. Persisted market value, unrealized PnL, total assets, and NAV are
derived from the final quantized inputs so a database round trip cannot create a false conflict.

Canonical account payloads quantize supplied fields and sort positions, but do not repair a
caller-provided inconsistency. The integrity gate validates finite values, Position weight,
unrealized PnL, valuation source, adjustment factor, NAV exposure, and the earlier count/value/NAV
invariants. Position `realized_pnl` accumulates partial-sale results only while that holding exists;
full liquidation removes it. Run-level realized performance is a later Performance concern.

`AshareInstrumentRuleResolver` is the shared quantity authority for Rebalance and Execution.
Rebalance may emit a complete odd-lot sale as one child when it is within the instrument maximum.
Over-cap quantities are split only into children that remain legal regardless of execution order;
otherwise planning records `UNSPLITTABLE_QUANTITY` and leaves projected holdings unchanged.

Frozen Portfolio/Execution/Accounting business configuration remains executable after deployment
YAML changes. Strategy, Opportunity, and algorithm source identity changes remain incompatible.
A future M13.4 runner may route an interrupted Run to a compatible worker or explicitly create a
new Run, but cannot silently substitute source identity or mutate the frozen snapshot.

## M13.4 persistent backtest runner

`backtest_v7` introduces one production execution path: `BacktestRunner`. HTTP lifecycle methods
only queue a `portfolio_backtest` JobRun. The worker claims that job, acquires the matching Run
ownership, and executes each real open date as START_OF_DAY, OPEN, CLOSE, AFTER_CLOSE, then
DAY_COMPLETED. AFTER_CLOSE schedules only the next open date inside the Run interval; the final
date records the explicit `NO_PLAN_OUTSIDE_RANGE` policy.

Migration `0035_m13_4_backtest_runner` adds `owner_worker_id` and `ownership_version` to the Run
and creates `portfolio_backtest_checkpoint`. The unique Run/date/phase row stores STARTED,
COMPLETED, or FAILED status, canonical input and result identities, timestamps, error details,
attempt/version, and Worker owner. A durable STARTED row identifies in-flight work. Business
results and the COMPLETED update are committed together.

Execution, Accounting, and Rebalance retain their default standalone transaction behavior. The
Runner calls them with external transaction control, appends the result identity and completed
checkpoint, and then commits once. A pre-checkpoint exception rolls back both business data and
the checkpoint completion. A process loss after commit leaves a completed checkpoint whose
stored evidence is verified before it is skipped.

Resume is explicit. It first validates the frozen configuration and current source algorithm
identity, checkpoint order, and persisted business evidence. The running worker additionally
recomputes phase input fingerprints and compares current historical inputs. Missing seals,
changed inputs, conflicting ledger rows, or unverifiable business evidence reject recovery.
Heartbeat timeout marks the Job and Run FAILED for review and never replays automatically.

Authenticated lifecycle/result APIs are:

- `POST /api/v1/portfolio/backtests/{run_id}/execute`
- `POST /api/v1/portfolio/backtests/{run_id}/cancel`
- `POST /api/v1/portfolio/backtests/{run_id}/resume`
- `GET /api/v1/portfolio/backtests/{run_id}/progress`
- `GET /api/v1/portfolio/backtests/{run_id}/nav`
- `GET /api/v1/portfolio/backtests/{run_id}/positions`
- `GET /api/v1/portfolio/backtests/{run_id}/orders`

The source fingerprints detect drift but are not a complete immutable market-data snapshot.
Performance attribution, PAPER/LIVE, Broker integration, and Agent runtime remain out of scope.

### Concurrency, cancellation, and stale recovery

Every execution claim produces a lease containing `job_id`, `worker_id`, and the incremented
Run `ownership_version`. Phase-start, phase-result/checkpoint commit, cancellation, terminal
transition, failure handling, and stale recovery lock rows in one order: `JobRun` first, then
`PortfolioBacktestRun`. Locked ORM reads use `populate_existing`; every phase commit verifies
the fresh Job/Run relationship and the exact ownership generation. A former worker therefore
rolls back its business transaction and cannot fail, cancel, or complete a replacement job.

Cancellation is linearized by the Job row lock. A queued Job is cancelled immediately. A running
Job records the request and the runner observes it from a scalar database read at the next safe
phase boundary. If a phase already owns the locks, that phase's business data and COMPLETED
checkpoint commit together, and no following phase starts. At the final boundary, a committed
cancel request wins over SUCCESS; once SUCCESS holds and commits the Job lock, a later request
cannot rewrite either terminal state.

Stale recovery first discovers candidates without locks, then locks Job followed by Run and
revalidates job type, status, heartbeat, current Run pointer, worker, and ownership generation.
Only a still-stale current lease is marked FAILED. Recovery never replays phases; continuation is
always an explicit resume that creates and claims a new generation.

AFTER_CLOSE result identity version `after_close_result_v2` seals CANCEL decisions for prior
pending orders (order ID, Run ownership, final CANCELLED status, and reason). Later OPEN/status
changes to new orders and KEEP decisions remain legitimate and are not hashed as cancellation
evidence. A legacy `backtest_v7` checkpoint with no cancel decisions remains verifiable; a legacy
checkpoint that omitted actual cancellation evidence is rejected explicitly rather than rewritten.

### Downgrade operations rule

Migration `0035_m13_4_backtest_runner` is deployed history and must not be edited. Before any
downgrade below it, operations must run:

```bash
python scripts/check_m13_4_downgrade.py
```

If checkpoint rows exist, the command refuses the downgrade. Export and retain the audit history,
obtain explicit data-loss approval, and rerun with `--allow-checkpoint-data-loss` before invoking
Alembic. Direct production downgrade without this preflight is prohibited because 0035 downgrade
drops the checkpoint table.
