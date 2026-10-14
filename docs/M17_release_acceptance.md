# M17 Release Acceptance

**In development, not sealed; PAPER is not usable yet.** Current A foundation,
B-F not implemented. No business database migration/cleanup or automatic trades.

## A Evidence

Local M17 focused pytest: 97 passed. `python -m pytest tests/unit -q`: 1174 passed,
2 inherited warnings. Alembic heads: one 0053. Full pytest/PG17/current/heads/Ruff
are pending isolated GitHub CI. First CI run 38500210299 failed on a duplicate
order CHECK name; source-hash CHECK was renamed and a name-collision regression
also identified a fill fee-JSON CHECK name collision, now fixed. Retesting is
required. Cross-owner tests require an actual foreign-key violation on first
insert, and financial tests require actual CHECK violations, not duplicate-key
errors. No local full pytest against the user business DB.
No frontend, API or worker path yet; no financial formula or M13-M16 identity change.

## Taskbook Matrix

A-PG tests exist but are pending CI acceptance. Partial is not full completion.

| # | Scenario | Evidence / remaining gate |
|---|---|---|
| 01 | migration/old hashes | A-PG roundtrip, actual legacy rows, metadata comparison pending |
| 02 | nonempty downgrade | A-PG refusal with preserved ledger pending |
| 03 | account states | A unit passed; PG head/terminal tests pending |
| 04 | not BACKTEST | A independence/guard unit passed; D write path pending |
| 05 | cross-owner 404 | Partial A scoped FKs; B-E HTTP pending |
| 06 | default disabled | A unit passed; F scheduler pending |
| 07 | closed-day observation | B pending |
| 08 | source/version/coverage | B pending |
| 09 | T excludes future | B pending |
| 10 | corrections preserve old hash | A-PG immutable pending; B workflow pending |
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
| 23 | pending conflict | A-PG unique index pending; C audit pending |
| 24 | true next open | C/D pending |
| 25 | EOD gate | D pending |
| 26 | bad price/zero volume | D pending |
| 27 | suspension/ST/limits | D pending |
| 28 | legal quantities | D pending |
| 29 | T+1 sellable | A-PG bounds pending; D timing pending |
| 30 | Decimal fees | D pending |
| 31 | cash competition | D pending |
| 32 | unique execution keys | A-PG keys pending; D retries pending |
| 33 | crash/lost response | D/F pending |
| 34 | concurrent workers | D/F pending |
| 35 | sealed source drift | A-PG sealed result pending; D source checks pending |
| 36 | corporate actions | D pending |
| 37 | finance conservation | A-PG structural checks pending; D replay pending |
| 38 | no skipped open days | D pending |
| 39 | pause/resume gaps | D/F pending |
| 40 | benchmark unavailable | A-PG NULL/status pending; E pending |
| 41 | counterfactual not NAV | E pending |
| 42 | no reverse rewrite | A-PG immutable pending; E path pending |
| 43 | M16 owner/hash binding | B pending |
| 44 | no LIVE/broker | A PAPER-only config passed; C/E API pending |
| 45 | M13-M16 regression | isolated full CI pending |
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
Proceed to B only after A PG17 gate passes. Full monitoring/pause/disaster/recovery
Runbook is a required F deliverable, not yet implemented.
