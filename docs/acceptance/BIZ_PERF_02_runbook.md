# BIZ-PERF-02 Isolated Runbook

Do not load business `.env` or supply a cloud URL. Use a freshly owned dedicated
loopback PG17 instance; record its independently obtained physical system ID and
UUID marker. Supply TEST_DATABASE_URL, V14_TEST_INSTANCE and
V14_TEST_SYSTEM_IDENTIFIER explicitly. The DB name must end `_test`.
The v14 helper verifies both before creating/dropping its random UUID child DB.
Migrations apply only to disposable children. Never run CI downgrade on user data.

Keep FACTOR_INPUT_REUSE_ENABLED, RAW_PREFLIGHT_BATCH_ENABLED,
FACTOR_CPU_OPTIMIZATION_ENABLED and AB_MERGE_READ_ENABLED false. LLM is disabled.
Use the repository Python 3.12 dependencies. No production Worker is launched:
the harness invokes existing claim/execute functions only against its verified DB.

```powershell
$env:PYTHONPATH = 'backend;.'
python -m scripts.business_test_runner tests/integration/test_business_quality_batch.py -q
python -m scripts.business_test_runner tests/integration/test_business_quality_continuity.py -q
python -m scripts.business_quality_matrix --stocks 4 --repeats 3 --output .codex_tmp/biz02-new
```

The matrix must start on master, with the candidate business bytes committed.
It independently verifies actual backend/config/migration bytes against each
implementation SHA. It archives the fixed old source without switching branches.
Each sample owns a new DB; no inherited candidate or published result is reused.
Observe process/DB inactivity before starting; never run tests concurrently with
the matrix. Stop on unsupported resources rather than borrowing a business server.

The observer requires the packaged PG17 auto_explain module and synthetic-server
superuser LOAD capability. It never installs extensions or changes server files.
Session controls enable only the first actual lookup per table; JSON plans contain
actual rows/buffers, not query parameters/conditions. Client notification may arrive
on the following protocol Sync. Missing/invalid plans fail the sample, never replay
after publication or substitute a fabricated empty plan. Observer SQL and wall
time are disclosed. RSS is process-lifetime high-water, not exclusive stage RSS.

Inspect matrix.json, per-sample JSON/gzip/exit/log, all nine exact golden pairs,
stage medians and every anomaly. Never sum overlapping stages. The tool always
retains PERFORMANCE_OPEN / RESOURCE_DEFERRED, even for a complete small matrix.
Million-row or cloud execution requires independent qualified resources and
separate execution authorization; this command cannot grant it.

## Regression And Rollback

Run unfiltered pytest/Ruff and the existing ordinary CI. Linux-only resource/pidfd
tests require a capable native runner, not Windows collection or the Linux 3.10 VM.
Keep original tests, coverage >=70%, migrations, frontend/build and Compose checks.
Never weaken source contracts, xfail, skip or dispatch costly experiments to get green.

Rollback by a new revert commit for the BIZ-PERF-02 business change after review.
No schema downgrade, quality certificate rewrite, cache purge, task replay or
publication cleanup is needed. Existing false flags do not disable this small
always-equivalent candidate batching change; revert its code to restore singleton
writes. In production, any future deployment/drain/restart needs separate approval.
Stop only this task's UUID PG instance once evidence is collected; never kill
another test/app process, prune containers or delete earlier lab artifacts.
