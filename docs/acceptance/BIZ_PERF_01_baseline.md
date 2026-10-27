# BIZ-PERF-01 Baseline

Baseline commit: `1e510532bd140110e29b10b6e4eed30fbd573159`.
Status: PERFORMANCE_OPEN; no cloud access.

The first unmodified business smoke used an independently initialized Windows PG17.11,
loopback-only, explicit UUID marker plus physical system identifier. Existing Alembic
head was installed only in self-owned synthetic databases. No .env/business DB access.

Four synthetic securities, 1-month request (January 2025), 900 calendar days of Raw
history, full Worker/service/quality/publication. Actual unprofiled overall: 18.078 s;
CPU: 14.984 s; SELECT: 5684; job SUCCESS; ledger PUBLISHED. This is NOT capacity proof.

A separate frozen-source profiled run (git archive of the baseline, no backend edits)
measured 34.953 s overall; profiling overhead means it MUST NOT be compared as a speedup
against an unprofiled candidate. Profile: factor compute 15.736 s, raw preflight 5.516 s;
factor daily/adj/status/basic/index reads 0.387/0.328/0.346/0.046/0.265 s.
Across 13 factor chunks, daily/adj each delivered 17064 rows, status 7332, index 12798,
basic 52. The request output has 23 trading days; warmup adds 250 prior open days.
This confirms repeated input transport, not a production bottleneck attribution.

Full-scale 1/3/12-month symmetrical >=3-per-implementation measurements, server plans,
actual wire bytes and the >=30% complete-job target remain separate requirements.
Loopback SQL driver timings do not identify cross-WAN wait or exclusive server CPU.

## Final Small Matrix

PG17.11 / Windows / one loopback instance, same frozen timestamps, Raw snapshot
hashes and financial identity. Eight securities, AB/BA interleaving, three complete
old and three complete new runs per case. No other test process ran concurrently.
All 18 jobs SUCCESS/PUBLISHED; all 9 input/identity/table-digest pairs match.
This is a distinct cohort from the initial 4-stock smoke/profile above.

| Months | Actual Raw Daily Rows | Old Median s | New Median s | Reduction | Old/New SELECT Median |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 5320 | 24.750 | 16.625 | 32.8% | 5689 / 2111 |
| 3 | 5648 | 33.032 | 22.688 | 31.3% | 7694 / 3577 |
| 12 | 7224 | 75.485 | 59.063 | 21.8% | 17278 / 10548 |

Twelve-month factor input transport: daily and adj each 63056 -> 6544 rows;
trade status 43192 -> 4088; benchmark 23646 -> 2454; basic 192 -> 8.
Source verification scans remain real overhead, not zero-cost reuse.
Process-lifetime peak RSS ranges: baseline 220618752..230350848 bytes, new
223334400..228995072 bytes. Retained compact input peak <=340014 bytes in this
small fixture; this does not establish a million-row memory cap or peak reduction.

Receipts: [baseline](biz_perf_01/baseline.json), [after](biz_perf_01/after.json),
[golden](biz_perf_01/financial_golden.json), [chain](biz_perf_01/end_to_end.json),
[queries](biz_perf_01/query_counts.json). Each summary references a lossless gzip
JSON observation with compressed/uncompressed SHA256. Raw receipts contain no
prices, SQL bind parameters, credentials or absolute source paths.
SQLAlchemy operation counts and cursor FETCH counts are separate, not packet counts.

Earlier interrupted exploration is not mixed into this final-source cohort. Its
successful/failing samples and interruption reason are retained in the validation
summary; neither slow samples nor the 12-month shortfall are discarded.
