# M15.2 Experiment Evaluation & Selection

M15.2 evaluates a completed M15.1 experiment from persisted M14 Performance, Risk,
Trade, and Period artifacts. It never starts a backtest, resumes a failed trial, or
recalculates M14 analytics.

The result is an immutable `experiment_eval_v1` artifact containing one report, one
evaluation row per experiment trial, and marginal sensitivity rows for all six M15.1
parameters. A rank-1 trial is an **in-sample selected research candidate**. It is not a
production recommendation and is not written back to `config/portfolio.yaml`.

## Readiness and calculation

- `GET /api/v1/portfolio/experiments/{experiment_id}/evaluation/readiness`
- `POST /api/v1/portfolio/experiments/{experiment_id}/evaluations/calculate`

All trials must be terminal. Every successful trial must have a complete, comparable
`performance_v1` + `risk_v1` + `trade_v1` + `period_v1` bundle. Failed and cancelled
trials are retained as `EXCLUDED` rows. Missing analytics or incompatible bundles fail
closed and do not trigger M14 calculation.

The calculate request accepts an optional typed policy. Metric directions are fixed by
the catalog; arbitrary expressions and user-defined directions are rejected. The
effective policy, static evaluation config, and frozen source snapshot have independent
SHA-256 identities. Repeating the same identity reuses the prior artifact; a changed
policy or M14 generation creates a new immutable history entry.

## Reading artifacts

- `GET /api/v1/portfolio/experiments/{experiment_id}/evaluations`
- `GET /api/v1/portfolio/experiments/{experiment_id}/evaluations/{evaluation_id}`
- `GET /api/v1/portfolio/experiments/{experiment_id}/evaluations/{evaluation_id}/trials`
- `GET /api/v1/portfolio/experiments/{experiment_id}/evaluations/{evaluation_id}/sensitivity`

Trial pages support `status`, `feasible`, `shortlisted`, `pareto_front`, `limit`, and
`offset`. Sensitivity is a marginal grid summary, not a causal or out-of-sample claim.

## Selection rules

Constraints are inclusive and nullable metrics fail closed when required. Pareto fronts
use exact Decimal strict dominance. Feasible trials are ranked by Pareto front, primary
objective, ordered tie breakers, and finally `trial_no`. If no trial is feasible, the
artifact still succeeds with `NO_FEASIBLE_TRIALS`, an empty shortlist, and no selected
trial.

Evaluation jobs use a stable PostgreSQL advisory lock keyed by experiment and policy.
Artifact rows and the successful JobRun terminal update commit atomically. Heartbeat
recovery never deletes artifacts or creates a replacement job, and an old worker that
lost ownership rolls back all uncommitted evaluation rows.
