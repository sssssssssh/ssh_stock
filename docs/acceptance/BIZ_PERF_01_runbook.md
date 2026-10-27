# BIZ-PERF-01 Runbook

Default: all three new switches false; AB_MERGE_READ_ENABLED=false.
No automatic production operations are performed by this change.

## Isolated Measurements

Provision a NEW dedicated loopback PG17, not an SSH tunnel/business instance. Record
its custom v14.test_instance UUID and physical system identifier. Set explicit
TEST_DATABASE_URL (database name ends _test), V14_TEST_INSTANCE and
V14_TEST_SYSTEM_IDENTIFIER. Never paste credentials into artifacts or logs.

```powershell
$env:PYTHONPATH = 'backend;.'
python -m scripts.business_test_runner -q
python -m scripts.business_recalc_measure --stocks 4 --months 1 --output .codex_tmp/biz-perf/old.json
python -m scripts.business_recalc_measure --stocks 4 --months 1 --optimized --output .codex_tmp/biz-perf/new.json
```

For the old command, PYTHONPATH must point first to the backend extracted from
`git archive 1e510532bd140110e29b10b6e4eed30fbd573159`; use the SAME measurement script.
Do not switch branches or overwrite the user's tree. Measurement flags affect only
the fresh child process. `--profile` is diagnostic only; do not mix profiled/unprofiled
timings. Repeat symmetrically/interleaved, no other tests running, retain slow/failing
runs. The small defaults are smoke, NOT the required million-row capacity test.
Use 1/3/12 months, sufficient stocks for >1M actual stock_daily rows, and compare
complete SUCCESS/PUBLISHED results and source hashes before claiming acceptance.

```powershell
python -m scripts.business_recalc_matrix --stocks 8 --repeats 3 --output .codex_tmp/biz-perf-matrix
python -m scripts.business_cloud_diagnostic_plan
```

The first command is SMALL local smoke, not capacity closure; use a NEW output
directory for each cohort. The second only prints the unexecuted read-only plan.
Published task evidence uses lossless `.json.gz` observations plus JSON summaries;
both compressed and uncompressed SHA256 are independently checkable. Installation
archives, database files and raw execution logs remain ignored and are not delivered.

The test runner verifies the physical target before imports/migrations, disables
Settings .env loading and runs the full pytest entry point. Windows cannot collect
old Linux-only resource-module tests; `--continue-on-collection-errors` can run the
remaining collected tests but DOES NOT erase errors or mean full pytest passed.

## Cloud Read-Only Plan (NOT AUTHORIZED)

No script here opens a cloud connection or reads .env. After separate approval, an
operator would supply a dedicated read-only connection explicitly, begin READ ONLY,
record SELECT 1 latency and server version/settings, then inspect only aggregates of
pg_stat_activity for the worker's application_name (state/wait_event_type/wait_event).
Never export query text, bind parameters, user names or connection strings.
Capture SQLSTATE 57014 and fixed query label from the existing sanitized Worker log.
Named-cursor per-FETCH budgets and whole-job wall time are different; neither may be
expanded to manufacture success. EXPLAIN ANALYZE is a separately reviewed read load.
No real task is submitted as part of this diagnostic approval.

## Topology And Rollback

A: keep Windows Worker and measure reduced repeated transport, CPU and source-hash cost.
B: dedicated same-region/VPC isolated Worker, same dataset/config/resources and run
order; measure RTT/throughput first. Budget VM CPU/RAM/disk, network egress, private
routing, TLS and access controls; prices require a current provider quote, not an
assumed number. B is not presumed faster and is not deployed by this task.

After independent capacity acceptance and explicit deployment approval, stop admitting
new work, allow the current owner to finish, verify no old Writer remains, then deploy
one Worker with the reviewed flags. Scheduler remains under its separate approval.
Rollback: drain safely and set all three flags false, reload the old/current compatible
Worker. No schema downgrade, task replay, A cleanup, timeout changes or migration.
