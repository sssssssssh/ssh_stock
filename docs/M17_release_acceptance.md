# M17 Release Acceptance

## Release Gate

A-F accepted and sealed on 2026-10-15. Final functional commit:
`ad38b7e5a4dab785090148b2e23c29f49c0dfe2e`.
[Full CI 38663846267](https://github.com/sssssssssh/ssh_stock/actions/runs/38663846267)
passed: 1641 pytest (142 warnings, 88% backend coverage), full Ruff, PostgreSQL 17
migration roundtrip and 0053 current=heads, Docker Compose/config/build/Nginx,
122 Vue tests (82.22% statement coverage), production build and actual Chromium
acceptance at 1440/390. No migration, cleanup, test writes or PAPER transactions
were run against the user's business database. All automatic flags remain false.

| Phase | Accepted commit | Full CI | pytest |
|---|---|---|---|
| A | 219120b | [38501965762](https://github.com/sssssssssh/ssh_stock/actions/runs/38501965762) | 1420 |
| B | cd7ec91 | [38506248886](https://github.com/sssssssssh/ssh_stock/actions/runs/38506248886) | 1443 |
| C | dc773eb | [38509773000](https://github.com/sssssssssh/ssh_stock/actions/runs/38509773000) | 1480 |
| D | a0f0cd4 | [38514217405](https://github.com/sssssssssh/ssh_stock/actions/runs/38514217405) | 1518 |
| E | e920652 | [38528878133](https://github.com/sssssssssh/ssh_stock/actions/runs/38528878133) | 1545 |
| F | ad38b7e | [38663846267](https://github.com/sssssssssh/ssh_stock/actions/runs/38663846267) | 1641 |

Each accepted phase includes full pytest/Ruff, isolated PostgreSQL 17 migration
roundtrip and current=heads, Compose/container build, frontend coverage/build and
legacy browser regression. E adds actual M17 browser acceptance at 1440/390.
Migration head stays `0053_m17_decision_paper_foundation`; no F migration.

F local commands: `python -m pytest tests/unit -q` (1299 passed, two inherited
deprecation warnings); `npm run test:coverage` with Node 22 (122 passed, 82.22%
statement coverage). Full Ruff, production build and actual Edge browser acceptance
at 1440/390 passed, including the complete PAPER/non-live/no-return-promise badge.
Full `python -m pytest` runs only on CI's disposable PostgreSQL 17, not stock_db.

## Scope And Contracts

F adds worker dispatch for PAPER_DAILY/REVIEW/OBSERVATION, immutable dispatch
receipts, commit-time worker/cancellation fencing, atomic job/result completion,
stale-job audit, explicit retry, optional EOD scheduling and retention protection.
Owner-scoped API adds job cancellation and account-wide active-job count. Legacy
shared job/runtime endpoints do not expose private PAPER jobs. No new table/API
permits LIVE, broker execution, Agent writes or automatic approval.

Changed areas: backend API, paper services/repository, decision metrics, existing
Worker/Scheduler/retention dispatch, M16 contract/report resource paths, Vue
workbench/service, CI and regression tests. F adds no schema/table/column. The new
write API is `POST /api/v1/paper/accounts/{account_id}/jobs/{job_id}/cancel`;
own jobs GET now returns `meta.active_count`. For the exact F file list, run
`git diff --name-only e920652..ad38b7e`; A's 0053/13-table delivery is unchanged.

Financial formulas remain Decimal. Partial sales retain the remaining position's
last-buy stage; completed EOD expires unapproved drafts without changing frozen
evidence. Approval/execution/attribution metrics expose versions, dates,
denominators and input hashes. Financial and counterfactual results remain separate.

M13-M16 identities, hashes and BACKTEST guards remain unchanged. M16 P2 changes
only request-local verification reuse and pre-collection/pre-write capacity checks;
subsequent HTTP requests still reverify. Existing frozen report bytes are tested.

## Checklist Mapping

All paths below are relative to `tests/` unless specified. Every item 01-52 passed
its mapped acceptance in the final full CI. Item 51 is a risk review and input
regression, not a claim that inherited dependency advisories have been repaired.

| # | Taskbook assertion | Test / evidence |
|---|---|---|
| 01 | 0052/0053 roundtrip; legacy rows/hashes unchanged | integration/test_m17_foundation.py, roundtrip test |
| 02 | Nonempty PAPER downgrade refused | same, any_paper_history_blocks_downgrade |
| 03 | Account create/pause/activate/close, illegal transitions | integration/test_m17_paper_daily.py; unit/test_m17_foundation_contracts.py |
| 04 | Independent PAPER, not BACKTEST | foundation contracts; real daily write path; full M13 regressions |
| 05 | Cross-owner child reads/writes return 404 | integration/test_m17_paper_queries.py; manual_approval; paper_jobs |
| 06 | Default disabled, no autonomous fills | unit/test_m17_job_contracts.py; integration/test_m17_paper_jobs.py |
| 07 | Closed-day observation refused | integration/test_m17_decision_sources.py, readiness cases |
| 08 | Missing/stale/partial source fails closed | same, readiness_failures_make_no_observation |
| 09 | T capture excludes T+1 facts | same, t_boundary_ignores_future_price_and_score |
| 10 | Corrections cannot overwrite prior hashes | same; foundation immutable guards |
| 11 | Stable score/code TopN sorting | same, frozen deterministic observation |
| 12 | Risk/WATCH reasons retained | same, owner_security_watch_risks_and_revision |
| 13 | Explicit manual gesture; Agent read-only | unit/test_m17_decision_api.py; frontend workbench; browser script; old Registry tests |
| 14 | WATCH/reject creates no execution | integration/test_m17_manual_approval.py |
| 15 | Approval and order atomic | same, approval_event_and_intent_atomic_idempotent_and_frozen |
| 16 | Precommit approval fault rolls back | same, fault_before_commit cases |
| 17 | Same request/payload replays | sources; manual_approval; paper_queries; paper_jobs |
| 18 | Request payload mismatch gives conflict | sources; manual_approval; paper_queries |
| 19 | Concurrent approve/reject has one outcome | integration/test_m17_manual_approval.py, real_concurrent test |
| 20 | Cannot backfill expired approval window | same, failed_approval cases |
| 21 | Paused/closed cannot approve execution | same; integration/test_m17_paper_daily.py |
| 22 | Position/cash/count/weight limits | unit/test_m17_approval_contracts.py; real approval and daily tests |
| 23 | Conflicting pending symbol rejected/audited | integration/test_m17_manual_approval.py |
| 24 | SSE/SZSE true next open, not natural day | approval; daily; source fixtures and calendar assertions |
| 25 | Full next-day EOD gate | integration/test_m17_paper_daily.py; paper_jobs; EOD source timestamp tests |
| 26 | Bad price/zero volume cannot fill | unit/test_m17_paper_execution.py, conservative_market_blocks |
| 27 | Suspension/ST/limits fail conservatively | same; PG limit_block_is_final |
| 28 | Lots/odd lots/side/quantity bounds | unit/test_execution_resolver.py; test_m17_approval_contracts.py |
| 29 | T+1 sellability | unit/test_m17_paper_execution.py; PG daily and real 250-day assertions |
| 30 | Exact Decimal fees/taxes/slippage | pure execution/accounting tests; PG exit_next_open and capacity |
| 31 | Shared cash, sell-before-buy, no negatives | risk reservations; execution resolver/accounting; PG daily conservation |
| 32 | Unique order/attempt/fill/ledger keys | foundation PG constraints; daily idempotent replay; jobs retries |
| 33 | Faults before order/after fill/before NAV/commit; lost reply | integration/test_m17_paper_jobs.py, crash and postcommit cases |
| 34 | Concurrent workers commit once | same, two_executions; daily concurrent_workers |
| 35 | Source drift marks review, never reprices | PG daily/queries/jobs source correction tests |
| 36 | Unsupported corporate action fails closed | PG company_action_stops_before_first_fill; pure market cases |
| 37 | Cash/qty/fee/assets/NAV conservation | PG daily and capacity, committed ledger reconciliation |
| 38 | Cannot skip an open day | PG daily missing_day; jobs scheduler_blocks_gap |
| 39 | Pause/resume sequential; no phantom backfill | PG pause_resume_is_sequential; job/scheduler gap checks |
| 40 | Missing benchmark is NULL, not zero | PG daily and queries benchmark tests |
| 41 | Counterfactual return never enters NAV | PG queries WATCH review; capacity counterfactual_returns |
| 42 | Reviews do not rewrite original decisions | same, append-only/hash assertions; foundation guards |
| 43 | M16 report owner/hash/date binding, no authority | PG decision_sources exact report reference |
| 44 | No LIVE/broker endpoint or parameter | unit/test_m17_decision_api.py and paper execution DTO tests |
| 45 | M13-M16 full compatibility | full pytest in every phase CI, immutable report bytes and hashes |
| 46 | Real 1/30/250-day advance SQL/time bounded | integration/test_m17_paper_capacity.py, real_daily_queue_claim_source_and_settlement_are_bounded |
| 47 | 1440/390 layout, filters, confirmation, warnings | scripts/m17_browser_smoke.cjs; Vue workbench/chart tests; screenshots |
| 48 | Outage/double-click/reload safe | same browser; workbench retry tests; PG idempotence/lost response |
| 49 | Account/job separate; traceable recovery | PG paper_jobs recovery/cancel/worker-fencing and immutable audit |
| 50 | Safe APIs/logs/export, no sensitive execution payload | unit/test_m17_job_contracts.py; own jobs/hidden legacy runtime; report exports |
| 51 | Node/npm/ECharts risk reviewed | Node 22 CI; audit and controlled-input browser XSS checks, residual risks below |
| 52 | Export verification budget and large-window preflight | unit/test_m17_report_export_budget.py; test_m17_contract_capture_entry.py; PG contract_capture_entry_pg |

## Performance Evidence

CI publishes `m17-capacity-measurements` JSONL. Real 1/30/250-day runs use actual
queue/claim/source-read/financial-job commit, one explicit manually approved buy,
then carried holdings. No financial/source mocks. Every day verifies three SUCCESS
heads, Job completion, immutable fill, single charged fee, cash conservation and
T+1 sellability. Setup/assertion queries are excluded from measured work.
Predeclared limits: <=400 SQL/day and <15 seconds/day; total linear budget.
Synthetic two-symbol calendar is not a claim of full-market production throughput.

Separate frozen-summary measurements use 1/30/250 fee-paying synthetic ledger
dates, <=14 SQL/read and <30 seconds. They are not a substitute for daily replay.
History row/byte overflow refuses before loading historical JSON. Final measured
values are retained in the
[JSONL artifact](https://github.com/sssssssssh/ssh_stock/actions/runs/38663846267/artifacts/11940377655).

| Operation | Days | SQL total | Maximum daily SQL | Seconds total | Maximum daily seconds |
|---|---|---|---|---|---|
| Actual daily advance | 1 | 203 | 203 | 0.309 | 0.309 |
| Actual daily advance | 30 | 6148 | 205 | 7.329 | 0.305 |
| Actual daily advance | 250 | 51248 | 205 | 60.981 | 0.309 |
| Frozen summary | 1 | 12 | n/a | 0.056 | n/a |
| Frozen summary | 30 | 12 | n/a | 0.097 | n/a |
| Frozen summary | 250 | 12 | n/a | 0.608 | n/a |

The independent M16.6 1/36-window capacity rerun also passed: 14 SELECTs each,
0.0322/0.2315 seconds and 31905/1148661 JSONB bytes. This larger explicit repository
budget exercise is separate from the default chat turn's 100-contract refusal.
Browser screenshots are retained in the CI `m16-6-synthetic-browser` artifact,
including the M17 subdirectory. Local Edge screenshots were also inspected.

## Security And Remaining Operational Work

Official npm audit reviewed on 2026-10-14: 11 advisories overall (4 critical,
3 high, 4 moderate); omit-dev 4 (2 high, 2 moderate, no critical). Runtime-declared
dependencies include ECharts XSS, source-map-js and Vite/esbuild dev-server issues;
dev tooling has additional critical advisories. These are not claimed fixed.
The final Nginx image serves static dist, not a Vite development server. ECharts
accepts bounded typed dates/Decimal strings, controlled series and richText tooltip,
not user HTML/options. XSS probes run in a real browser. Taskbook section 16 calls
for a separate dependency-upgrade PR with regression, not a forced major upgrade here.

No live market, broker, real LLM or production-account exercise is claimed. Synthetic
browser API tests are paired with actual PG HTTP/transaction tests. User staging
backup, reviewed migration and deliberate feature enablement remain deployment work.
No production auto-migration or changes to trading strategy weights were made.

## Operations And Recovery

See README's M17 Runbook for backup/migration, manual-first rollout, separate
API/Worker/Scheduler restart, EOD readiness, sequential gap repair, cancellation,
explicit retry, drift review, monitoring and disaster restore. Disable automatic
flags to stop scheduling; pause accounts to prevent new executable approvals.
Rollback by disabling features while retaining 0053 and immutable financial
history. Never delete history or force downgrade to make an older app start.

Earlier rejected candidates remain visible in Git/CI: A duplicate CHECK names and
test filename collision; D reversed fixture tuple; E three synthetic source update
timestamps. Each was corrected and rerun without weakening financial assertions.
F candidate bcf4ea7 / CI 38661921595 was cancelled while blocked: independent
progress used UPDATE against the JobRun FK KEY SHARE held by its financial
transaction. Progress and cancellation now use NO KEY UPDATE; a SQL lock-mode
regression and ten-second lock-wait bounds in new PG tests prevent silent hangs.
The capacity fixture uses the existing 36-window maximum (108 contracts against
the unchanged 100-contract limit), not an impossible 37-window study. M16 report
creation timestamps are fixed on initial insert to the simulated clock; both a
valid prior report and a future report rejection are exercised regardless of CI date.
CI 38662750607 then completed with 1637 passed/3 failed; after those two fixture
fixes, CI 38663317402 had 1640 passed/1 failed. The remaining partial-sale fixture
used a target weight that became a non-lot after fees. It now derives a legal
whole-lot target and asserts actual sold/remaining quantities and the original buy
stage. No lot rule was relaxed. All cases passed final CI 38663846267.
