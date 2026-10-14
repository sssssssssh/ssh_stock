# M17 Design Decisions

Baseline: b57809ff650cc25712452ff3c2d138de0ec53ef2, master, M16.6 sealed.
Taskbook: M17 Decision Journal & Paper Portfolio V1.0, 2026-10-14.
Implement A -> B -> C -> D -> E -> F with independent commits and tests.
Current delivery: A accepted, B source/draft implementation under PG acceptance.
No usable PAPER execution runtime yet.

## B Source And Draft Contract

DecisionSourceReadiness uses an independent REPEATABLE READ / READ ONLY transaction.
Exact source-integrity and RawCompleteness gates are reused without ingestion,
recalculation or persistence. Current metadata versions, exact code sets, ST/status,
successful calculation Job IDs/date scopes and raw-update/factor timestamps are
verified. Any open/failed/processing dirty range affecting T blocks observation.
Queries fix trade_date=T, never consume future prices/scores or forward outcomes.
Source rows are bounded by decision.max_source_rows; selected records are bounded
by top_n plus <=100 explicit context codes. Hashes bind full source layers and
selected instrument metadata; profile/name is captured reference metadata, not a
claim that mutable StockBasic name is PIT history. T status is the risk truth.

Rule v1 sorts full-precision score DESC/code ASC, keeps raw reason codes and separate
BLOCKED/WATCH risk codes. Paper-only stage/score filters reuse the existing provider;
M13 production config is unchanged. Draft score is normalized to its NUMERIC scale,
while original precision is preserved in frozen candidate evidence.

DecisionApplication uses owner/request advisory locks and canonical payload hashes.
Retry returns the same verified immutable record; changed payload conflicts. New
requests can freeze repaired T facts without changing old observations. Drafts
recheck exact source hash, require owner-matched account/observation/security and
freeze optional M16 owner/hash/date/level references as context, never permission.
WATCH creates no order and can log old evidence; actionable drafts expire at the
actual next calendar opening cutoff. Superseding revisions never rewrite content.
Shared record envelopes bind every immutable typed column, identity, timestamp and
source JSON; mutable heads are excluded and separately guarded by DB state triggers.
B has no approval or execution side effects; its service/DTOs precede C/E APIs.

## A Schema Contract

Migration 0053_m17_decision_paper_foundation descends from 0052. No BACKTEST
history is copied and no M13-M16 table, strategy, formula or hash is rewritten.
Each record has UUID id, owner, aware UTC created_at, schema_version,
record_json and record_hash. Record JSON is a bounded 128 KiB versioned object;
layer-specific DTOs are delivered by later phases. Services must bind all typed
facts into the canonical contract; hash format checks alone do not prove truth.

| Table / ORM | Typed facts beyond common envelope | Constraints |
|---|---|---|
| paper_account / PaperAccount | name/mode/state/cash/benchmark/first date/config/activation/version/request | PAPER; finite positive cash; owner/name and owner/request unique |
| paper_account_event / PaperAccountEvent | account/from/to/request | same owner; request unique; append-only |
| decision_observation / DecisionObservation | signal/READY/cutoff/ready/strategy hash/request | ready<=cutoff<=created; request unique; append-only |
| decision_proposal / DecisionProposal | account/observation/code/action/weight/stage/score/revision/state/expiry/supersedes/request | scoped parents; finite weight; immutable facts; version+1 legal transitions |
| decision_approval_event / DecisionApprovalEvent | proposal/account/actor/decision/approved weight/time/request | actor=owner; one event/proposal; scoped parents; append-only |
| paper_day_run / PaperDayRun | date/phase/status/source/input/result/generation/lease/job/error | account/date/phase unique; frozen input; successful result sealed |
| paper_order / PaperOrder | approval/proposal/signal/schedule/code/side/qty/weight/type/mode/status/source | same approval/proposal/account/owner; one order/approval; one pending code/account; NEXT_OPEN/PAPER |
| paper_order_attempt / PaperOrderAttempt | order/date/number/outcome/reason/market hash/policy | scoped order; order/date/number unique; append-only |
| paper_fill / PaperFill | attempt/order/date/code/side/qty/prices/gross/fees/cash | exact parent scope/date; one fill/attempt; cash formula; append-only |
| paper_ledger_entry / PaperLedgerEntry | day/fill/date/key/type/cash/share/instrument | exact scope/date; key/fill unique; one initial entry/account; append-only |
| paper_position_daily / PaperPositionDaily | day/date/code/qty/sellable/cost/price/value/PnL/adj/source | exact scope/date; account/date/code unique; sellable<=qty; append-only |
| paper_nav_daily / PaperNavDaily | day/date/cash/value/assets/NAV/benchmark/cost/count/source | exact scope/date; account/date unique; assets=cash+value; missing benchmark NULL; append-only |
| paper_outcome_review / PaperOutcomeReview | proposal/asof/window/eval/source/status | scoped proposal; proposal/date/window/version unique; append-only |

