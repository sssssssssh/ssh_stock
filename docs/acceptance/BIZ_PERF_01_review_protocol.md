# BIZ-PERF-01 review: frozen diagnostic protocol v1

## Scope and admission

Base 06b4cd6ee1783c399bdb89264c8da6190f282273; immutable historical source
1e510532bd140110e29b10b6e4eed30fbd573159. Current static fingerprint is distinct from
historical performance and G1 admission. No real A4/G1 run, cloud connection, business service,
configuration enable, resource purchase, or production job retry is authorized by this protocol.

## One SQL diagnosis

Commit this protocol and its exact harness before execution. Run
`python -m scripts.business_recalc_diagnosis --output <new-private-evidence.json>` only with
explicit TEST_DATABASE_URL, V14_TEST_INSTANCE UUID and V14_TEST_SYSTEM_IDENTIFIER referring to
the separately owned PG17 loopback instance. The existing helper migrates and removes only
its newly created UUID database. Never reuse a business .env or lower a timeout for a PASS.

Deterministic dataset: 1,000 stock codes, every weekday in 2022–2025: 1,043,000 StockDaily,
same-count adjustment/status facts, stock metadata and configured benchmark indices.
Existing migrated keys/indexes, normal ANALYZE once after load; no speculative index or planner hints.
This is a SQL diagnosis only, not the required representative ten-table Worker acceptance matrix.
Free-disk reserve 8GiB checked before/through load and each stage; existing Worker memory and
publication budgets unchanged. Falling below the reserve stops with RESOURCE_DEFERRED.
Any failed observation is retained; do not restart this trial to get a better result.

Invoke the actual FactorInputWindow production prepare for these fixed windows in order:
2022-11-27..2024-01-31, 2023-01-27..2024-03-31, 2024-10-27..2025-12-31.
The accumulated evidence range is retained, including the root's status candidate query.
Replay captured SELECTs with EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) under the same SHARE locks.
Report replay plans separately from the original prepare wall times; keep every sample.
Close the cache and run an independent final verify, preserving all seven original budget charges.
No production SQL changes may be justified from missing plans. Full candidate/quality/opportunity
plans, incrementally safe fingerprints and any SQL changes remain open until measured.

## Required full acceptance (unchanged)

The full Worker matrix is 1/3/12 months × old/new × at least three interleaved runs,
>=1,000,000 StockDaily with 250 trading-day warmup, monthly 430 natural-day lookback, representative
nonempty public/candidate ten tables, identical snapshot/version/resources/cache convention.
No eight-stock or empty-theme/signals fixture substitutes for it. Every run must finish SUCCESS/PUBLISHED,
all ten financial digests and identities must match exactly, independent RR readers see only A,
failures/cancel/timeout/disconnect/dirty repair/multiple-child catchup retain their original semantics.
Full 12-month median must improve >=30%, inclusive of all validation and publication.
No stable P95 inference from n=3; no retries for PASS. Missing resource evidence => RESOURCE_DEFERRED,
PERFORMANCE_OPEN; SQL-only results do not close capacity or performance admission.

## Regression and delivery

Keep all original 4,925 baseline pytest case identities and negative assertions. Four original ordinary
workflows must run on the final exact SHA. Original expensive dispatch admission stays closed.
Preserve RED XML and original CI artifacts; report local platform failures separately from Linux CI.
No skip/xfail, weakened hash guard, widened budget or rewritten historical evidence is permitted.
