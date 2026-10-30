# W04 Business Parity / W05 Resource Boundary

R4 isolated Linux targeted run: **66 passed in 487.28 s**, including all
three OFF/ON lifecycle nodes. `green-pg17-retry.xml` retains both arms'
cost observations and exact per-table financial hashes.

The unchanged `tests/integration/test_worker02_r2_lifecycle.py` executes real
queued `recalculate`, `daily` and `catchup` root lifecycles OFF/ON. Each arm
gets a new random isolated PostgreSQL database, the same deterministic seed
(420 calendar-day history) and a synthetic Provider; no TuShare is called.
The real Worker claim, calculators, candidate storage and publish path run.

Each root must finish SUCCESS and PUBLISHED with successful children. Exact
per-table natural-key ordering, values, JSON, versions and configuration
hashes are compared. The only excluded columns are enumerated by the old
test: per-run calculation/job UUIDs, timestamps and surrogate IDs on the
three explicitly named tables. Financial/natural-key/JSON columns are not
arbitrarily discarded. Raw/derived/candidate/publication evidence is covered
by the old lifecycle and companion Worker tests, not by receipt-only mocks.

JUnit property `worker02_r2_cost_observations` holds both arms' per-table row
counts/dtypes/SHA-256 and wall/CPU/RSS/SQL-count/WAL observations. Diagnostics
records query/FETCH/frame, compute, candidate lookup/store and publication.
Nested timings are not additive. Lifetime high-water RSS and cluster WAL
delta retain their original limitations; neither is advertised as exclusive
per-stage memory or statement cost. `factor_window` remains NOT_INSTRUMENTED.

## Capacity Preflight

The matrix remains **1,443,097 rows x 3 rounds**. The existing read-only
resource preflight is run without changing its 4 GiB planning reserve.
Observed VM total RAM: 3,953,963,008 bytes; available during this round:
1,500,606,464 bytes; temporary runner limit: 1,342,177,280 bytes; available
test disk: 19,559,845,888 bytes. The isolated test PG is version 170006 with
pg_stat_statements preloaded. Test DB marker and independent physical system
identifier are validated by the original helper before every owned create/drop.

Outcome: **RESOURCE_DEFERRED**. Zero benchmark rounds and zero million-row
capacity measurements completed. No SQL plan/performance improvement is
claimed from the small parity input. No memory limit, benchmark scale,
acceptance threshold or production SQL/index/algorithm is changed.

## Field Status

**FIELD_NOT_RETESTED**. The historical incident and its 785000-row/57014
report are leads only. R4 does not read production PG, `.env`, TuShare, ECS,
onsite Writer or physical G1, release a production job, or recalculate it.
Production authority is not installed or independently approved. Historical
R3 field access is not reused as authorization or R4 field evidence.
