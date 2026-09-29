# Agent-ready Service Contracts

M13.1 prepares explicit service boundaries for a future Agent runtime; it does not add an Agent
SDK or autonomous trading loop.

## Capability levels

| Capability | Meaning | M13.1 examples |
| --- | --- | --- |
| `READ` | Read current identity and persisted definitions | config, candidates, backtest list/detail |
| `SIMULATE` | Does not touch real trading; may produce a preview or persist an experiment/backtest draft | target preview, backtest definition |
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
- Candidate consumers must inspect `source_status`. `INCOMPLETE` and `UNAVAILABLE` must not be
  interpreted as a valid empty trading signal; only `READY` may enter portfolio construction.
- A `READY` source with zero filtered candidates is a valid empty signal and all-cash target.
- Preview is a side-effect-free simulation. Backtest definition creation is also `SIMULATE`, but
  it may persist a `CREATED` simulation draft and still cannot place or execute an order.
- Definition creation persists status `CREATED`; it cannot submit, resolve or fill an order.
- `PAPER`, `LIVE`, broker adapters, production execution resolution and `/run` endpoints remain
  outside the permitted M13.1 surface.

These contracts let a later Agent layer reason over stable application services while keeping
authorization, identity, simulation and execution permissions separable.
