# M15.3 Walk-forward / OOS Validation

## Scope

M15.3 adds deterministic walk-forward orchestration and out-of-sample validation on top of the existing M13 backtest, M14 analytics, M15.1 experiment, and M15.2 evaluation contracts. The current write identity is `walk_forward_v1`.

The feature does not calculate M14 analytics, resume failed downstream work, mutate current Portfolio configuration, deploy a selected strategy, or carry an account between OOS windows.

## Frozen Study Definition

A Study freezes:

- Rolling or Expanding mode, requested date range, train/test open-day counts, and step equal to the test length.
- Complete SSE open-day evidence and a stable calendar hash.
- M15.1 base definition and the canonical six-parameter Grid.
- M15.2 evaluation policy and policy hash.
- Strategy, Opportunity, Portfolio, Execution, Accounting, and Backtest versions, snapshots, and hashes needed by downstream definitions.
- Initial cash and benchmark.

Only complete windows are persisted. Test windows are contiguous and non-overlapping. A partial tail is omitted rather than shortened.

## Window Lifecycle

`advance` is bounded by the configured maximum number of transitions. For each window it:

1. Creates exactly one training Experiment from the frozen Study definition.
2. Starts or observes that Experiment through the M15.1 service.
3. Resolves the exact-current immutable M15.2 Evaluation Artifact.
4. Accepts only rank 1. An empty shortlist ends selection without fallback.
5. Creates an independent OOS Backtest Run with the selected full parameter set and exact test dates.
6. Dispatches or observes the OOS Run through the standard M13 service.
7. Waits for externally produced, exact-owner M14 Performance, Risk, Trade, and Period artifacts.

Study and window status are dynamic projections of persisted lineage and downstream state. Cancellation persists the parent stop gate before it asks downstream services to cancel active work.

## Validation Source Gate

Before a validation job calculates anything, it reconstructs and verifies the complete evidence chain:

- Stored Study definition hash and each Window calendar hash.
- Training Experiment ownership, frozen definition, and date range.
- Evaluation ownership, identity, policy/source hashes, selected Trial, and selected in-sample Run.
- Selected Trial parameter hash and complete six-parameter value set.
- OOS Run ownership, frozen configuration, exact test date range, and successful terminal state.
- Exact train and OOS Performance/Risk/Trade/Period owners, generation identities, config hashes, benchmark, and date sets. Train dates come from the selected Trial Evaluation's pinned Performance artifact; no latest-artifact substitution is allowed.

Missing or incompatible evidence fails closed. Readiness reports the precise missing or mismatched stage and never launches M14 work.

## Metrics and Stability

Non-overlapping OOS daily returns are stitched in window/date order. Decimal compounding produces daily strategy NAV, benchmark NAV, and relative NAV. Aggregate output includes total return, annualized return, maximum drawdown, N-1 sample volatility, Sharpe, and per-window train-to-OOS degradation.

Stability is computed for each of the six M15.1 parameters using selected value counts/rates, adjacent-window switches, and deterministic warnings. Full-hash switching stores `transition_count`, `switch_count`, and `switch_rate`; each parameter stores its own adjacent value switch count/rate after canonical Decimal normalization. Default warning thresholds are `0.5` for frequent hash switching and `0.5` for low dominant-hash rate. Rates are stored so each parameter distribution sums exactly to one.

These values are research evidence only. They are not a production-best label, deployment recommendation, or live-performance guarantee.

## Persistence and Jobs

Migration `0043_m15_3_walk_forward_validation` adds:

- `portfolio_walk_forward_study`
- `portfolio_walk_forward_window`
- `portfolio_walk_forward_validation_report`
- `portfolio_walk_forward_window_validation`
- `portfolio_walk_forward_parameter_stability`

Migration `0044_m15_3_1_walk_forward_integrity` adds immutable structured lineage, train bundle owner FKs, train/test date hashes, switch metrics, policy identity, and PostgreSQL append-only triggers. Existing 0043 artifacts are backfilled only when their complete owner/date chain validates; downgrade refuses to discard the new lineage while Validation artifacts exist.

The Validation Policy (`walk_forward_validation_policy_v1`) includes only metric sample limits and stability-warning thresholds. Runtime orchestration settings such as `max_actions_per_advance` are excluded from its hash. Changing policy creates another append-only Validation artifact and never rewrites history.

A stable PostgreSQL advisory transaction lock prevents duplicate active validation work. The terminal lock order is Study advisory/row, Validation identity advisory, then Job row. The immutable Artifact and Job SUCCESS are committed atomically. Study cancellation cancels queued jobs and cooperatively stops running jobs at the terminal fence; a lost lease or stop gate rolls back the Artifact. Stale recovery rechecks the heartbeat and maps cancelled work to CANCELLED rather than creating a replacement.

## API

Authenticated endpoints under `/api/v1/portfolio/walk-forwards` cover Study creation/detail, bounded advance, cancellation, validation readiness/submission/detail/history, Validation window lineage, and parameter stability. Readiness failures contain `error_code`, `window_no`, `scope`, `missing_stage`, `details`, and deterministic `blockers`; identity mismatches never recommend replacement calculation. Errors use explicit 404, 409, or 422 mappings and do not expose configuration snapshots or credentials in logs.
