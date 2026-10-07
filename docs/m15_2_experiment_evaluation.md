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

Before reading any M14 bundle, the source gate revalidates that every Trial contains the
complete fixed six-parameter set and that its canonical sorted-key JSON SHA-256 matches
the persisted M15.1 `parameter_hash`. A missing parameter or hash mismatch returns
`EXPERIMENT_EVALUATION_SOURCE_INVALID` and produces no evaluation rows.

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

The detail response preserves the original top-level identity fields and also exposes a
structured `identity` object with `evaluation_id`, `experiment_id`,
`evaluation_version`, `evaluation_config_hash`, `policy_hash`, and `source_hash`.

## M15.2.1 integrity acceptance

The closeout suite runs against PostgreSQL and covers the complete terminal-state and
missing-stage matrices, all eight cross-Trial compatibility fields, immutable Policy and
M14-generation identities, composite ownership and persistence constraints, and mixed
SUCCESS/FAILED/CANCELLED exclusion semantics. `experiment_eval_v1`, migration 0042, and
all selection formulas remain unchanged.

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