DDL is explicit in migration, not imported from live ORM or create_all. Isolated
PG tests compare metadata, exercise constraints/triggers and legacy-row roundtrip.
All parents RESTRICT deletion. Any M17 history blocks downgrade; disabling config
is the non-destructive rollback. No production migration is executed by development.

## Identity And State

M17 canonical JSON uses sorted keys, context-independent finite Decimal strings,
ISO dates, aware UTC timestamps; no floats, naive times or non-string keys.
Stable UUID5 IDs are owner-namespaced and business-key/version bound.
Published M13-M16 canonical functions remain unchanged.
Money/raw prices use NUMERIC(24,4), cost/NAV (24,8), adj (24,10), weight (12,8).
D must reuse ledger precision normalization and assert reconciliation, not repair it.

Account CREATED -> ACTIVE/PAUSED/CLOSED, ACTIVE <-> PAUSED, CLOSED terminal.
Proposal DRAFT -> PENDING_REVIEW -> APPROVED/REJECTED/EXPIRED; draft can expire.
ORDER_PENDING -> FILLED/SKIPPED/CANCELLED/EXPIRED, terminal immutable.
Head transitions require version+1 and cannot change frozen facts. Successful day
can only become REVIEW_REQUIRED with error, not rewrite hash/generation/job/lease.
Generation/lease fields are storage only: crash/ownership protocol is a D/F gate.

## Forward Policy And Remaining Design

config/paper.yaml is validated by Settings.build. All flags default false;
auto_approve=true is forbidden. Only PAPER, MANUAL_CONFIRM and
POST_EOD_SIMULATED_OPEN are supported. A adds no API/worker/scheduler actions.
Paper-only limits: 10 positions, 10% single weight, 2% cash floor, 2 new positions,
30% sector/theme concentration, 50% daily turnover. Freeze execution/accounting
and paper policy at account creation. Names are unique per owner, including closed
history; use distinct names, never replace old accounts.

first_trade_date is explicit forward inception. Calendar and approval clock use
Asia/Shanghai, real SSE/SZSE opens, and opening cutoff; never backdate approvals.
D requires complete EOD before replay of previously approved NEXT_OPEN intents,
pure existing engines, stable sells-first, shared cash, T+1 and sequential dates.
Blocked orders SKIP_NO_RETRY; corporate actions fail closed; source corrections
require review, never rewriting ledger. Missing benchmark unavailable, not zero.
F must exclude PAPER jobs from retention; RESTRICT alone is not retention scheduling.
No broker, LIVE, LLM write tools or changing BACKTEST mode guards.

Gates: A schema/PG/config; B readiness/T facts/drift/ranking/idempotency;
C manual approval/risk/atomic intent/races; D financial replay/retry/locks;
E frozen reviews/API/1440+390 UI; F jobs/recovery/performance/Runbook/full CI.
See M17_release_acceptance.md for actual evidence and incomplete items.
