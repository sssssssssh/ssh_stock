# M17 Release Acceptance

**In development, not sealed.** A/B/C/D accepted; E implemented pending isolated
PG acceptance, F pending. No business DB migration/cleanup/trades.

## D Accepted And E Candidate

D commit a0f0cd4da8c3533a9fd40fef1c6c6d33bb7be9e6 passed
[CI 38514217405](https://github.com/sssssssssh/ssh_stock/actions/runs/38514217405):
1518 pytest, 88% backend coverage, Ruff, 0053 current=heads, Docker/Compose,
frontend coverage/build and legacy browser regression. This resolves the D gate.

E local verification: 1236 unit pytest, full Ruff, npm ci with Node 22,
121 Vue tests (81.94% statement coverage), production build and actual M17 browser
acceptance at 1440/390: manual approval, lost response/reload, pagination,
SVG series, XSS and outage recovery. Screenshots reviewed for layout and axis fit.
PG API/source/review/queue tests require the E CI gate. F dispatch/recovery remains
pending, so queue success does not yet imply job completion.
E candidate 34c3897 / CI 38527890255: 1542 passed, 3 failed. The new EOD gate
correctly rejected three synthetic next-day rows whose ORM update timestamp used
the runner's real current date. Those scenarios now explicitly set a synthetic
post-close ingestion timestamp before the synthetic derived calculation. Assertions
remain unchanged; the corrected candidate must rerun the entire PG gate.

## B Evidence (Accepted)

Local `python -m pytest tests/unit -q`: 1185 passed. Ruff passed. Added actual PG
tests in test_m17_decision_sources.py for T+1 isolation, raw/derived staleness,
missing/old source identities, dirty range, deterministic ranking, corrected-source
immutability, owner/security/revision/idempotency and WATCH zero-order behavior.
M16 exact report binding is tested without giving Agent execution capabilities.
No migration change (0053 remains head), API or frontend change in B.
B gate passed at [CI 38506248886](https://github.com/sssssssssh/ssh_stock/actions/runs/38506248886)
for cd7ec91, with full PG17/migrations/Ruff/container/frontend/legacy browser steps.
No claim that PAPER execution is ready.

## C Evidence (Accepted)

Added pure risk/Decimal/manual DTO tests, strict authenticated write API tests and
actual PG atomicity/retry/failed-approval/pending-conflict/race tests. Account snapshot
reads are independent from BACKTEST and reconcile with immutable initial/financial
ledger. Financial execution is still absent; approvals cannot generate fills.
No migration change (0053), no strategy/hash/Agent permission changes.

## A Evidence

Local M17 focused pytest: 97 passed. `python -m pytest tests/unit -q`: 1174 passed,
2 inherited warnings. Full-suite collection: 1420 tests, no name collisions.
Accepted code: `219120bb73a1da273f9076955bccad8f4cb63b65`.
[Isolated CI](https://github.com/sssssssssh/ssh_stock/actions/runs/38501965762)
passed: PostgreSQL 17; 1420 pytest, 87% backend coverage; Ruff; empty migration
roundtrip; 0053 current=heads; Docker/Compose/nginx; Vue tests/build;
existing M16 browser acceptance at 1440/390. These are legacy browser regressions,
not acceptance of a new M17 UI (which is still pending E).
First CI run 38500210299 failed on a duplicate
order CHECK name; source-hash CHECK was renamed and a name-collision regression
also identified a fill fee-JSON CHECK name collision, now fixed. Retesting is
completed in the accepted CI. Run 38501597460 passed migration roundtrip but collection found
unit/integration test module name collision; the unit module is now named
test_m17_foundation_contracts.py. Cross-owner tests require an actual FK on first
insert, and financial tests require actual CHECK violations, not duplicate-key
errors. No local full pytest against the user business DB.
No frontend, API or worker path yet; no financial formula or M13-M16 identity change.

## Taskbook Matrix

### Historical A-D Gate Tracking

B commit cd7ec918: CI 38506248886 passed, 1443 pytest, 87% coverage.
C commit dc773ebd: CI 38509773000 passed, 1480 pytest, 87% coverage,
0053 current=heads, Ruff, Compose build and existing frontend/browser regressions.
Sources/requests/approval/risk API tests cover matrix 07-23, 43/44, plus existing
legacy compatibility. D implementation adds independent account lifecycle and
atomic daily replay; its PG gate is not yet accepted. E/F remain unimplemented.
No user DB migration or full local pytest against business data was performed.

D candidate 6cfe8c0 failed CI 38513408709 at fixture setup: the new test reversed
the shared helper's (session factory, engine) tuple. No D financial assertion ran;
this is not an accepted PG gate. Corrected fixture and added sell/limit/AFTER_CLOSE
regressions before rerun. Local unit suite: 1233 passed; full Ruff passed.

A-PG proofs below passed the accepted CI. Partial is not full M17 completion.

| # | Scenario | Evidence / remaining gate |
|---|---|---|
| 01 | migration/old hashes | A-PG passed: roundtrip, actual legacy rows, metadata comparison |
| 02 | nonempty downgrade | A-PG passed: refusal with preserved ledger |
| 03 | account states | A unit/PG head/terminal tests passed; application lifecycle D pending |
| 04 | not BACKTEST | A independence/guard unit passed; D write path pending |
| 05 | cross-owner 404 | A scoped FKs passed for all 11 child types; B-E HTTP pending |
| 06 | default disabled | A unit passed; F scheduler pending |
| 07 | closed-day observation | B pending |
| 08 | source/version/coverage | B pending |
| 09 | T excludes future | B pending |
| 10 | corrections preserve old hash | A-PG immutable passed; B workflow pending |
| 11 | stable ranking | B pending |
| 12 | risk/watch reasons | B pending |
| 13 | manual/LLM boundary | C/E pending; registry unchanged |
| 14 | WATCH/reject no order | C pending |
| 15 | atomic approval/order | C pending |
| 16 | approval rollback | C pending |
| 17 | same-payload replay | B/C pending |
| 18 | changed-payload 409 | B/C pending |
| 19 | approval/reject races | C pending |
| 20 | expired window | C pending |
| 21 | paused/closed | C/D pending |
| 22 | risk limits | A config validation passed; C/D pending |
| 23 | pending conflict | A-PG unique index passed; C audit pending |
| 24 | true next open | C/D pending |
| 25 | EOD gate | D pending |
| 26 | bad price/zero volume | D pending |
| 27 | suspension/ST/limits | D pending |
| 28 | legal quantities | D pending |
| 29 | T+1 sellable | A-PG bounds passed; D timing pending |
| 30 | Decimal fees | D pending |
| 31 | cash competition | D pending |
| 32 | unique execution keys | A-PG keys passed; D retries pending |
| 33 | crash/lost response | D/F pending |
| 34 | concurrent workers | D/F pending |
| 35 | sealed source drift | A-PG sealed result passed; D source checks pending |
| 36 | corporate actions | D pending |
| 37 | finance conservation | A-PG structural checks passed; D full replay pending |
| 38 | no skipped open days | D pending |
| 39 | pause/resume gaps | D/F pending |
| 40 | benchmark unavailable | A-PG NULL/status passed; E workflow pending |
| 41 | counterfactual not NAV | E pending |
| 42 | no reverse rewrite | A-PG immutable passed; E path pending |
| 43 | M16 owner/hash binding | B pending |
| 44 | no LIVE/broker | A PAPER-only config passed; C/E API pending |
| 45 | M13-M16 regression | A isolated full CI passed; rerun each phase |
| 46 | 1/30/250 performance | F pending |
| 47 | desktop/mobile | E/F pending |
| 48 | errors/doubleclick/refresh | C/E/F pending |
| 49 | account/job separation | A separate schemas; F recovery pending |
| 50 | safe API/log/export | E/F pending |
| 51 | Node/npm/ECharts | P2 F pending; inherited alerts not cleared |
| 52 | M16 verification budgets | P2 F pending; M16 unchanged |

## Rollback And Next Entry

Keep paper.enabled=false. A introduces no production auto-migration or job.
Apply Alembic only through reviewed deployment; never delete historical data to
force downgrade. With history, disable configuration and retain immutable evidence.
The A PG17 gate passed; B is the next implementation phase. Full monitoring/pause/disaster/recovery
Runbook is a required F deliverable, not yet implemented.
