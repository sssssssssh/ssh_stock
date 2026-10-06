# M15 Strategy Experiment Architecture

## 1. Scope and boundary

M15.1 introduces a persistent strategy-experiment plan over the existing M13 backtest
runtime. It creates deterministic Portfolio parameter trials and delegates every execution
to an ordinary M13 child backtest. It does not calculate M14 artifacts, rank trials, choose
a best strategy, run non-grid search, perform walk-forward/OOS validation, add a UI, or
create an experiment parent `JobRun`.

## 2. Configuration and allowed parameter surface

`config/experiment.yaml` is validated by strict `ExperimentConfig` and freezes
`experiment_v1`, `GRID`, `max_trials=128`, and `max_values_per_parameter=20`. The only
tunable paths are, in canonical order:

1. `candidate.min_score`
2. `candidate.top_n`
3. `construction.max_positions`
4. `construction.max_single_position_weight`
5. `construction.min_cash_ratio`
6. `construction.max_new_positions_per_day`

The API uses nested typed request models. Missing fields inherit the current Base Portfolio
Config as singleton lists. Generic patch paths and Strategy, Opportunity, Execution, or
Accounting search fields cannot cross the request boundary.

## 3. Deterministic Grid domain

The ORM-free Grid domain canonicalizes finite Decimals to non-exponent strings, rejects
duplicates after canonicalization, sorts every list numerically, validates list and total
limits, and expands with `itertools.product` so the rightmost parameter changes fastest.
Every combination must pass `PortfolioConfig` plus `top_n >= max_positions` and
`max_new_positions_per_day <= max_positions`; one invalid combination rejects the whole
definition.

Every Trial stores the complete six-value parameter map, a parameter hash, the complete
validated Portfolio snapshot, and its config hash. Parameter-space and Trial hashes use
canonical, sorted-key JSON and exclude timestamps, names, and UUIDs.

## 4. Experiment identity

`definition_hash` binds the experiment/search versions; date, cash, and benchmark; frozen
Strategy/Opportunity source identities; Portfolio/Execution/Accounting versions and config
hashes; Backtest engine version; and parameter-space hash. It deliberately excludes the
Experiment ID, name, audit timestamps, and random identifiers. Equal definitions are allowed
and indexed, not unique.

## 5. Persistence and migration

Migration `0041_m15_1_experiment_foundation` only adds `portfolio_experiment` and
`portfolio_experiment_trial`. A Trial belongs to its Experiment with cascade delete and may
bind one globally unique Run through a restrictive FK. Trial number and parameter hash are
unique within the Experiment. No Trial status/job/error columns exist; M13 Run and Job rows
remain authoritative. Downgrade refuses while either table contains data.

## 6. Shared child-run factory

`BacktestRunFactory` builds an unsaved `PortfolioBacktestRun` from explicit frozen snapshots
and identities. The existing single-backtest API and Experiment materialization use this
same factory, so both paths freeze and hash Strategy, Opportunity, Portfolio, Execution, and
Accounting identically. Persistence and transaction ownership stay with the caller.

## 7. Atomic create

Create loads the current base identities/configuration, validates and expands the entire
Grid, computes all identities, and inserts the Experiment plus every Trial in one transaction.
The reported count equals persisted Trial rows. Create produces no Backtest Run and no Job.

## 8. Start, idempotence, and concurrency

Start has two phases. Phase A acquires an Experiment advisory transaction lock, locks the
Parent and ordered Trial rows, validates the source gate and all stored hashes/snapshots,
materializes every missing Child Run, binds every Trial, sets first `started_at`, and commits
once. Any failure rolls back every new Run binding.

Phase B walks Trials by `trial_no`. Every dispatch reacquires the Experiment advisory
transaction lock, locks and freshly reads the Parent stop gate, freshly reads the Trial/Run/Job
projection, and calls `BacktestApplicationService.execute()` only for an eligible CREATED Run
before committing. The cancellation check and M13 job creation are therefore in one
Experiment serialization window. Active jobs and RUNNING/terminal Runs are skipped. An
active-job conflict referring to the same Run is an idempotent success. Repeated Start
therefore creates neither another Run nor another active job.

The global lifecycle lock order is Experiment advisory transaction lock →
`portfolio_experiment` row → M13 Run/Job locks. Cancel commits the Parent stop gate and
releases the first two locks before iterating children through M13 cancellation. It never
holds the Experiment lock while acquiring child locks, so dispatch/cancel cannot form a
reverse-order deadlock. If cancel wins, later dispatch sees the committed gate and creates no
Job; if dispatch wins, cancel observes and cancels the new M13 generation.

## 9. Runtime source identity gate

Before materialization, runtime algorithm version, analysis Strategy hash, Opportunity
calculation version, and Opportunity config hash must match the frozen Experiment source
identity. Portfolio, Execution, and Accounting can execute from their frozen snapshots, but
the current candidate provider still selects facts from runtime source identity. A mismatch
returns `EXPERIMENT_SOURCE_IDENTITY_DRIFT` with zero new Runs and Jobs.

## 10. State, progress, and reads

Trial state is `PLANNED` without a Run, otherwise exactly the Child Run status. Experiment
state and counts are dynamic projections: CREATED before Start, RUNNING while work remains,
SUCCESS when all succeed, FAILED when a terminal zero-success set contains a failure,
CANCELLED when all Trials are manually cancelled, and COMPLETED_WITH_ERRORS for all other
mixed terminal sets. A committed Parent cancel gate also projects CANCELLED as soon as no
Child is active. Progress is terminal Trial count divided by planned count.

Trial pages outer-join Run and current Job in one query and can filter by derived state; they
do not query Checkpoints per row. Single Trial Detail may call the existing Backtest progress
service for phase-level progress.

## 11. Cancellation, API, and errors

Cancel locks the Experiment, persists `cancel_requested`, and commits before touching Child
Runs. It then delegates active Child cancellation to the M13 service. Completed children are
unchanged, unqueued CREATED children are not dispatched, PLANNED children are not
materialized, and one Child conflict cannot roll back the Parent gate.

Authenticated endpoints under `/api/v1/portfolio/experiments` create, start, read, page/read
Trials, and cancel. Schema/config errors return 422, missing resources return 404, and
identity/state conflicts return 409 with stable `EXPERIMENT_*` codes. Persistence exception
details are not exposed to clients.

## 12. M15.1.1 lifecycle recovery and observability closeout

Test-only fault hooks can stop materialization before any selected Trial, after the single
Phase A commit, or inside a serialized dispatch window. They are inert by default and do not
change the API or domain contract. PostgreSQL integration tests prove all-or-nothing Phase A,
reuse of materialized Run IDs after a pre-dispatch crash, partial-dispatch retry without job
duplication, both dispatch/cancel race orders, terminal child non-resume, manual M13 resume
observation, and generation-aware child cancellation.

Lifecycle logs are structured and allowlisted. Creation, materialization, dispatch/skip,
cancel gate/child cancellation, source drift, and identity mismatch events include only
scalar IDs, Trial number, safe hashes, operation, outcome, and mismatch field names. Frozen
configuration snapshots, parameter-space bodies, provider tokens, cookies, and secrets are
never serialized.
