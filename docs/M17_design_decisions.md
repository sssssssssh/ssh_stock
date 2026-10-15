# M17 Design Decisions

Baseline: b57809ff650cc25712452ff3c2d138de0ec53ef2, master, M16.6 sealed.
Taskbook: M17 Decision Journal & Paper Portfolio V1.0, 2026-10-14.
Implement A -> B -> C -> D -> E -> F with independent commits and tests.
Current delivery: A-F accepted, functional commit ad38b7e, CI 38663846267.
Independent PAPER execution is available but all runtime flags remain disabled by default.

## C Approval Contract

Approval uses request advisory -> account row -> proposal row lock order. Locked
loads refresh identity-map state so a waiting concurrent approve/reject cannot act
on a stale PENDING_REVIEW object. Actor is authenticated owner, never body data.
Explicit confirmed=true and Decimal-string weight required; no Agent tool is added.
Only ACTIVE account may approve; WATCH never executable. Reject writes no order.
Proposal/evidence remain frozen; terminal state increments version exactly once.

Approve rechecks frozen source, next real calendar open/cutoff and no started day,
validates the frozen account config, initial ledger or exact T close and its cash,
position count, quantities/value/NAV against persisted ledger. Stable sizing uses
known signal close plus adverse configured slippage estimate and existing market
quantity rules. Pending intents reserve shared cash, exposures, concentration,
positions/new buys and turnover; no assumed pending-sale proceeds. D checks
actual post-EOD prices/risk again. These are simulations, not real execution promises.

ApprovalEvent + unique PaperOrder + terminal Proposal commit together. Faults after
event flush or before commit roll back all. Same payload retries replay, changed
payload conflicts. Business blocks append a separate owner-scoped immutable audit;
they do not change the draft or manufacture a terminal approval. Public POST APIs
use existing Cookie auth and a separate business DB session, strict DTOs and safe
error codes. Account creation/lifecycle and execution passed the D/E/F gates.

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

## D Atomic Daily Replay

Accounts are forward-only, initially PAUSED, with a single INITIAL_CASH entry.
The inception is no earlier than the next still-unopened real calendar date.
Policy, execution, accounting, decision config and upstream version identity are
frozen. Runtime identity changes require a new account, not reinterpretation.
Optional account-bound observations use that frozen decision configuration.

Each EOD date is one bounded transaction under the account row lock. All three
phase heads and financial facts commit together; checkpoints are whole-day, not
partial intraday checkpoints. A rollback can safely replay the whole day. A
post-commit response loss returns the original verified bundle. F supplies Job
failure/lease evidence; readiness failures leave compact account audit events,
not fabricated hashes or successful day heads. No previous-NAV fallback or gap jump.

Market inputs are captured within the source's repeatable-read snapshot. Existing
pure AshareExecutionResolver and AccountingEngine are reused without changing the
BACKTEST guard. Sells precede buys; cash is updated after each fill. Opening-price
risk checks do not auto-shrink approved quantities. Blocked attempts are immutable
SKIPPED, no automatic retry. New buys remain unavailable until the next open day.
Unsupported adj changes, including new-buy intentions, stop the whole day.
No missing close is silently valued using an old price. Missing benchmark is NULL.
Financial facts are normalized once to existing ledger precision before hashing.
Source drift after sealing marks REVIEW_REQUIRED and never replaces financial rows.

## E Frozen Read Models And Workbench

Owner-scoped query projections verify each immutable envelope. List endpoints are
bounded and paginated, with date/stage/state filters; child detail requires the
same account as the route. Decimal financial metrics are canonical strings.
Performance reads only frozen NAV/fills/positions and orders. Missing open days
produce null gaps and suppress continuous returns/drawdown. Source corrections
never reprice the financial history. Financial/review hashes use explicit order.

OutcomeReview freezes T-close to true-calendar 1/5/20-day close marks, evaluation
identity and denominator. WATCH/rejected counterfactual marks are never financial
ledger entries. Latest review per proposal/window defines observation hit rate;
stage attribution is explicitly non-causal. Capacity is checked before writes.

The independent Vue workbench has explicit manual approval, separate journal,
portfolio, ledger and review views, responsive tables, frozen SVG charts and
retry-stable session request IDs. Read refresh never writes. Advance/review POST
only creates an owner/account job plus immutable request receipt. F validates
that receipt before worker dispatch and completes jobs atomically with results.

## F Jobs, Cancellation And Recovery

JobRun dispatch identity is frozen inside an append-only owner/account request
receipt. Type/date/config/mode/source/window and receipt scope must match before
work and at commit. Only the claimed RUNNING worker can commit; cancellation or
worker identity loss rolls back the financial transaction. Successful daily,
review and observation results commit with Job SUCCESS. Response loss after commit
cannot downgrade SUCCESS or append a second fill/fee. Progress/heartbeat use small
independent transactions and do not imply partial financial checkpoints.

Account locks are FOR NO KEY UPDATE: still exclusive against account changes and
other executors, compatible with FK KEY SHARE for cancellation audit insertion.
Independent progress/cancel JobRun locks also use NO KEY UPDATE, compatible with
the financial day heads' JobRun FK KEY SHARE. UPDATE would self-block across
sessions while the executor waits for its progress transaction.
Recovery uses account then job row locks and skips locked accounts. Stale jobs
become FAILED with immutable audit and require an explicit new request. Jobs and
account states are distinct. PAPER jobs survive generic retention and are hidden
from legacy shared job/runtime read/cancel endpoints; owner-scoped pages verify
receipt identity and count active jobs across every history page.

Optional scheduling is installed only when enabled and an automatic flag is on.
It checks today's EOD and archived latest input, never skips gaps or approves.
Account-bound observations wait for their own successful close (except before
inception). Drift marks REVIEW_REQUIRED and retains financial history. Successful
EOD expires pending drafts with append-only evidence; partial sales retain the
remaining position's last-buy context for non-causal attribution.

Financial summary preflights history row counts and UTF-8 record bytes. Default
runtime max_history_bytes is 32 MiB (maximum 64 MiB), separately from frozen
financial policy. Risk ratios have eight decimal places, counts are strict ints.
All metric hashes include the legal mutable state they summarize; frozen finance
hashes remain distinct from decision/review state. Capacity acceptance measures
real 1/30/250-day queue/claim/source/settlement on isolated PG17, including one
manually approved buy, T+1 sellability, single fee and daily cash reconciliation.
Limits are fixed at 400 SQL and 15 seconds per day. Separate frozen-summary read
measurements have a 14-SQL/30-second budget; they are not daily execution evidence.

M16 export reuses one verified archive/contract result within one request and one
deadline; subsequent requests verify again. Contract capture checks aggregate
count before bulk collection, prepares dependencies/manifest and verifies all
byte budgets before any add/flush. Existing hash and export byte conventions stay
unchanged. Node 22 and controlled ECharts options/richText are accepted inputs;
dependency advisories remain separately recorded rather than treated as cleared.

A-F were accepted on 2026-10-15 at functional commit ad38b7e / CI 38663846267.
The exact 52-item mapping, rejected candidate history, real daily advancement
measurements and operational residual risks are in M17_release_acceptance.md.
No user database migration or automatic feature enablement was performed.
