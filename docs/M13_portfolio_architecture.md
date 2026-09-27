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
  `execution_v1` plus its config hash, and `backtest_v1`.
- M13.1 application APIs accept only `BACKTEST`. `PAPER` and `LIVE` are reserved schema values,
  not enabled operating modes.

## Candidate boundary

`OpportunityCandidateProvider` is the only M13.1 candidate adapter. It reads
`stock_opportunity_daily` for the exact requested trade date and applies the shared current
Opportunity identity filters. It never falls back to an earlier date and never recalculates
Factor, State, Sector or Theme data. Ranking fields are whitelisted and ordering is stable:
score descending, then code ascending.

An empty result and an unavailable source are distinct. `CandidateBatch.source_available`
is false when the target date contains no rows for the current Opportunity identity.

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
