# M13 Portfolio / Backtest Architecture

## Scope

M13.1 establishes the portfolio backtest foundation without claiming a production-grade
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
- The identity tuple contains the analysis algorithm version, Strategy hash,
  `opportunity_v1` plus its config hash, `portfolio_v1` plus its config hash,
  `execution_v3` plus its config hash, and `backtest_v3`.
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

## M13.3.1 deterministic rebalance and accounting closeout

M13.3.1 advances the immutable identities to `portfolio_v3`, `accounting_v2`, and
`backtest_v5`; `execution_v3` remains unchanged. Historical v2/v1/v4 definitions are
read-only. All four write paths use the same current-contract guard.

The daily protocol is START_OF_DAY, OPEN, CLOSE, AFTER_CLOSE. AccountGateway resolves the first
real open date from the run interval. Later dates must use the current calendar row's exact
`pretrade_date` NAV and Position snapshot; latest-before fallback is forbidden. The prior shares
become available under T+1, then current Trade Status and D-1/D adjustment factors are checked
only for those prior holdings. A gate failure occurs before any execution Attempt or Fill.

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

All Execution, Accounting, and Rebalance write services require a `BACKTEST/RUNNING` run and
acquire the same run row with `SELECT FOR UPDATE`. Migration
`0034_m13_3_1_closeout` adds plan input identity and its portfolio_v3 constraint. Public run
lifecycle orchestration, performance/benchmark calculations, corporate-action settlement,
PAPER/LIVE, and Broker integration remain deferred.
