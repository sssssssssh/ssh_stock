# BIZ-PERF-02 Isolated Runbook

Outcome: BUSINESS_CHANGE_WITHDRAWN. Current quality writes use the baseline six
singleton calls. Do not deploy or replay the rejected candidate to obtain a pass.

## R1 Documentation Review Only

The [R1 closeout](BIZ_PERF_02_closeout.md#r1-evidence-closure) and
[exact-SHA CI summary](biz_perf_02/ci_8f4e607_r1.json) verify existing GitHub
receipts for 8f4e6071b74ae90dd95eb56a71ade1ed3dcb1e6a. Rehash existing archives,
parse their safe JUnit/JSON, and read job/step conclusions; do not start a
database, service, test or performance matrix for this documentation task.
The historical reproduction/rollback commands below remain for traceability,
not execution authorization in R1. Do not revert withdrawal commit 8f4e6071.
A05/A06 stay PARTIAL, and performance/capacity remain open/deferred. Validate
only document scope, links, JSON, unchanged experiment rules and quality Git blob;
show the full diff for owner review before committing. Do not push without
explicit authorization, and do not automatically start another phase.

## Historical Isolated Reproduction

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
python -m scripts.business_quality_matrix --stocks 4 --repeats 3 --candidate-sha 6c4096e5de77368c67ff1c2cff7ddd3285a8e56e --output .codex_tmp/biz02-new
```

The command above reproduces the rejected historical candidate, not current code.
Do not rerun merely to override its failed retention rule. The matrix must start
on master, with the candidate business bytes committed.
It independently verifies actual backend/config/migration bytes against each
implementation SHA. It obtains the fixed old source without switching the user's branch.
Both source contexts now use clean detached local shared Git clones with LF bytes;
the initial archive/live cohort was stopped and is not used for retention.
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

Business rollback is already performed by a new withdrawal commit; candidate
commits remain in history. No schema downgrade, quality certificate rewrite,
cache purge, task replay or publication cleanup is needed. To undo all task tooling
after review, prepare one combined new revert of all BIZ-PERF-02 commits in reverse
order using --no-commit, inspect the combined diff and test before committing.
Never revert the withdrawal alone: that would re-enable the rejected candidate.
Never reset, amend or rewrite history. Any production deployment/drain/restart
needs separate approval.
Stop only this task's UUID PG instance once evidence is collected; never kill
another test/app process, prune containers or delete earlier lab artifacts.
