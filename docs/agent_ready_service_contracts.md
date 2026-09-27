# Agent-ready Service Contracts

M13.1 prepares explicit service boundaries for a future Agent runtime; it does not add an Agent
SDK or autonomous trading loop.

## Capability levels

| Capability | Meaning | M13.1 examples |
| --- | --- | --- |
| `READ` | Read current identity and persisted definitions | config, candidates, backtest list/detail |
| `SIMULATE` | Produce an in-memory, non-persistent result | target preview |
| `MUTATE_DRAFT` | Persist a mutable research draft | reserved for a future challenger strategy |
| `EXECUTE` | Produce orders/fills or touch a broker | not exposed in M13.1 |

## Allowed application surface

A future Agent may depend on `PortfolioApplicationService` methods:

- `get_config_status()` (`READ`)
- `list_candidates(trade_date)` (`READ`)
- `preview_target(trade_date)` (`SIMULATE`)
- `create_backtest_definition(...)` (`SIMULATE`)
- `list_backtests()` and `get_backtest(run_id)` (`READ`)

The Agent must use the authenticated API or these application methods. It must not depend on
`PortfolioRepository`, ORM types, SQLAlchemy sessions, or database tables directly.

## Safety invariants

- Every result reports Portfolio, Execution, Opportunity and Backtest identity metadata.
- Candidate reads use the exact requested date and current Opportunity identity only.
- `source_available=false` must not be interpreted as a valid empty trading signal.
- Preview is side-effect free.
- Definition creation persists status `CREATED`; it cannot submit, resolve or fill an order.
- `PAPER`, `LIVE`, broker adapters, production execution resolution and `/run` endpoints remain
  outside the permitted M13.1 surface.

These contracts let a later Agent layer reason over stable application services while keeping
authorization, identity, simulation and execution permissions separable.
