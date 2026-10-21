# A4-2 SQL and Actual Cursor Plan Matrix

Production SQL is frozen. All alternate statements are in
`scripts/ab_read_experiment_v14_a4_2.py::sql`, used only by the marked laboratory.

| Task ID | Receipt variant | Shape | Protection |
| --- | --- | --- | --- |
| S0 | Q0_LEGACY_RAW / Q0_SERVICE_CONTROL | Unchanged frozen TEMP VIEW; old SELECT | Not safety equivalent |
| S0 protected | Q0_SAFETY_EQUIVALENT | Same SELECT, wrapped E0, full-frame sort and T8 | Existing E0 contract |
| S1 | Q1_CURRENT | Exact frozen date-limited merge and SQL ORDER BY | Existing E0 |
| S2 | Q2_CURRENT | Same SQL in 5-open-day calendar intervals | Existing E0 |
| S3 | S3 | Date-bounded complete B-key MATERIALIZED CTE, JSONB anti-join | Existing E0 |
| S3 inline | S3_INLINE | Same CTE NOT MATERIALIZED | Existing E0 |
| S3 narrow | S3_KEYS | MATERIALIZED keys only; decode B separately, avoid copying JSON into temp workset | Existing E0 |
| S4 | S4 | Full typed date/code LEFT JOIN, missing complete key selects A | Existing E0 |
| S5 | S5 | Narrow-key S3 without SQL ORDER BY; identical complete-frame Python sort | Existing E0 |
| S6 | Not implemented | Native temporary cache deliberately deferred | Not a shortcut into stage C |

All keys, including tombstones and wrong-version/hash B, enter masking. Identity
filtering happens only after merge. Every optimized SQL must first pass unchanged
whole-root redundant key/payload validation: without it the date CTE can be wrong.
S5 deliberately retains native whole-record decoding; projecting only requested
JSON fields could hide malformed unrequested fields and change error semantics.

Every receipt retains real psycopg ServerCursor names, all FETCH batch sizes,
first-row/5000/EOF times, close state, per-window metrics and all slow samples.
Supplemental untimed probes preserve SELECT ANALYZE BUFFERS, DECLARE estimates and
auto_explain actual DECLARE/full-FETCH plans (actual rows/loops/buffers/temp I/O).
Plan probes run after alternating timed trials, never as a substitute for FETCH.
Planner comparisons use only transaction-local cursor_tuple_fraction 0.1/1.0.
No production indexes, temporary caches, planner defaults or timeout are changed.

Window matrix: None/1/3/5/10/20 open days, but each interval covers every calendar
date, including stored closed-day anomalies. All windows are joined into one typed,
globally sorted frame before any engine would run. Monthly trials call the actual
FactorService._read_trade_status method with 430-natural-day bounds; only its
transport is substituted in-process. They do not run independent rolling engines.

The strengthened golden suite reuses frozen tests for all native requested fields,
NULL/dtype/order, wrong identities, rebuilds and other roots. Additional experiments
reuse real Worker cancel/57014/disconnect and final publication-source rejection.
This document makes no estimate-only performance claim; measured tables belong in
`v14_a4_2_experiment_results.md` and per-SHA CI raw artifacts.
