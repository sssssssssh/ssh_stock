# M16.1 Contract Inventory

## Scope

M16.1 adds a deterministic, authenticated, read-only tool layer. It does not add an
LLM, chat history, autonomous planning, data writes, recalculation, job creation, or
broker access. No database migration is required.

## Dependency graph

```text
HTTP /api/v1/agent
  -> AgentApplicationService
    -> explicit AgentToolRegistry (8 tools, version 1.0)
      -> MarketDataAgentAdapter
        -> L1 TradeCalendar / DataQualityDaily
      -> OpportunityAgentAdapter
        -> audited L2 read queries
          -> MarketDaily / SectorFactorDaily / ThemeFactorDaily
          -> StockOpportunityDaily
      -> ResearchAgentAdapter
        -> L3 PortfolioBacktestRun / PortfolioNavDaily
        -> L3 M14 Performance/Risk/Trade/Period reports
        -> L3 M15.3 WalkForward Study/Validation reports
```

Only DTO dictionaries and `EvidenceRef` values cross the adapter boundary. ORM
instances and SQLAlchemy sessions never enter tool results.

## Existing read contracts

| Layer | Persisted sources | Existing identity/read contract | M16.1 consumer |
| --- | --- | --- | --- |
| L1 | `trade_calendar`, `data_quality_daily` | Date-bounded quality rows; persisted status and coverage | `data.coverage` |
| L2 | `market_daily` | `MARKET_CALC_VERSION` + analysis strategy hash | `market.snapshot` |
| L2 | `sector`, `sector_factor_daily` | `SECTOR_CALC_VERSION` + analysis strategy hash | `sector.top` |
| L2 | `theme`, `theme_factor_daily` | `theme_factor_identity_filters()`; persisted `member_snapshot_date` | `theme.top` |
| L2 | `stock_basic`, `stock_opportunity_daily` | `opportunity_identity_filters()` | `opportunity.list` |
| L3 | `portfolio_backtest_run`, `portfolio_nav_daily` | Exact `run_id`, successful `BACKTEST`, frozen identity columns | `backtest.summary` |
| L3 | four M14 report tables | Exact report owners and persisted version/config/source hashes | `performance.summary` |
| L3 | Walk-forward Study/Validation | Exact `study_id + validation_id`; stored policy/source identity | `walk_forward.summary` |

Existing user-facing read APIs remain authoritative for the application UI:
`/system/data-coverage`, `/dashboard`, `/sectors`, `/themes`, `/opportunities`,
`/portfolio/backtests`, `/portfolio/backtests/*/analytics`, and
`/portfolio/walk-forwards`. M16.1 does not replace or change them.

## Existing write services excluded from Agent

The registry does not expose ingestion, recalculation, jobs, backtest execution,
experiment lifecycle, M14 calculation, or Walk-forward advancement/validation
calculation. In particular, `IngestionService`, `RecalculationService`,
`BacktestApplicationService`, `ExperimentApplicationService`,
`Performance*ApplicationService`, and `WalkForwardApplicationService` write paths
are not dependencies of any M16.1 handler.

## Gaps closed by M16.1

- A stable DTO/evidence envelope did not exist for future model consumers.
- Existing APIs returned endpoint-specific shapes and sometimes ORM-derived payloads.
- No explicit allowlist prevented a future agent from gaining arbitrary SQL/HTTP/path
  capabilities.
- M14 run-based reads could select a latest artifact. M16.1 rejects ambiguous runs and
  requires `report_id` when more than one performance report exists.
- The existing authentication model has no role column. This deployment is therefore
  documented as single-tenant authenticated administrator access, not multi-tenant RBAC.

## Non-goals and unresolved items

- Real LLM integration, prompt storage, conversations, autonomous orchestration and
  citations rendered by a model are M16.2 or later.
- Tenant/role authorization requires a separate identity model and migration.
- Source-wide immutable Raw snapshots do not exist; evidence references the persisted
  quality record or derived/report identity currently available.
- M16.1 does not repair missing data and reports `DATA_UNAVAILABLE`, `DATA_INCOMPLETE`,
  `NOT_READY`, or `SOURCE_IDENTITY_MISMATCH` instead.
