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
  `execution_v1` plus its config hash, and `backtest_v2`.
- Existing `backtest_v1` definitions remain immutable history. A future run command must reject
  any definition whose stored Backtest Engine version differs from the current engine version.
- M13.1 application APIs accept only `BACKTEST`. `PAPER` and `LIVE` are reserved schema values,
  not enabled operating modes.

## Candidate boundary

`OpportunityCandidateProvider` is the only M13.1 candidate adapter. It reads
`stock_opportunity_daily` for the exact requested trade date and applies the shared current
Opportunity identity filters. It never falls back to an earlier date and never recalculates
Factor, State, Sector or Theme data. Ranking fields are whitelisted and ordering is stable:
score descending, then code ascending.

An empty filtered result and an unready source are distinct. Readiness compares the exact
current-identity `StockStateDaily` and `StockOpportunityDaily` code sets and requires current
Core Analysis completeness. `READY` means both non-empty sets match exactly; `UNAVAILABLE`
means both sets are absent; every partial, mismatched, or Core-incomplete source is
`INCOMPLETE`. Portfolio construction fails closed unless the source is `READY`. A `READY`
source with zero candidates after portfolio filters is a valid no-signal day and produces an
all-cash target.

## Portfolio policy

`TopNEqualWeightPolicy` is a pure service. It has no database dependency. It performs stable
candidate ordering, caps the selection by `top_n` and `max_positions`, applies equal weights,
respects the single-position cap, and keeps total allocation within `1 - min_cash_ratio`.
The output is a `PortfolioTarget`; it does not create orders or fills.

## Execution and backtest boundaries

M13.1 defines `ExecutionResolver`, reason codes and `MarketExecutionSnapshot`, but deliberately
does not ship a simplified production resolver. The `BacktestEngine` is dependency-injected and
only orchestrates `TradingCalendarGateway`, `CandidateProvider`, `PortfolioPolicy`,
`ExecutionResolver` and `AccountingLedger`. Its loop imports neither SQLAlchemy nor ORM models.

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
